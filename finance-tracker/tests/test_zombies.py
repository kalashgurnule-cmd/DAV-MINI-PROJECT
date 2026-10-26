"""Zombie detector tests — synthetic DataFrames built with pandas directly.

Run from project root:  pytest tests/ -q
"""
from datetime import datetime

import pandas as pd

from backend.analytics import zombies


def _ledger(rows: list[tuple[str, datetime, str, float, str]]) -> pd.DataFrame:
    """(merchant, date, direction, amount, category) -> dirty-df-like frame."""
    return pd.DataFrame(rows, columns=["merchant", "txn_date", "direction", "amount", "category"])


def test_monthly_pattern_detected():
    months = [datetime(2025, 1, 7), datetime(2025, 2, 8), datetime(2025, 3, 6),
              datetime(2025, 4, 7), datetime(2025, 5, 7)]
    df = _ledger([("Netf lix", d, "debit", 499.0, "Subscriptions") for d in months])
    # rename to canonical to bypass cleaner mapping
    df["merchant"] = "Netflix"
    out = zombies.compute_zombies.__wrapped__(df) if hasattr(zombies.compute_zombies, "__wrapped__") else None
    # direct call against monkeypatched loader
    _run_direct(df, expect_merchant="Netflix", expect_freq="monthly")


def test_yearly_pattern_detected():
    years = [datetime(2024, 7, 9), datetime(2025, 7, 8)]
    years.append(datetime(2023, 7, 10))
    years.sort()
    df = _ledger([("Prime Video", d, "debit", 1499.0, "Subscriptions") for d in years])
    df["merchant"] = "Prime Video"
    _run_direct(df, expect_merchant="Prime Video", expect_freq="yearly")


def test_irregular_pattern_not_flagged():
    days = [datetime(2025, 1, 3), datetime(2025, 1, 4), datetime(2025, 3, 28),
            datetime(2025, 4, 2)]  # gaps: 1, 83, 5 -> not recurring
    df = _ledger([("Swiggy", d, "debit", 300.0, "Food & Dining") for d in days])
    df["merchant"] = "Swiggy"
    _run_direct(df, expect_merchant="Swiggy", expect_freq=None)


def test_fewer_than_three_debits_not_flagged():
    df = _ledger([
        ("Netflix", datetime(2025, 1, 4), "debit", 499.0, "Subscriptions"),
        ("Netflix", datetime(2025, 2, 4), "debit", 499.0, "Subscriptions"),
    ])
    df["merchant"] = "Netflix"
    _run_direct(df, expect_merchant="Netflix", expect_freq=None)


# -------------------------------------------------------------- helpers ----
def _run_direct(df: pd.DataFrame, expect_merchant: str, expect_freq: str | None):
    """Patch load_df, run compute_zombies, assert on the result."""
    orig = zombies.load_df
    zombies.load_df = lambda: df
    try:
        out = zombies.compute_zombies()
    finally:
        zombies.load_df = orig

    if expect_freq is None:
        assert all(i["merchant"] != expect_merchant for i in out["items"])
        return

    match = [i for i in out["items"] if i["merchant"] == expect_merchant]
    assert match, f"{expect_merchant} not detected in {out['items']}"
    item = match[0]
    assert item["frequency"] == expect_freq
    assert item["txn_count"] >= 3
    assert item["monthly_cost"] > 0
