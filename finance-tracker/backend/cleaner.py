"""ETL cleaning layer — the "Transform" stage.

Mirrors DAV Practical 5 tasks: duplicates, missing values, trailing spaces,
date normalization, numeric coercion, standardized names, and a provenance
report ("cleaning report") that the dashboard can show.
"""
from __future__ import annotations

import re
from datetime import datetime

import pandas as pd

import backend.categorizer as categorizer

# raw merchant text -> canonical display name (first match wins)
_MERCHANT_CANON: list[tuple[str, str]] = [
    ("netflix", "Netflix"),
    ("spotify", "Spotify"),
    ("primevideo", "Prime Video"),
    ("prime video", "Prime Video"),
    ("hotstar", "JioHotstar"),
    ("youtube", "YouTube Premium"),
    ("adobe", "Adobe CC"),
    ("golds gym", "Gold's Gym"),
    ("gold's gym", "Gold's Gym"),
    ("swiggy", "Swiggy"),
    ("zomato", "Zomato"),
    ("blinkit", "Blinkit"),
    ("zepto", "Zepto"),
    ("bigbasket", "BigBasket"),
    ("dmart", "DMart"),
    ("amzpay", "Amazon"),
    ("amazon", "Amazon"),
    ("flipkart", "Flipkart"),
    ("myntra", "Myntra"),
    ("croma", "Croma"),
    ("uber", "Uber"),
    ("ola ", "Ola"),
    ("rapido", "Rapido"),
    ("irctc", "IRCTC"),
    ("airtel", "Airtel Postpaid"),
    # bill-payment rails (real data uses these VPAs for electricity/recharge)
    ("bbps", "BBPS Bill Pay"),
    ("billdesk", "BillDesk Bill Pay"),
    # real-data merchants first (before the fuzzy umbrella keys below):
    ("paytmqr", "Paytm UPI"),
    ("paytm", "Paytm UPI"),
    ("euronet", "Euronet ATM"),
    ("jio@", "Jio Recharge"),
    ("jio", "Jio Fiber"),
    ("vodafone", "Vi Postpaid"),
    ("bescom", "BESCOM Electricity"),
    ("electricity", "Electricity Bill"),
    ("gas", "Indane Gas"),
    ("rent", "House Rent"),
    ("landlord", "House Rent"),
    ("emi", "Bike Loan EMI"),
    ("bikesloan", "Bike Loan EMI"),
    ("loan", "Loan EMI"),
    ("pharmacy", "Apollo Pharmacy"),
    ("apollo", "Apollo Pharmacy"),
    ("hospital", "Hospital"),
    ("bookmyshow", "BookMyShow"),
    ("pvr", "PVR Cinemas"),
    ("inox", "INOX Cinemas"),
    ("udemy", "Udemy"),
    ("coursera", "Coursera"),
    ("salary", "Salary (ABC Tech)"),
    ("cashback", "Cashback"),
    ("interest", "Interest Credit"),
    ("starbucks", "Starbucks"),
    ("haldiram", "Haldiram's"),
    ("chayos", "Chaayos"),
    ("domino", "Domino's"),
]

_JUNK_CHARS = re.compile(r"[*\-_.]+$|[*\-_.]+")  # trailing *1234, dots, dashes


def canonical_merchant(merchant: str) -> str:
    """'AMZPAY*1243' -> 'Amazon'; 'NETFLIX.COM' -> 'Netflix'; unknown -> 'Unknown'.

    UPI handles that aren't in the canonical map fall back to their readable
    local part: 'sachinhiwale424-2@oksbi' -> 'Sachinhiwale' (person-to-person
    transfers show a person, not a bank code soup).
    """
    m = (merchant or "").strip()
    if not m:
        return "Unknown"
    m = re.sub(r"\s+", " ", m).strip()
    low = m.lower()
    for key, canonical in _MERCHANT_CANON:
        if key in low:
            return canonical
    if "@" in low:
        local = low.split("@", 1)[0]
        # payment-platform handles keep their label; name handles drop the
        # trailing id digits/loan numbers ("bajajpay.6879729.05..." -> "Bajajpay")
        lead = re.match(r"([a-z]{3,})", local)
        if lead:
            return lead.group(1).title() or "Unknown"
        # phone-number handles ("9322553779-2@ibl") keep the phone number
        local = local.split("-", 1)[0]
        if re.fullmatch(r"\d+", local):
            return local
        return _JUNK_CHARS.sub(" ", local).title().strip() or "Unknown"
    cleaned = _JUNK_CHARS.sub(" ", m).title().strip()
    return cleaned or "Unknown"


