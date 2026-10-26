"""Seeding orchestrator: generate -> parse -> clean -> categorize -> store.

Every data path into the system flows through here:
  - ensure_seeded()      first-run bootstrap (only if DB empty)
  - reseed(new_seed)     'regenerate data' button
  - ingest_sms(text)     user-pasted SMS block
  - ingest_sms_bulk(raw) a WHOLE exported SMS dump file (txt / XML backup)
  - ingest_csv(file)     uploaded standard CSV

Real personal SMS franken-source note: a phone's SMS dump is full of OTPs,
promotions, and delivery updates. The parser naturally rejects anything
without an amount+date+direction — those are counted as "failed" in the
report rather than crashing. Nothing leaves this machine (local SQLite).
"""
from __future__ import annotations

import codecs
import csv as _csvmod
import html
import io
import json
import os
import random
import re
import sqlite3
import tempfile
import zipfile
import xml.etree.ElementTree as ET

import backend.categorizer  # noqa: F401  (ensures rule engine import works)
import config
from backend import database
from backend.cleaner import clean_csv, clean_parsed, df_to_db_rows
from backend.data_generator import generate_sms
from backend.parser import parse_sms

# Android "SMS Backup & Restore" XML: <sms ... body=" Rs.499 debited ...... " ... />
_XML_BODY_RE = re.compile(r'body="([^"]*)"')

# keys that plausibly hold the SMS text inside JSON objects / CSV headers
_JSON_KEYS = ("body", "message", "text", "sms", "content", "msg", "message_text")
# keys that plausibly hold the message timestamp (epoch s / ms, or a date string)
_JSON_DATE_KEYS = ("date", "date_ms", "timestamp", "time", "date_sent",
                   "sent", "received", "epoch", "created")

_SQLITE_MAGIC = b"SQLite format 3\x00"
_ZIP_MAGIC = b"PK\x03\x04"


def _decode_bytes(data: bytes) -> str:
    """UTF-8 / UTF-8-BOM / UTF-16 (with or without BOM) / cp1252 tolerated."""
    for bom, enc in ((codecs.BOM_UTF8, "utf-8-sig"),
                     (codecs.BOM_UTF16_LE, "utf-16-le"),
                     (codecs.BOM_UTF16_BE, "utf-16-be")):
        if data.startswith(bom):
            return data[len(bom):].decode(enc, errors="replace").rstrip("\x00")
    # NUL bytes in a text dump => UTF-16 without BOM (UTF-8 would "succeed"
    # decoding interleaved NULs, so we must check BEFORE trying UTF-8).
    nulls = data.count(0)
    if nulls > len(data) // 8:
        zeros_odd = sum(1 for i in range(1, len(data), 2) if data[i] == 0)
        enc = "utf-16-le" if zeros_odd > nulls - zeros_odd else "utf-16-be"
        out = data.decode(enc, errors="replace").rstrip("\x00")
        return out
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def split_sms_messages(raw, filename: str = "") -> list[str]:
    """Split an exported SMS dump into individual SMS strings.

    Convenience wrapper around :func:`extract_entries` that drops the
    per-message timestamps (backward compatible with pasted-text paths).
    """
    return [e["text"] for e in extract_entries(raw, filename or "")]


def extract_entries(raw, filename: str = "") -> list[dict]:
    """Split an exported SMS dump into entries: [{text, date_ms|None}, ...].

    ``date_ms`` is epoch milliseconds when the CONTAINER knows the time
    (SMS-Backup XML ``date=`` attribute, JSON date fields, CSV/TSV date
    column, mmssms.db ``date`` column) — bank SMS bodies themselves often
    have no date, so the parser needs this fallback.
    """
    entries, _formats = _extract_entries(raw, filename, depth=0)
    return entries


def _extract_entries(raw, filename: str, depth: int) -> tuple[list[dict], list[str]]:
    """Route a dump into per-format extractors. Returns (entries, formats)."""
    # ---- binary containers first (they don't survive text decode) ----
    if isinstance(raw, bytes):
        low_name = filename.lower()
        if raw.startswith(_SQLITE_MAGIC) or low_name.endswith((".db", ".sqlite", ".sqlite3")):
            return _sqlite_entries(raw)
        if raw.startswith(_ZIP_MAGIC) or low_name.endswith(".zip"):
            entries, kinds = [], []
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                for name in z.namelist():
                    if name.endswith("/"):
                        continue
                    m, k = _extract_entries(z.read(name), name, depth + 1)
                    entries.extend(m)
                    kinds.extend(k)
            return entries, kinds or ["zip"]

        text = _decode_bytes(raw)
    else:
        text = raw

    s = text.lstrip()
    # ---- xml ----
    if s.startswith("<") and "<sms" in s.lower() and 'body="' in s.lower():
        return _xml_entries(text)
    # ---- json ----
    if s[:1] in ("{", "["):
        return _json_entries(text)
    # ---- csv / tsv ----
    if filename.lower().endswith((".csv", ".tsv")) or _looks_like_csv(text):
        return _csv_entries(text)
    # ---- plain text ----
    return _txt_entries(text)


