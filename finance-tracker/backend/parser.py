"""Regex-based parser for Indian bank transaction SMS messages.

The parser is intentionally tolerant of "dirty" text because the synthetic
generator plants noise on purpose:
  - currency written as Rs / Rs. / INR / ₹
  - cheque-style digits with letter O: "8O0" -> 800, "18O00" -> 18000
  - many date styles: 12-Mar-25, 03/04/25, 2025-04-12, 15th Nov 25
  - merchant introduced by: towards / toward / for / at / to
  - missing merchant, missing balance, stray refs

Returns one dict per SMS line; parse errors are skipped and counted.
"""
from __future__ import annotations

import re
from datetime import datetime

_MONTHS = "jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec"

# ---------------------------------------------------------------- amount ----
# comma-form FIRST (needs >=1 comma), then a plain digit run: otherwise a
# greedy 3-digit prefix would swallow "65000" as "650" (real bug found in viva!)
_AMOUNT_RE = re.compile(
    r"""(?:rs\.?|inr|₹)\s*        # currency prefix
        ([0-9O]{1,3}(?:,[0-9O]{2,3})+ | [0-9O]{1,7})    # 1,25,000  |  65000
        (?:\.[0-9O]{1,2})?        # optional decimals
    """,
    re.IGNORECASE | re.VERBOSE,
)

# ---------------------------------------------------------------- balance ----
# available balance first ("Avl Bal Rs.X", "Avlbl Amt:Rs.XCR"), then
# "Total Bal:Rs.XCR" (BOB style shows both; available is the more useful one)
_BAL_AVAIL_RE = re.compile(
    r"avlbl?\.?\s*(?:amt|bal(?:ance)?\.?)\s*:?\s*(?:rs\.?|inr|₹)?\s*"
    r"([0-9O,]+(?:\.[0-9O]{1,2})?)\s*(?:CR)?" ,
    re.IGNORECASE,
)
_BALANCE_RE = re.compile(
    r"(?:avlbl?\.?\s*(?:amt|bal(?:ance)?\.?)\s*:?\s*|total\s*bal\s*:?\s*|"
    r"avl\.?\s*(?:bal(?:ance)?\.?)\s*:?\s*)(?:rs\.?|inr|₹)?\s*"
    r"([0-9O,]+(?:\.[0-9O]{1,2})?)",
    re.IGNORECASE,
)

# ---------------------------------------------------------------- direction ----
# "transferred from A/c" is a debit (money going out); "transferred to" a credit
_DEBIT_RE = re.compile(r"\b(debited|debit|used for|spent|transferred from)\b", re.IGNORECASE)
_CREDIT_RE = re.compile(r"\b(credited|credit|deposited|refund)\b", re.IGNORECASE)
# plain "transferred" with no from/to hint — decide by nearby wording
_TRANSFER_RE = re.compile(r"\btransferred\b", re.IGNORECASE)
# modern BOB shorthand: "Rs.200.00 Dr. from A/C … and Cr. to <vpa>"
_DR_SHORT_RE = re.compile(r"\bdr\.?\s+(?=from\b)", re.IGNORECASE)
_CR_SHORT_RE = re.compile(r"\bcr\.?\s+(?=to\b)", re.IGNORECASE)

# ---------------------------------------------------------------- date ----
_DATE_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("%Y-%m-%d", re.compile(r"(\d{4}-\d{2}-\d{2})")),
    ("%d-%b-%Y", re.compile(rf"(\d{{1,2}}[-/](?:{_MONTHS})[-/]\d{{4}})", re.IGNORECASE)),
    ("%d-%b-%y", re.compile(rf"(\d{{1,2}}[-/](?:{_MONTHS})[-/]\d{{2}})", re.IGNORECASE)),
    ("%d %b %y", re.compile(rf"(\d{{1,2}}\s+(?:{_MONTHS})\s+\d{{2,4}})", re.IGNORECASE)),
    ("%d-%m-%Y", re.compile(r"(\d{1,2}[-/]\d{1,2}[-/]\d{4})")),
    ("%d-%m-%y", re.compile(r"(\d{1,2}[-/]\d{1,2}[-/]\d{2})")),
    # real BOB style: "… Avlbl Amt:Rs.30687.2(17-10-2022 18:24:50)"
    ("%d-%m-%Y %H:%M:%S", re.compile(r"(\d{1,2}-\d{1,2}-\d{4} \d{1,2}:\d{2}:\d{2})")),
    # real BOB shorthand style: "… AvlBal:Rs37613.07(2025:07:22 06:30:56)"
    ("%Y:%m:%d %H:%M:%S", re.compile(r"(\d{4}:\d{2}:\d{2} \d{1,2}:\d{2}:\d{2})")),
    # real BOB text date: "on Date 2025-05-13 01:46:30 PM"
    ("%Y-%m-%d I:%M:%S %p", re.compile(r"(\d{4}-\d{2}-\d{2} \d{1,2}:\d{2}:\d{2} [APap][Mm])")),
]

