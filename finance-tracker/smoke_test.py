"""End-to-end smoke test: seed -> analytics -> API responses."""
import sys, json

sys.path.insert(0, ".")

from backend.seed import ensure_seeded                      # noqa: E402
from backend.database import load_df, row_count             # noqa: E402
from backend.app import app                                 # noqa: E402

print("== seeding pipeline ==")
if row_count() == 0:
    report = ensure_seeded()
    print(f"rows_in={report['rows_in']} dups={report['duplicates_removed']} "
          f"unknown={report['unknown_merchants']} failed={report['failed']} "
          f"rows_out={report['rows_out']}")

df = load_df()
print("stored rows :", len(df))
print("date range  :", df['txn_date'].min(), "->", df['txn_date'].max())
print("categories  :", sorted(df['category'].unique()))
print("merchants sample:", sorted(df['merchant'].unique())[:12])

client = app.test_client()
for url in ["/api/overview", "/api/zombies", "/api/inflation", "/api/health-score", "/api/transactions?limit=5"]:
    res = client.get(url)
    body = res.get_json()
    status = res.status_code
    size = len(json.dumps(body)) if not isinstance(body, dict) else "obj"
    err = body.get("error") if isinstance(body, dict) else None
    print(f"{url}  ->  {status}  {err or ('items ok, bytes=' + str(size))}")

# spot-check key values
ov = client.get("/api/overview").get_json()
z = client.get("/api/zombies").get_json()
inf = client.get("/api/inflation").get_json()
hs = client.get("/api/health-score").get_json()
print("\n== verdict ==")
print("months          :", ov.get("months", [None])[-1] if not ov.get('empty') else "EMPTY")
print("balance         :", ov.get("balance"))
print("savings rate    :", ov.get("savings_rate"), "%")
print("zombie count    :", z.get("count"), "| active drain/mo:", z.get("active_monthly_drain"))
print("zombie names    :", [i['merchant'] for i in z.get("items", [])][:8])
print("personal YoY    :", inf.get("personal_yoy"), "% | CPI YoY:", inf.get("cpi_yoy"), "%")
print("health score    :", hs.get("score"), "/", hs.get("grade"))
print("suggestions     :", len(hs.get("suggestions", [])))
