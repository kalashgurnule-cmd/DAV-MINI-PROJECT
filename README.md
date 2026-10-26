# 💰 Personal Finance Shadow Tracker

Turn messy bank SMS / transaction data into a clean, explainable money dashboard:
**Subscription Zombie Detector · Personal Inflation vs CPI · Financial Health Score**.

Runs **100% locally** — Flask backend + browser frontend + SQLite.
No API keys, no internet needed to analyze.

---

## 🧱 Architecture

```
Synthetic dirty SMS generator ─┐
Pasted SMS text ───────────────┤→  parser (regex) → cleaner (ETL) → categorizer
Uploaded CSV ──────────────────┘                     │
                                                     ▼
                                              SQLite + SQLAlchemy
                                                     │
                       ┌─────────────────────────────┼───────────────────────┐
                       ▼                             ▼                       ▼
              overview (monthlies)        zombie detector            inflation index
                       │                     (gap analysis)          vs CPI (YoY)
                       └──────────────┬──────────────┴───────────────────────────┘
                                      ▼
                        REST API (Flask) → Plotly dashboard (vanilla JS)
```

**Data pipeline order (fixed):** `data_generator → parser → cleaner → categorizer → database`

---

## 📁 Folder Structure

```
finance-tracker/
├── run.py                     # entry point: seed + start server
├── config.py                  # seed, months of history, paths, ports
├── requirements.txt
├── AGENTS.md                  # rules for AI agents (Antigravity)
├── backend/
│   ├── app.py                 # Flask routes (REST + static)
│   ├── data_generator.py      # synthetic DIRTY Indian bank SMS
│   ├── parser.py              # regex SMS parser (amount/date/merchant)
│   ├── cleaner.py             # ETL: dedup, missing fills, normalization + report
│   ├── categorizer.py         # keyword rule engine → category
│   ├── database.py            # SQLAlchemy model + helpers
│   ├── seed.py                # orchestrates generate→parse→clean→store
│   └── analytics/
│       ├── overview.py        # monthly income/spend/net + top categories
│       ├── zombies.py         # recurring-payment interval detector
│       ├── inflation.py       # personal price index vs illustrative CPI
│       └── health_score.py    # 5-component weighted score + suggestions
├── frontend/
│   ├── index.html             # 6-tab dashboard shell
│   ├── css/style.css
│   └── js/ api.js · charts.js · ui.js · app.js
├── tests/  test_parser.py · test_zombies.py     (pytest)
└── data/   sample/sample_sms.txt · finance.db   (DB auto-created)
```

---

## 🚀 Run It

```bash
cd finance-tracker
pip install -r requirements.txt
python run.py
```

Open **http://localhost:5000** — the app starts **EMPTY** and shows a
"no transactions loaded yet" hero. Load data from the **Ingest tab**:

1. **Paste bank SMS** (one per line), or
2. **Upload an SMS dump** — the uploader auto-detects the format:
   **.txt** exports (one SMS per line / blank-line blocks),
   **Android "SMS Backup & Restore" XML**, **CSV / TSV** spreadsheets
   (need a body/message/text column), **JSON** message lists,
   **ZIP** archives of any of these, and Android **mmssms.db / .sqlite**
   SMS databases. Encoding sniffs UTF‑8/UTF‑16; OTPs and promos are
   auto-skipped; rows already in the DB are skipped (no double counting), or a
3. **CSV** of transactions (`date, direction, amount, merchant`), or
4. click **"Load demo dataset"** for a synthetic example feed, or upload
   one of the ready-made demo dumps in `data/sample/`:
   `demo_upload.txt`, `demo_sms.csv`, `demo_sms.json`, `demo_sms.zip`,
   `demo_mmssms.db` (regenerate anytime: `py scripts/make_demo_dump.py`).

Run tests:

```bash
pytest tests/ -q
```

---

## 🧪 What Each Tab Shows

| Tab | Content | DAV concept |
|-----|---------|-------------|
| **Overview** | 3-year income/spend/net, donut + top-category table with MoM deltas | time-series aggregation |
| **Zombies** | recurring debit detection (median interval), monthly/annual drain, active vs dormant | interval gap analysis |
| **Inflation** | your basket's price index vs illustrative CPI, category YoY table | index construction, weights |
| **Health Score** | 0–100 gauge: savings, runway, debt, zombie drain, volatility + suggestions | composite scoring |
| **Ledger** | cleaned table, search/filter, CSV export | ETL result inspection |
| **Ingest** | paste SMS, **upload whole SMS dump** (.txt / Android SMS-Backup XML), upload CSV, regenerate dataset | data acquisition |

## 🧬 Deliberate Data-Quality Noise (in the synthetic feed)

- ₹ / Rs / Rs. / INR variants · letter-O digit typos (`8O0`, `18O00`)
- 5 date formats incl. `15th Nov 25` and `03/04/25`
- ~2% exact duplicates · ~3% missing merchants · missing balances
- messy merchant strings (`SWIGGY*NOODLEHOUSE`, `AMZPAY*1243`)

The cleaning report (rows in → duplicates → unknown fills → rows out) prints in
the console on seed and after every ingest — perfect for the viva ETL story.

## 🎓 Map to DAV Practicals

| Practical | Here |
|-----------|------|
| Lab 4 (API data) | Ingest endpoints replace live APIs; same fetch→parse→store flow |
| Lab 5 (ETL + SQLite + SQLAlchemy) | cleaner.py + database.py are a direct extension |
| Lab 8 (Matplotlib/Plotly charts) | frontend/served Plotly charts (paid discipline: each chart has a question) |

## 🔒 Privacy

All data is synthetic (faker) — no real accounts, numbers or SMS anywhere.