_MERCHANT_KEYWORDS = ("towards", "toward", "for ", "at ", "to ")
_MERCHANT_STOP = re.compile(r"\.\s*ref|\bref\s*\d|\bref\b|\bavl\b|\bbal\b|\bon\s|\n", re.IGNORECASE)
_MERCHANT_SANITY = re.compile(
    r"^(your|a/c|acc|ending|ref|avl|bal|on\b|rs\.?|inr|₹)", re.IGNORECASE)
# token-level filters for the fallback builder (whole-token matches, NOT prefixes —
# otherwise "OLA" dies because its leading O looks like a fake zero)
_MONTH_WORD_RE = re.compile(r"^(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[.,]?$", re.IGNORECASE)
_NUMERIC_TOKEN_RE = re.compile(r"^[\dOo.,/:\-]+$")
_DATEISH_RE = re.compile(
    r"^\d{1,2}[-/][A-Za-z]{3}[-/]?\d{0,4}$|^\d{4}[-/]\d{1,2}[-/]\d{1,2}$|^\d{1,2}(?:st|nd|rd|th)[.,]?$",
    re.IGNORECASE)

# ---------------------------------------------------------------- promos ----
# Marketing / phishing texts deliberately LOOK like transactions ("Your Rs.8850
# welcome bonus is ready to be credited…"). They must never become ledger rows:
# with XML-borne dates they would otherwise slip past the "no date" guard.
# Also caught here: mandate/collection REQUESTS ("...has requested money,
# on approval Rs 166.00 will be debited") — asking is not spending.
_PROMO_RE = re.compile(
    r"(claim (?:now|bonus|your)|welcome bonus|download\b|https?://|www\.|"
    r"click (?:here|bonus)|\bwin\b|winner|up ?to rs|\bopt ?out|optout|"
    r"unsubscribe|reply\s+(?:yes|stop)\b|install now|congratulations|"
    r"\brummy\b|\bkdssn\b|\bsmsl\b|apply now|to claim\b|referral code|"
    r"hurry[\s!,]|withdraw (?:now|cash|amount)|\bhas requested\b|"
    r"redeem\b|will be (?:debited|credited))",
    re.IGNORECASE)


def _clean_amount(raw: str) -> float | None:
    """'1,25,0O0.50' -> 125000.5  (letter O inside digits -> 0)."""
    fixed = raw.replace(",", "").upper().replace("O", "0")
    try:
        return float(fixed)
    except ValueError:
        return None


def _clean_date(raw: str, fmt: str) -> datetime | None:
    try:
        return datetime.strptime(raw.replace("/", "-"), fmt)
    except ValueError:
        return None


def _extract_date(text: str) -> datetime | None:
    # strip ordinal suffixes first: "15th Nov 25" -> "15 Nov 25"
    text = re.sub(r"(\d{1,2})(st|nd|rd|th)\b", r"\1", text, flags=re.IGNORECASE)
    for fmt, pattern in _DATE_PATTERNS:
        m = pattern.search(text)
        if m:
            dt = _clean_date(m.group(1), fmt)
            if dt:
                return dt
    return None


def _extract_amount(text: str) -> float | None:
    m = _AMOUNT_RE.search(text)
    return _clean_amount(m.group(1)) if m else None


def _extract_balance(text: str) -> float | None:
    m = _BAL_AVAIL_RE.search(text)      # prefer the *available* amount
    if not m:
        m = _BALANCE_RE.search(text)
    return _clean_amount(m.group(1)) if m else None


def _extract_direction(text: str) -> str | None:
    has_debit = bool(_DEBIT_RE.search(text) or _DR_SHORT_RE.search(text))
    has_credit = bool(_CREDIT_RE.search(text) or _CR_SHORT_RE.search(text))
    if has_credit and not has_debit:
        return "credit"
    if has_debit:
        return "debit"
    if _TRANSFER_RE.search(text):
        # bare "transferred": "to: ..." -> outgoing, "from ..." -> incoming
        return "credit" if re.search(r"transferred to\b", text, re.IGNORECASE) else "debit"
    return None


# real-bank merchant patterns (JioPay UPI + Bank of Baroda)
#   debit: "…is credited to VPA paytmqr2810050501b4 UPI Ref no …"  / "credited to
#          sachinhiwale424-2@oksbi UPI Ref:" — the PAYEE is the counterparty
#          (local part may start with a digit: "8668376143@ybl"; the SMS may
#           use full words "credited to VPA x@y" or the shorthand "Cr. to x@y")
_MERCHANT_UPI_PAYEE_RE = re.compile(
    r"(?:credited to\s+(?:VPA\s+)?|cr\.?\s+)"
    r"([A-Za-z0-9][A-Za-z0-9.\-_]*@[A-Za-z0-9.\-_]+|paytmqr[A-Za-z0-9]+)",
    re.IGNORECASE)
