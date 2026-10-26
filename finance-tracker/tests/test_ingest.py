"""Bulk SMS dump splitter tests — plain text, XML, CSV/TSV, JSON, ZIP, SQLite.

Run from project root:  pytest tests/ -q
"""
import io
import json
import sqlite3
import zipfile

from backend.seed import split_sms_messages

TXT_LINES = (
    "Rs.499 debited from HDFC a/c XX4521 on 12-Mar-25 towards NETFLIX.COM. Ref 554212\n"
    "INR 2,400 debited on 07-Mar-25 to GOLDS GYM SUBSCRIPTION. Avl Bal Rs.45,320\n"
)

XML_BACKUP = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<smses count="3">\n'
    '<sms address="HDFC" date="1700000000" body=" Rs.499 debited from HDFC a/c XX4521 on 12-Mar-25 towards NETFLIX.COM. Ref 554212" />\n'
    '<sms address="HDFC" date="1700000001" body="Your OTP is 438291. Do not share!" />\n'
    '<sms address="SBI" date="1700000002" body="INR 18,000 debit on 2025-03-05 toward RENT LANDLORD. Avl Bal Rs.27,100" />\n'
    '</smses>\n'
)

TXT_WRAPPED = (
    "Rs.1,250 debited from HDFC a/c XX4521 on 12-Mar-25\n"
    "towards AMAZON RETAIL IN. Ref 554212\n"
    "\n"
    "Rs.320 debited on 25-Mar-25 to BLINKIT GROCERY 4421\n"
)


def test_txt_one_sms_per_line():
    out = split_sms_messages(TXT_LINES)
    assert len(out) == 2
    assert "NETFLIX" in out[0]
    assert "GOLDS GYM" in out[1]


def test_xml_backup_extracts_bodies():
    out = split_sms_messages(XML_BACKUP)
    assert len(out) == 3                       # no <sms> wrapper lines leak through
    assert any("NETFLIX" in m for m in out)
    assert any("OTP" in m for m in out)
    assert not any(m.startswith("<?xml") for m in out)


def test_txt_blank_line_blocks_joined():
    out = split_sms_messages(TXT_WRAPPED)
    assert len(out) == 2                       # wrapped SMS joined to one line each
    assert "AMAZON RETAIL" in out[0]


def test_empty_input():
    assert split_sms_messages("") == []
    assert split_sms_messages("   \n  ") == []
    assert split_sms_messages(b"", "empty.txt") == []


# ------------------------------------------------------- new formats ----
def test_csv_with_body_column():
    csv_text = ("\n"
                "date,address,body\n"
                "2025-03-12,HDFC,\"Rs.499 debited from HDFC a/c XX4521 on 12-Mar-25 towards NETFLIX.COM. Ref 554212\"\n"
                "2025-03-07,SBI,\"INR 2,400 debited on 07-Mar-25 to GOLDS GYM SUBSCRIPTION. Avl Bal Rs.45,320\"\n")
    out = split_sms_messages(csv_text, "sms_export.csv")
    assert len(out) == 2
    assert "NETFLIX" in out[0]
    assert "GOLDS GYM" in out[1]


def test_csv_without_message_column_raises():
    try:
        split_sms_messages("a,b,c\n1,2,3\n", "x.csv")
        raised = False
    except Exception:
        raised = True
    assert raised


def test_commas_in_plain_sms_not_treated_as_csv():
    """A normal bank SMS that merely contains commas must still parse as text."""
    line = "Rs.1,250 debited from HDFC a/c XX4521 on 12-Mar-25, towards AMAZON RETAIL IN. Ref 554212"
    out = split_sms_messages(line, "note.txt")
    assert len(out) == 1 and "AMAZON" in out[0]


def test_json_list_of_strings():
    data = json.dumps([
        "Rs.499 debited from HDFC a/c XX4521 on 12-Mar-25 towards NETFLIX.COM. Ref 554212",
        "Your OTP is 438291. Do not share!",
        "INR 18,000 debit on 2025-03-05 toward RENT LANDLORD. Avl Bal Rs.27,100",
    ])
    out = split_sms_messages(data.encode("utf-8"), "messages.json")
    assert len(out) == 3
    assert any("RENT LANDLORD" in m for m in out)


def test_json_list_of_objects_uses_body_key():
    data = json.dumps({"messages": [
        {"body": "Rs.499 debited from HDFC a/c XX4521 on 12-Mar-25 towards NETFLIX.COM. Ref 554212",
         "address": "HDFC"},
        {"body": "INR 18,000 debit on 2025-03-05 toward RENT LANDLORD. Avl Bal Rs.27,100"},
    ]})
    out = split_sms_messages(data.encode("utf-8"), "backup.json")
    assert len(out) == 2
    assert any("NETFLIX" in m for m in out)


