"""Chart payload analytics for the visualization layer.

One function -> one /api/charts response feeding: daily spend bars +
heatmap, category-by-month stacked bars, top merchants, month-end
forecast, auto-budget vs actual, and the cash-flow waterfall.

All JSON-serializable: dates are "YYYY-MM-DD" strings, no Timestamps.
"""
from __future__ import annotations

import pandas as pd

from backend.database import load_df

_MONTH_FMT = "%b %y"


def _fmt_period(m: pd.Period) -> str:
    return m.strftime(_MONTH_FMT)


def compute_chart_data() -> dict:
    df = load_df()
    if df.empty:
        return {"empty": True}

    df["txn_date"] = pd.to_datetime(df["txn_date"])
    df["day"] = df["txn_date"].dt.normalize()
    df["month"] = df["txn_date"].dt.to_period("M")

    debits = df[df["direction"] == "debit"]
    months_range = pd.period_range(df["month"].min(), df["month"].max(), freq="M")

    # ------------------------------------------------------- daily spend ----
    daily = (debits.groupby("day")["amount"]
             .agg(["sum", "count"])
             .reindex(pd.date_range(df["day"].min(), df["day"].max(), freq="D"),
                      fill_value=0.0)
             .rename(columns={"sum": "amount", "count": "txns"}))
    daily.index.name = "date"
    daily_series = [
        {"date": d.strftime("%Y-%m-%d"),
         "amount": round(float(r["amount"]), 2),
         "txns": int(r["txns"])}
        for d, r in daily.iterrows()
    ]
    # weekly buckets for the >500-point aggregation rule
    wk = (debits.groupby(pd.Grouper(key="day", freq="W"))["amount"]
          .agg(["sum", "count"]))
    weekly_series = [
        {"date": d.strftime("%Y-%m-%d"),
         "amount": round(float(r["sum"]), 2),
         "txns": int(r["count"])}
        for d, r in wk.iterrows()
    ]

    # ---------------------------------------------- category by month ------
    grp = debits.groupby(["month", "category"])["amount"].sum().reset_index()
    top_cats = grp.groupby("category")["amount"].sum().nlargest(6).index.tolist()
    grp["cat2"] = grp["category"].where(grp["category"].isin(top_cats), "Other")
    piv = grp.pivot_table(index="month", columns="cat2", values="amount",
                          aggfunc="sum").reindex(months_range, fill_value=0.0)
    # pivot_table leaves NaN where a category had no txns in a month — that
    # would become literal `NaN` in the JSON response (invalid for JS), so fill
    piv = piv.fillna(0.0)
    # keep a stable order: top cats (desc) then Other last
    cat_totals = grp.groupby("cat2")["amount"].sum().sort_values(ascending=False)
    ordered_cols = [c for c in cat_totals.index if c != "Other"] + \
                   (["Other"] if "Other" in cat_totals.index else [])
    piv = piv[ordered_cols]
    category_months = {
        "months": [_fmt_period(m) for m in months_range],
        "categories": [str(c) for c in piv.columns],
        "series": {str(c): [round(float(v), 2) for v in piv[c]] for c in piv.columns},
    }

    # ------------------------------------------------------ merchants ------
    mg = debits.groupby("merchant")["amount"].agg(["sum", "count"]) \
        .sort_values("sum", ascending=False).head(10)
    merchants = [
        {"merchant": str(m), "amount": round(float(r["sum"]), 2), "txns": int(r["count"])}
        for m, r in mg.iterrows()
    ]

    # --------------------------------------------- forecast (current mo) ----
    last_day = df["day"].max()
    m0 = last_day.to_period("M")
    month_days = pd.date_range(m0.start_time, m0.end_time, freq="D")
    cur = debits[debits["month"] == m0].groupby("day")["amount"].sum() \
        .reindex(month_days, fill_value=0.0)
    cumulative = cur.cumsum()
    forecast = {
        "month_label": _fmt_period(m0),
        "dates": [d.strftime("%Y-%m-%d") for d in cumulative.index],
        "cumulative": [round(float(v), 2) for v in cumulative],
        "days_in_month": len(month_days),
        "days_elapsed": int(cur.index.get_loc(last_day)) + 1,
        "month_days": len(month_days),
        "spent_so_far": round(float(cumulative.iloc[-1]), 2),
        "avg_daily": round(float(cumulative.iloc[-1]) / (cur.index.get_loc(last_day) + 1), 2),
        "projected_end": round(float(cumulative.iloc[-1]) * len(month_days) / (cur.index.get_loc(last_day) + 1), 2),
    }

    # ------------------------------------------------ budget vs actual -----
    full_months = months_range[:-1] if len(months_range) >= 2 else months_range
    base = debits[debits["month"].isin(full_months[-3:])]
    budget_m = base.groupby("category")["amount"].median()
    actual_m = debits[debits["month"] == m0].groupby("category")["amount"].sum()
    budgets = []
    for cat in sorted(set(budget_m.index) | set(actual_m.index)):
        b = float(budget_m.get(cat, 0.0))
        a = float(actual_m.get(cat, 0.0))
        state = "exceeded" if a > b else ("approaching" if a > b * 0.85 else "within")
        icon = {"within": "✔", "approaching": "△", "exceeded": "✖"}[state]
        budgets.append({"category": str(cat), "budget": round(b, 2),
                        "actual": round(a, 2), "state": state, "icon": icon})
    budgets.sort(key=lambda x: -x["actual"])

    # -------------------------------------------------------- waterfall ----
    w0 = full_months[-3] if len(full_months) >= 3 else full_months[0]
    win_start = w0.start_time
    opening = float(df[df["txn_date"] < win_start]
                    .assign(s=df["direction"].map({"credit": 1, "debit": -1}) * df["amount"])["s"].sum()) \
        if (df["txn_date"] < win_start).any() else 0.0
    w_income = round(float(df[(df["txn_date"] >= win_start)]["direction"].eq("credit").mul(
        df.loc[df["txn_date"] >= win_start, "amount"]).sum()), 2)
    w_spend = round(float(df[(df["txn_date"] >= win_start)]["direction"].eq("debit").mul(
        df.loc[df["txn_date"] >= win_start, "amount"]).sum()), 2)
    waterfall = {
        "window": f"{_fmt_period(w0)} – {df['month'].max().strftime(_MONTH_FMT)}",
        "opening": round(opening, 2),
        "income": w_income,
        "expenses": w_spend,
        "net": round(opening + w_income - w_spend, 2),
        "txn_count": int((df["txn_date"] >= win_start).sum()),
    }

    return {
        "empty": False,
        "daily": daily_series,
        "weekly": weekly_series,
        "category_months": category_months,
        "merchants": merchants,
        "forecast": forecast,
        "budgets": budgets,
        "waterfall": waterfall,
    }


def compute_aria_summary(daily_slice: list[dict]) -> str:
    """Tiny helper for a11y summaries on the daily chart."""
    if len(daily_slice) < 2:
        return "Not enough daily data yet."
    vals = [d["amount"] for d in daily_slice]
    avg = sum(vals) / len(vals)
    spike = max(range(len(vals)), key=vals.__getitem__)
    return (f"Daily spend averaged {round(avg)} per day over {len(vals)} days; "
            f"highest was {round(vals[spike])} on {daily_slice[spike]['date']}.")
