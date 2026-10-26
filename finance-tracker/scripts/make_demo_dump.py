"""Dev utility: write ready-to-upload demo SMS dump files.

Creates data/sample/demo_upload.txt — a COMPLETELY DIFFERENT synthetic
persona from the internal demo button (own seed, ~2.4 years of history so
both monthly and yearly zombies are detectable, plenty of inflation data).
Also emits the same dump as CSV / JSON / ZIP so the multi-format uploader
can be demonstrated live.

Usage:  py scripts/make_demo_dump.py
"""
from __future__ import annotations

import io
import json
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # project root

import config
from backend.data_generator import generate_sms

DEMO_SEED = 2027        # different persona from the default internal seed
DEMO_MONTHS = 29        # spans 3 Julys -> yearly zombie detected too


def write_variants(msgs: list[str], sample_dir: Path) -> None:
    # 1) classic .txt — one SMS per line
    sample_dir.joinpath("demo_upload.txt").write_text("\n".join(msgs), encoding="utf-8")

    # 2) CSV export with a body column (proper quoting via csv module)
    import csv as _csv
    import io as _io
    buf_csv = _io.StringIO()
    writer = _csv.writer(buf_csv)
    writer.writerow(["date", "body"])
    for m in msgs:
        writer.writerow(["", m])
    sample_dir.joinpath("demo_sms.csv").write_text(buf_csv.getvalue(), encoding="utf-8")

    # 3) JSON backup
    sample_dir.joinpath("demo_sms.json").write_text(
        json.dumps({"messages": msgs}, indent=1), encoding="utf-8")

    # 4) ZIP archive (txt + json inside)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("sms_part1.txt", "\n".join(msgs))
        z.writestr("sms_part2.json", json.dumps(msgs))
    sample_dir.joinpath("demo_sms.zip").write_bytes(buf.getvalue())

    # 5) Android mmssms.db style SQLite
    import sqlite3
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as t:
        tpath = t.name
    conn = sqlite3.connect(tpath)
    conn.execute("CREATE TABLE sms (_id INTEGER PRIMARY KEY, body TEXT, address TEXT)")
    conn.executemany(
        "INSERT INTO sms (body, address) VALUES (?, ?)",
        [(m, "BANK") for m in msgs])
    conn.commit()
    conn.close()
    sample_dir.joinpath("demo_mmssms.db").write_bytes(Path(tpath).read_bytes())
    Path(tpath).unlink()


def main() -> None:
    msgs = generate_sms(seed=DEMO_SEED, months=DEMO_MONTHS)
    sample_dir = config.DATA_DIR / "sample"
    sample_dir.mkdir(parents=True, exist_ok=True)
    write_variants(msgs, sample_dir)
    print(f"wrote {len(msgs)} SMS in 4 formats -> {sample_dir}")


if __name__ == "__main__":
    main()