def test_zip_archive_containing_txt_and_json():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("part1.txt", TXT_LINES)
        z.writestr("part2.json", json.dumps(
            ["INR 18,000 debit on 2025-03-05 toward RENT LANDLORD. Avl Bal Rs.27,100"]))
    out = split_sms_messages(buffer.getvalue(), "all_sms.zip")
    assert len(out) == 3
    assert any("RENT LANDLORD" in m for m in out)
    assert any("GOLDS GYM" in m for m in out)


def test_utf16_le_txt_decodes():
    txt = "Rs.499 debited from HDFC a/c XX4521 on 12-Mar-25 towards NETFLIX.COM. Ref 554212\n"
    data = txt.encode("utf-16-le")           # BOM-less, as some exporters do
    out = split_sms_messages(data, "android_utf16.txt")
    assert out == [txt.strip()]


def test_sqlite_mmssms_db(tmp_path):
    path = tmp_path / "mmssms.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE sms (_id INTEGER PRIMARY KEY, body TEXT, address TEXT, date INTEGER)")
    conn.execute("INSERT INTO sms (body, address, date) VALUES (?, ?, ?)",
                 ("Rs.499 debited from HDFC a/c XX4521 on 12-Mar-25 towards NETFLIX.COM. Ref 554212", "HDFC", 1700000000000))
    conn.execute("INSERT INTO sms (body, address, date) VALUES (?, ?, ?)",
                 ("INR 18,000 debit on 2025-03-05 toward RENT LANDLORD. Avl Bal Rs.27,100", "SBI", 1700000001000))
    conn.commit()
    conn.close()
    out = split_sms_messages(path.read_bytes(), "mmssms.db")
    assert len(out) == 2
    assert any("RENT LANDLORD" in m for m in out)


# ------------------------------------ entries with container timestamps ----
def test_xml_entries_carry_epoch_ms():
    from backend.seed import extract_entries
    entries = extract_entries(XML_BACKUP.encode("utf-8"), "backup.xml")
    assert [e["date_ms"] for e in entries] == [1700000000000, 1700000001000, 1700000002000]
    assert all("netflix" in e["text"].lower() or "otp" in e["text"].lower()
               or "rent" in e["text"].lower() for e in entries)


def test_json_entries_carry_timestamp_fields():
    from backend.seed import extract_entries
    data = json.dumps({"messages": [
        {"body": "Your VPA 7620687415@ibl linked a/c no. XXXXXX5884 is debited for Rs. 149.0 "
                 "and credited to VPA jio@yesbank UPI Ref no 209242109217.",
         "date": 1700001000000},
        {"body": "Rs.499 debited from HDFC a/c XX4521 on 12-Mar-25 towards NETFLIX.COM. Ref 554212"},
    ]})
    entries = extract_entries(data.encode("utf-8"), "backup.json")
    assert entries[0]["date_ms"] == 1700001000000
    assert entries[1]["date_ms"] is None         # body carries its own date


def test_seconds_vs_ms_epoch_unit_healing():
    from backend.seed import extract_entries, _date_ms_of
    assert _date_ms_of(1700000000) == 1700000000000        # seconds -> ms
    assert _date_ms_of(1700000000000) == 1700000000000     # already ms
    assert _date_ms_of("42") is None                       # nonsense year not trusted


def test_pipeline_uses_container_date_fallback(tmp_db):
    """JioPay-style body (no date in text) stored with the XML timestamp date."""
    from backend.seed import ingest_sms_bulk
    JIO_BODY = ("Your VPA 7620687415@ibl linked a/c no. XXXXXX5884 is debited for "
                "Rs. 149.0 and credited to VPA jio@yesbank UPI Ref no 209242109217")
    xml = ('<?xml version="1.0"?>\n<smses count="1">\n'
           '<sms address="JZ-JioPay" date="1698000000000" body="'
           + JIO_BODY + '" />\n</smses>')
    report = ingest_sms_bulk(xml.encode("utf-8"), "calendar.xml")
    assert report["parsed"] == 1
    txns = tmp_db.load_df()
    match = txns[(txns["amount"] == 149.0) & (txns["direction"] == "debit")]
    assert len(match) == 1
    assert str(match["txn_date"].iloc[0])[:10] == "2023-10-23"


def test_second_ingest_of_same_dump_is_full_dedup(tmp_db):
    from backend.seed import ingest_sms_bulk
    JIO_BODY = ("Your VPA 7620687415@ibl linked a/c no. XXXXXX5884 is debited for "
                "Rs. 149.0 and credited to VPA jio@yesbank UPI Ref no 209242109217")
    xml = ('<?xml version="1.0"?>\n<smses count="1">\n'
           '<sms address="JZ-JioPay" date="1698000000000" body="'
           + JIO_BODY + '" />\n</smses>')
    first = ingest_sms_bulk(xml.encode("utf-8"), "a.xml")
    second = ingest_sms_bulk(xml.encode("utf-8"), "b.xml")
    assert first["rows_out"] == 1
    assert second["already_stored"] == 1 and second["rows_out"] == 0