def clean_parsed(parsed_rows: list[dict]) -> tuple[pd.DataFrame, dict]:
    """parsed dicts (from parser.py) -> tidy DataFrame + cleaning report."""
    report = {"rows_in": len(parsed_rows)}

    df = pd.DataFrame(parsed_rows)
    report["failed_dates_dropped"] = 0
    report["duplicates_removed"] = 0
    report["unknown_merchants"] = 0
    report["reformatted"] = 0

    if df.empty:
        return df, report

    # 1) dates -> datetime (drop rows with invalid dates)
    df["txn_date"] = pd.to_datetime(df["txn_date"], errors="coerce")
    bad_dates = df["txn_date"].isna()
    report["failed_dates_dropped"] = int(bad_dates.sum())
    df = df[~bad_dates].copy()

    # 2) amounts -> numeric (parser already yields floats; guard against junk)
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
    df = df[df["amount"].notna() & (df["amount"] > 0)].copy()
    df["amount"] = df["amount"].round(2)

    # 3) unknown merchant fill (Practical 5: report missing values)
    blank = df["merchant"].isna() | (df["merchant"].astype(str).str.strip() == "")
    report["unknown_merchants"] = int(blank.sum())
    df.loc[blank, "merchant"] = "Unknown"

    # 4) standardize merchant names (strip spaces/junk, map to canonical)
    df["merchant"] = df["merchant"].apply(canonical_merchant)

    # 5) direction sanity
    df["direction"] = df["direction"].str.lower().str.strip()
    df = df[df["direction"].isin(["debit", "credit"])].copy()

    # 6) exact duplicates (same date+direction+amount+merchant)
    before = len(df)
    df = df.drop_duplicates(
        subset=["txn_date", "direction", "amount", "merchant"], keep="first"
    ).copy()
    report["duplicates_removed"] = before - len(df)

    # 7) categories via rule engine
    df["category"] = df.apply(
        lambda r: categorizer.categorize(r["merchant"], r["direction"]), axis=1
    )

    # 8) sort + index reset
    df = df.sort_values("txn_date").reset_index(drop=True)
    report["rows_out"] = len(df)
    report["reformatted"] = report["rows_in"] - report["duplicates_removed"] - report["failed_dates_dropped"]
    return df, report


def clean_csv(df_csv: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Manually uploaded CSV -> tidy DataFrame + report (expects the standard
    columns: date, direction, amount, merchant; category/balance/source optional)."""
    report = {"rows_in": len(df_csv), "failed_dates_dropped": 0,
              "duplicates_removed": 0, "unknown_merchants": 0, "reformatted": 0}

    if df_csv.empty:
        return pd.DataFrame(), report

    cols = {c.strip().lower(): c for c in df_csv.columns}
    required = ["date", "direction", "amount", "merchant"]
    missing = [c for c in required if c not in cols]
    if missing:
        raise ValueError(f"CSV missing required columns: {', '.join(missing)}")

    out = pd.DataFrame()
    out["txn_date"] = pd.to_datetime(df_csv[cols["date"]], dayfirst=True, errors="coerce")
    report["failed_dates_dropped"] = int(out["txn_date"].isna().sum())
    out = out.assign(
        direction=df_csv[cols["direction"]].astype(str).str.lower().str.strip(),
        amount=pd.to_numeric(
            df_csv[cols["amount"]].astype(str).str.replace(r"[₹,\s]", "", regex=True),
            errors="coerce",
        ),
        merchant=df_csv[cols["merchant"]].astype(str).str.strip(),
    )

    out = out[out["txn_date"].notna() & out["amount"].notna() & (out["amount"] > 0)].copy()
    out["amount"] = out["amount"].round(2)

    # direction: rows indexed after filtering; re-derive from the source frame
    out["direction"] = df_csv.loc[out.index, cols["direction"]].astype(str).str.lower().str.strip()
    out.loc[~out["direction"].isin(["debit", "credit"]), "direction"] = "debit"

    if "balance" in cols:
        out["balance"] = pd.to_numeric(df_csv[cols["balance"]], errors="coerce")
    else:
        out["balance"] = None
    out["raw_text"] = ""

    blank = out["merchant"].isna() | (out["merchant"].str.strip() == "")
    report["unknown_merchants"] = int(blank.sum())
    out.loc[blank, "merchant"] = "Unknown"
    out["merchant"] = out["merchant"].apply(canonical_merchant)

    before = len(out)
    out = out.drop_duplicates(subset=["txn_date", "direction", "amount", "merchant"], keep="first")
    report["duplicates_removed"] = before - len(out)

    out["category"] = out.apply(
        lambda r: categorizer.categorize(r["merchant"], r["direction"]), axis=1
    )
    out = out.sort_values("txn_date").reset_index(drop=True)
    report["rows_out"] = len(out)
    report["reformatted"] = report["rows_in"] - report["duplicates_removed"] - report["failed_dates_dropped"]
    return out, report


def df_to_db_rows(df: pd.DataFrame, source: str = "sms") -> list[dict]:
    """DataFrame -> list of dicts ready for database.insert_rows()."""
    if "source" not in df:
        df["source"] = source
    rows = []
    for _, r in df.iterrows():
        rows.append({
            "txn_date": r["txn_date"].to_pydatetime(),
            "direction": r["direction"],
            "amount": float(r["amount"]),
            "merchant": r["merchant"],
            "category": r["category"],
            "balance": float(r["balance"]) if pd.notna(r.get("balance")) else None,
            "raw_text": r.get("raw_text", ""),
            "source": r.get("source", source),
            "created_at": datetime.now(),
        })
    return rows
