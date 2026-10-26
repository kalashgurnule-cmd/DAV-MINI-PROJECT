"""Entry point for the Personal Finance Shadow Tracker.

Usage:
    python run.py

Starts the dashboard at http://localhost:5000.
The database ships EMPTY by design — load real data via the Ingest tab
(paste SMS / upload SMS dump / upload CSV) or the explicit demo button.
"""
import config
from backend.app import app
from backend.database import init_db, row_count


def main() -> None:
    print("=" * 60)
    print("  Personal Finance Shadow Tracker")
    print("=" * 60)

    init_db()
    n = row_count()
    if n == 0:
        print("  Database is EMPTY - load data in the dashboard:")
        print("    Ingest tab -> paste SMS / upload SMS dump / upload CSV")
    else:
        print(f"  {n} transactions in database.")

    print(f"  Dashboard: http://{config.HOST}:{config.PORT}")
    print("=" * 60)
    app.run(host=config.HOST, port=config.PORT, debug=False)


if __name__ == "__main__":
    main()