def _date_ms_of(value) -> int | None:
    """Heal a container timestamp: ms (>1e12) or seconds (>1e9) -> epoch ms."""
    if value is None:
        return None
    try:
        v = int(float(str(value).strip()))
    except (ValueError, TypeError):
        return None
    if v > 10**12:
        return v
    if v > 10**9:
        return v * 1000
    return None


def _looks_like_csv(text: str) -> bool:
    """CSV only when the FIRST line is a header naming a message column —
    a normal bank-SMS line full of commas must NOT be treated as CSV."""
    first = text.splitlines()[0].lower() if text.splitlines() else ""
    return "," in first and any(h in first for h in _JSON_KEYS)


def _xml_entries(text: str):
    """SMS Backup & Restore XML — ET walk keeps the per-SMS `date` epoch."""
    entries: list[dict] = []
    try:
        root = ET.fromstring(text)
        for e in root.iter("sms"):
            body = re.sub(r"\s+", " ", html.unescape(e.get("body") or "")).strip()
            if not body:
                continue
            entries.append({"text": body, "date_ms": _date_ms_of(e.get("date"))})
    except ET.ParseError:
        # last-resort regex fallback for slightly malformed exports
        block_re = re.compile(
            r'<sms\b[^>]*?\bbody="([^"]*)"[^>]*?>', re.IGNORECASE)
        dm_re = re.compile(r'\bdate="(\d+)"')
        for m in block_re.finditer(text):
            body = re.sub(r"\s+", " ", html.unescape(m.group(1) or "")).strip()
            if body:
                dm = dm_re.search(text[max(0, m.start() - 400):m.end()])
                entries.append({"text": body,
                                "date_ms": _date_ms_of(dm.group(1)) if dm else None})
    if not entries:
        # extremely defensive: plain regex sweep (SMS-Backup files are huge
        # single-line XML; ET handles them, but belt-and-braces for odd files)
        for body_raw in _XML_BODY_RE.findall(text):
            body = re.sub(r"\s+", " ", html.unescape(body_raw)).strip()
            if body:
                entries.append({"text": body, "date_ms": None})
    return entries, ["xml"]


