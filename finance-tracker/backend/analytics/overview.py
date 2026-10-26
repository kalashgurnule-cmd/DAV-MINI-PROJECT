"""Overview analytics: monthly income / spend / net, KPIs, category table."""
from __future__ import annotations

import pandas as pd

from backend.database import load_df

_MONTH_FMT = "%b %y"


def compute_overview() -> dict:
    df = load_df()
    if df.empty:
        return {"empty": True}

    df["txn_date"] = pd.to_datetime(df["txn_date"])
    df["month"] = df["txn_date"].dt.to_period("M")

    credits = df[df["direction"] == "credit"].groupby("month")["amount"].sum()
    debits = df[df["direction"] == "debit"].groupby("month")["amount"].sum()
    months_range = pd.period_range(df["month"].min(), df["month"].max(), freq="M")

    income = [round(float(credits.get(m, 0.0)), 2) for m in months_range]
    spend = [round(float(debits.get(m, 0.0)), 2) for m in months_range]
    net = [round(i - s, 2) for i, s in zip(income, spend)]
    month_labels = [m.strftime(_MONTH_FMT) for m in months_range]

    total_income = float(sum(income))
    total_spend = float(sum(spend))
    balance = round(total_income - total_spend, 2)
    savings_rate = round((total_income - total_spend) / total_income * 100, 1) if total_income else 0.0

    last_month = months_range[-1]
    prev_month = months_range[-2] if len(months_range) >= 2 else last_month

    cur = df[(df["month"] == last_month) & (df["direction"] == "debit")].groupby("category")["amount"].sum()
    prv = df[(df["month"] == prev_month) & (df["direction"] == "debit")].groupby("category")["amount"].sum()
    categories = []
    for cat, amt in cur.sort_values(ascending=False).items():
        prv_amt = float(prv.get(cat, 0.0))
        change = ((float(amt) - prv_amt) / prv_amt * 100) if prv_amt else None
        categories.append({
            "name": str(cat),
            "amount": round(float(amt), 2),
            "change_pct": None if change is None else round(change, 1),
        })

    return {
        "empty": False,
        "months": month_labels,
        "income": income,
        "spend": spend,
        "net": net,
        "balance": balance,
        "savings_rate": savings_rate,
        "month_spend": round(float(spend[-1]), 2) if spend else 0.0,
        "prev_month_spend": round(float(spend[-2]) if len(spend) >= 2 else 0.0, 2),
        "month_label": month_labels[-1] if month_labels else "",
        "categories_current": categories,
        "txn_count": int(len(df)),
    }
