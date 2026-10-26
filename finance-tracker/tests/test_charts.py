"""Chart payload tests — the /api/charts contract with the frontend.

Bug history: pivot_table leaves NaN in months where a category had no
transactions; ``reindex(fill_value=0)`` only fills MISSING month rows, not NaN
cells inside existing rows. Flask then emitted literal ``NaN`` (invalid JSON),
the browser's JSON.parse failed, ``state.charts`` stayed empty, and every
overview panel showed "not enough data". These tests pin the no-NaN contract.

Run from project root:  pytest tests/ -q
"""
import json
from datetime import datetime

from backend.analytics.charts_data import compute_chart_data


def _row(day, direction, amount, category):
    return {
        "txn_date": datetime(2025 if day < 20 else 2026, max(2, day - 7), day % 28 + 1),
        "direction": direction,
        "amount": amount,
        "merchant": f"M{category}{day}",
        "category": category,
        "balance": None,
        "raw_text": "test",
        "source": "sms",
    }


def test_category_months_series_never_contains_nan(tmp_db):
    """Sparse categories must contribute explicit 0.0 for empty months."""
    rows = [
        # one Food txn in Feb 2025, one Transport txn in Jan 2026 -> the pivot
        # cell for (Jan 2026, Food) and (Feb 2025, Transport) would be NaN
        _row(10, "debit", 450.0, "Food & Dining"),
        _row(12, "debit", 120.0, "Transport & Fuel"),
    ]
    # force the two txns into DIFFERENT months 10 months apart
    rows[0]["txn_date"] = datetime(2026, 1, 2)
    rows[1]["txn_date"] = datetime(2025, 12, 3)

    tmp_db.insert_rows(rows)
    payload = compute_chart_data()

    series = payload["category_months"]["series"]
    bad = {cat: [v for v in vals if v != v]           # v != v  <=>  NaN
           for cat, vals in series.items()}
    assert not any(v for v in bad.values()), f"NaN survived in series: {bad}"


def test_chart_payload_is_strict_json_serializable(tmp_db):
    """allow_nan=False would raise on any leftover NaN (the Flask-side bug)."""
    rows = [
        _row(3, "debit", 80.0, "Shopping"),
        _row(5, "debit", 220.0, "Others"),
        _row(9, "credit", 7500.0, "Income"),
    ]
    tmp_db.insert_rows(rows)
    payload = compute_chart_data()
    # The exact failure mode observed in the browser: JSON.stringify emitting
    # literal NaN tokens instead of numbers.
    json.dumps(payload, allow_nan=False)


def test_chart_payload_sane_with_single_month(tmp_db):
    """Edge case: only one month of data must not crash or emit NaN."""
    rows = [
        _row(4, "debit", 60.0, "Food & Dining"),
        _row(8, "debit", 190.0, "Food & Dining"),
    ]
    tmp_db.insert_rows(rows)
    payload = compute_chart_data()
    json.dumps(payload, allow_nan=False)
    assert payload["empty"] is False