def _json_entries(text: str):
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Unreadable JSON dump: {exc}") from None
    if isinstance(data, dict):
        for key in ("messages", "sms", "data", "records"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
        else:
            raise ValueError("JSON dump needs a top-level list or a 'messages' list.")
    if not isinstance(data, list):
        raise ValueError("JSON dump must be a list of SMS strings or objects.")
    out = []
    for item in data:
        if isinstance(item, str):
            out.append({"text": item.strip(), "date_ms": None})
        elif isinstance(item, dict):
            text_val = next((str(item[k]) for k in _JSON_KEYS if item.get(k)), None)
            if text_val:
                ts = next((_date_ms_of(item[k]) for k in _JSON_DATE_KEYS if item.get(k)), None)
                out.append({"text": re.sub(r"\s+", " ", text_val).strip(), "date_ms": ts})
    return out, ["json"]


def _csv_entries(text: str):
    first = text.splitlines()[0] if text.splitlines() else ""
    delim = "\t" if "\t" in first else ","
    rows = [r for r in _csvmod.reader(io.StringIO(text), delimiter=delim)
            if any(c.strip() for c in r)]
    if not rows:
        return [], ["csv"]
    header = [c.strip().lower() for c in rows[0]]
    col = next((i for i, h in enumerate(header) if h in _JSON_KEYS), None)
    if col is None:
        raise ValueError("CSV/TSV export needs a message column named "
                         "body / message / text / sms / content / msg.")
    date_col = next((i for i, h in enumerate(header) if h in _JSON_DATE_KEYS), None)
    out = []
    for r in rows[1:]:
        if len(r) <= col or not r[col].strip():
            continue
        ts = _date_ms_of(r[date_col]) if date_col is not None and len(r) > date_col else None
        out.append({"text": re.sub(r"\s+", " ", r[col]).strip(), "date_ms": ts})
    fmt = "tsv" if delim == "\t" else "csv"
    return out, [fmt]


def _sqlite_entries(data: bytes):
    """Android mmssms.db: body + (optional) date from every table that has them."""
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    try:
        tmp.write(data)
        tmp.close()
        conn = sqlite3.connect(tmp.name)
        out = []
        try:
            tables = [t[0] for t in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")]
            for tbl in tables:
                cols = [c[1] for c in conn.execute(f"PRAGMA table_info({tbl})")]
                if "body" not in cols:
                    continue
                date_sql = ", date" if "date" in cols else ""
                for row in conn.execute(f'SELECT body{date_sql} FROM "{tbl}"'):
                    body = row[0]
                    if body:
                        ts = _date_ms_of(row[1]) if len(row) > 1 else None
                        out.append({"text": re.sub(r"\s+", " ", body).strip(), "date_ms": ts})
        finally:
            conn.close()
        return out, ["sqlite"]
    finally:
        os.unlink(tmp.name)


def _txt_entries(text: str):
    """plain text: prefer blank-line-separated blocks (SMS wraps joined),
    otherwise each line is one SMS. No container timestamps in this format."""
    if not text.strip():
        return [], ["text"]
    if re.search(r"\n\s*\n", text):                                # blank lines exist
        blocks = [re.sub(r"\s+", " ", b).strip()
                  for b in re.split(r"\n\s*\n+", text)]
        return [{"text": b, "date_ms": None} for b in blocks if b], ["text"]
    return [{"text": ln.strip(), "date_ms": None}
            for ln in text.splitlines() if ln.strip()], ["text"]


def _pipeline(raw_entries, source: str = "sms") -> dict:
    """Full ETL for a batch of SMS entries (dicts with text/date_ms, or plain
    strings from the synthetic generator). Returns the cleaning report."""
    normalized = []
    for item in raw_entries:
        if isinstance(item, str):
            normalized.append({"text": item, "date_ms": None})
        else:
            normalized.append(item)

    parsed, bad_lines = [], []
    for e in normalized:
        row = parse_sms(e["text"], e.get("date_ms"))
        if row is None:
            bad_lines.append(e["text"])
        else:
            parsed.append({**row})

    df, report = clean_parsed(parsed)
    report["rows_in"] = len(normalized)
    report["parsed"] = len(parsed)
    report["failed"] = len(bad_lines)
    report["failed_lines"] = bad_lines[:10]

    if not df.empty:
        # cross-batch dedup: skip rows the DB already holds (identical
        # date+direction+amount+merchant) — lets mam upload the same dump as
        # .txt, .json AND .csv without silently doubling the numbers
        already = database.dup_keys()
        key_series = df.apply(lambda r: (r["txn_date"].strftime("%Y-%m-%d"),
                                         r["direction"], round(r["amount"], 2),
                                         r["merchant"]), axis=1)
        mask = key_series.isin(already)
        report["already_stored"] = int(mask.sum())
        df = df[~mask]
    report["rows_out"] = int(len(df))
    if not df.empty:
        database.insert_rows(df_to_db_rows(df, source=source))
    return report


def ensure_seeded() -> dict | None:
    """Seed on first run only. Returns the cleaning report, or None if data exists."""
    database.init_db()
    if database.row_count() > 0:
        return None
    return _pipeline(generate_sms(config.SEED, config.DATA_MONTHS))


def reseed(seed: int | None = None) -> dict:
    """Wipe and regenerate with a given (or random) seed."""
    database.reset_db()
    seed = seed if seed is not None else random.randint(1, 999_999)
    report = _pipeline(generate_sms(seed, config.DATA_MONTHS))
    report["seed"] = seed
    return report


def ingest_sms(text: str) -> dict:
    """Parse manually pasted SMS text, clean, categorize, and append."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return _pipeline(lines, source="sms")


def ingest_sms_bulk(raw, filename: str = "") -> dict:
    """Parse a whole exported SMS dump file, one upload at a time.

    ``raw`` is the uploaded file's bytes (or pasted text); format is
    auto-detected: txt / XML backup / CSV / TSV / JSON / ZIP / SQLite db.
    Raises ValueError with a friendly message for unusable files.
    """
    try:
        entries, kinds = _extract_entries(raw, filename or "", depth=0)
    except ValueError:
        raise
    if not entries:
        raise ValueError(
            "No SMS messages found in this file. Supported: txt dumps "
            "(one SMS per line or blank-line blocks), Android SMS Backup XML, "
            "CSV/TSV with a body/message column, JSON message lists, ZIP "
            "archives, and mmssms.db / .sqlite databases.")
    report = _pipeline(entries, source="sms")
    report["messages_in_file"] = len(entries)
    report["file_format"] = "+".join(sorted(set(kinds))) or "text"
    return report


def ingest_csv_rows(df_csv, filename: str) -> dict:
    """Clean + store an uploaded CSV. Returns report including the filename."""
    df, report = clean_csv(df_csv)
    if not df.empty:
        database.insert_rows(df_to_db_rows(df, source="csv"))
    report["file"] = filename
    return report
