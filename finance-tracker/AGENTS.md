# Personal Finance Shadow Tracker

## Project Overview
Local web app: Flask (backend) + HTML/CSS/JS (frontend) + SQLite. Parses dirty bank SMS/
transaction data, cleans it (ETL), categorizes, and produces analytics:
Subscription Zombie Detector, Personal Inflation vs CPI, Financial Health Score.

## Tech Stack
- Python 3.10+, Flask 3, SQLAlchemy 2, pandas, faker (synthetic data only), pytest
- Frontend: vanilla JS + Plotly.js via CDN. No build step, no npm.
- Chart layer conventions (charts.js): all charts render through renderChart()
  (skeleton -> empty-state -> data -> 300ms fade; error gets a Retry chip;
  every chart has a "Table" fallback chip + aria note). Colors always come
  from CSS theme vars (THEME/ensureTheme) so re-theming the dashboard
  re-themes the charts. Axes use inrCompact() (₹1.2K/₹45K/₹1.5L/₹2Cr);
  tooltips use inrFull().

## Run Commands
- Setup: `pip install -r requirements.txt`
- Seed + start: `python run.py` (serves http://localhost:5000, auto-seeds DB if empty)
- Tests: `pytest tests/ -q`

## Folder Map
```
run.py              entry point: starts Flask (DB ships EMPTY until you ingest data)
config.py           constants (paths, seed, months of data)
backend/
  app.py            Flask routes (REST API + static serving)
  data_generator.py synthetic dirty SMS/transaction generator (demo button + dump script)
  parser.py         regex SMS parser (amount, date, merchant, direction)
  cleaner.py        ETL cleaning (dedup, missing values, normalization) - report dict
  categorizer.py    keyword rule engine -> category
  database.py       SQLAlchemy models, session, load_df(), dup_keys()
  seed.py           distributor: ingest multi-format dumps -> parse -> clean -> store
  analytics/
    overview.py     monthly income/spend/net, top categories
    charts_data.py  chart payload: daily/weekly spend, category-months,
                    merchants, forecast, auto-budgets, cash-flow waterfall
    zombies.py      recurring-payment interval detection
    inflation.py    personal price index vs synthetic CPI
    health_score.py weighted composite score + suggestions
                    (multi-format dump: txt / XML backup / CSV / TSV / JSON /
                     ZIP archive / Android mmssms.db SQLite; skips rows the
                     DB already holds so the same dump can be uploaded twice)
  analytics/
    overview.py     monthly income/spend/net, top categories
    charts_data.py  chart payload: daily/weekly spend, category-months,
                    merchants, forecast, auto-budgets, cash-flow waterfall
    zombies.py      recurring-payment interval detection
    inflation.py    personal price index vs synthetic CPI
    health_score.py weighted composite score + suggestions
frontend/
  index.html        tabs shell
  css/style.css     colorful dark "aurora" theme
  js/api.js         fetch wrappers
  js/charts.js      Plotly chart builders
  js/ui.js          tables, filters, CSV export, formatting
  js/app.js         tab switching + boot
scripts/
  make_demo_dump.py writes data/sample/demo_upload.txt (different persona, ready to upload)
tests/              pytest for parser, zombies & ingest splitter
data/               finance.db (starts absent) + sample/ (demo dumps in 4 formats)
```

## Rules for Agents
1. Keep modules single-purpose. New analytics = new file in backend/analytics/ + a route in app.py + maybe a frontend tab.
2. The data pipeline order is fixed: data_generator -> parser -> cleaner -> categorizer -> database. Do not reorder.
3. All generated data must use a seeded RNG (config.SEED). `POST /api/reset` may use a random seed; other code must not use unseeded randomness.
4. Never modify files under data/ manually; only the seeding code writes there.
5. Analytics endpoints must return JSON-serializable dicts only (ISO date strings, no Timestamps).
6. Frontend has no bundler: keep scripts plain ES6, loaded in order api.js -> charts.js -> ui.js -> app.js.
7. Currency formatting via Intl.NumberFormat('en-IN', currency INR). Do not hand-write rupee formatting.
8. When touching parser.py, update tests/test_parser.py with a case for the new format.
9. Keep prints minimal in request handlers; heavy logging belongs in seed/pipeline only.
10. Windows-friendly: no POSIX-only paths or signals.
11. The database ships EMPTY. No code may auto-seed on boot; loading synthetic data is always explicit (Ingest tab "Load demo dataset" button or scripts/make_demo_dump.py).