#   cash deposit: "Rs.20000 deposited in cash to A/c ...5884."
_CASH_DEPOSIT_RE = re.compile(r"deposited in cash to A/?c", re.IGNORECASE)
#   credit into own a/c: "…thru UPI/229098313411 by RSAL." — remitter after "by"
#   (bounded window instead of [^.]*? so "Rs.110.00" / "A/c ...5884" don't break it)
_MERCHANT_REMITTER_RE = re.compile(
    r"(?:credited to A/?C\b|account is credited)\b.{0,160}?\bby\s+"
    r"([A-Za-z][A-Za-z0-9@.\-]*)", re.IGNORECASE)
#   BOB bare transfer: "Rs.1 transferred from A/c ...5884 to:UPI/22909831341."
_MERCHANT_UPI_TRANSFER_RE = re.compile(r"\bto:UPI/\d+", re.IGNORECASE)


def _extract_real_merchant(text: str, direction: str) -> str | None:
    """Counterparty from real JioPay/BOB SMS bodies, or None to use generic path."""
    if direction == "debit":
        m = _MERCHANT_UPI_PAYEE_RE.search(text)
        if m:
            return m.group(1).rstrip(".,")
        if _MERCHANT_UPI_TRANSFER_RE.search(text):
            return "UPI Transfer"
    else:
        if _CASH_DEPOSIT_RE.search(text):
            return "Cash Deposit"
        m = _MERCHANT_REMITTER_RE.search(text)
        if m:
            return m.group(1).rstrip(".,")
    return None


def _extract_merchant(text: str, direction: str) -> str:
    """Merchant usually follows a keyword ('towards X', 'at X', 'for X') —
    sometimes before the date, so we scan keyword candidates anywhere in the
    text and return the first chunk that looks merchant-like."""
    low = text.lower()
    for kw in _MERCHANT_KEYWORDS:
        start = 0
        while True:
            idx = low.find(kw, start)
            if idx == -1:
                break
            chunk = text[idx + len(kw):]
            merchant = _MERCHANT_STOP.split(chunk)[0].strip(" .,")
            if merchant and not _MERCHANT_SANITY.match(merchant):
                return merchant
            start = idx + len(kw)
    # fallback: strip boilerplate, take first meaningful tokens (e.g. SALARY ABC...)
    tail = re.split(r"\.\s*ref|\bref\s*\d|\bref\b|\bavl\b|\bbal\b", text, flags=re.IGNORECASE)[0]
    tail = re.sub(r"(\d{1,2})(st|nd|rd|th)\b", r"\1", tail, flags=re.IGNORECASE)
    boiler = {
        "debited", "credited", "debit", "credit", "used", "spent", "from", "the",
        "your", "card", "account", "a/c", "acct", "reason", "towards", "toward",
        "at", "to", "for", "with", "and",
    }
    words = [
        w for w in re.split(r"[\s]+", tail)
        if w
        and not _MONTH_WORD_RE.fullmatch(w)
        and not _NUMERIC_TOKEN_RE.fullmatch(w)
        and not _DATEISH_RE.fullmatch(w)
        and not _MERCHANT_SANITY.match(w)
        and not re.fullmatch(r"xx?\d+", w, re.IGNORECASE)
        and w.lower().strip(".,") not in boiler
    ]
    return " ".join(words[:4]).strip(" .,") if words else ""


def parse_sms(text: str, date_ms: int | None = None) -> dict | None:
    """Parse a single SMS into a normalized dict, or None if unparseable.

    ``date_ms`` is an optional epoch-milliseconds timestamp known from the
    container (SMS-Backup XML ``date=`` attr, mmssms.db ``date`` column) —
    used when the body itself carries no date, which is common for JioPay/
    UPI debit alerts.
    """
    if not text or not text.strip():
        return None
    if _PROMO_RE.search(text):
        # marketing junk / mandate REQUESTS — reject outright. Some of these
        # mimic credit language ("...will be credited to your Rummy account"),
        # so there is no exemption for it.
        return None
    direction = _extract_direction(text)
    amount = _extract_amount(text)
    if direction is None or amount is None or amount <= 0:
        return None
    date = _extract_date(text)
    if date is None and date_ms:
        try:
            date = datetime.fromtimestamp(date_ms / 1000)
        except (OSError, OverflowError, ValueError):
            date = None
    if date is None:
        return None
    merchant = _extract_real_merchant(text, direction) \
        or _extract_merchant(text, direction) \
        or ""
    return {
        "txn_date": date,
        "direction": direction,
        "amount": round(amount, 2),
        "merchant": merchant,
        "balance": _extract_balance(text),
        "raw_text": text.strip(),
    }


def parse_report(bad_lines: list[str], parsed: list[dict]) -> dict:
    """Small provenance report used by the /api/ingest endpoint."""
    return {"parsed": len(parsed), "failed": len(bad_lines), "failed_lines": bad_lines[:10]}
