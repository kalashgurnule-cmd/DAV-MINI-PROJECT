"""Financial Health Score — weighted composite of five DAV-friendly components.

    Savings Rate   30%   (income - spend) / income
    Cash Runway    20%   months you survive if income stops today
    Debt Pressure  20%   Debt & Loans debits / income (lower is better)
    Zombie Drain   15%   active subscription drain / income (lower is better)
    Volatility     15%   coefficient of variation of monthly spend (impulse proxy)

Each raw metric is normalized to 0-100 with transparent linear maps so the
whole score is explainable (key viva talking point!).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from backend.analytics.overview import compute_overview
from backend.analytics.zombies import compute_zombies


def _fmt_inr(x: float) -> str:
    return f"₹{x:,.0f}"


def compute_health_score_with_debt(df_ledger: pd.DataFrame) -> dict:
    """Main entry point — pass the raw transactions DataFrame from the DB."""
    ov = compute_overview()
    if ov.get("empty"):
        return {"empty": True}

    income = sum(ov["income"]) or 1.0
    net = sum(ov["net"])
    avg_spend = sum(ov["spend"]) / max(1, len(ov["spend"]))

    zombies = compute_zombies()
    active_annual = (zombies.get("active_annual_drain", 0.0)
                     if not zombies.get("empty") else 0.0)

    debt_total = 0.0
    if df_ledger is not None and len(df_ledger) and "category" in df_ledger:
        debt_total = float(df_ledger.loc[df_ledger["category"] == "Debt & Loans", "amount"].sum())

    return _score(net, income, avg_spend, active_annual, ov, debt_total)


def _score(net: float, income: float, avg_spend: float,
           active_annual: float, ov: dict, debt_total: float | None) -> dict:
    # ---- component 1: savings ----
    savings_rate = net / income                      # 0..1
    s_savings = min(100.0, max(0.0, savings_rate / 0.30 * 100))

    # ---- component 2: runway ----
    runway_months = (net / avg_spend) if avg_spend > 0 else 0.0
    s_runway = min(100.0, max(0.0, runway_months / 6 * 100))

    # ---- component 3: debt pressure (no debt data -> neutral 100) ----
    debt_ratio = (debt_total / income) if debt_total is not None else 0.0
    s_debt = max(0.0, 100.0 - min(1.2, debt_ratio / 0.35) * 100)

    # ---- component 4: zombie drain ----
    zombie_ratio = active_annual / income
    s_zombie = max(0.0, 100.0 - min(1.2, zombie_ratio / 0.10) * 100)

    # ---- component 5: volatility ----
    spend = np.array(ov["spend"], dtype=float)
    cv = float(spend.std() / spend.mean()) if spend.mean() > 0 else 0.0
    s_vol = max(0.0, 100.0 - cv * 200)

    total = round(
        s_savings * 0.30 + s_runway * 0.20 + s_debt * 0.20 + s_zombie * 0.15 + s_vol * 0.15
    )

    grade = ("Excellent" if total >= 80 else
             "Good" if total >= 60 else
             "Fair" if total >= 40 else "Needs Attention")

    components = [
        {"name": "Savings Rate", "weight": 30, "score": round(s_savings),
         "raw": f"{savings_rate * 100:.1f}% saved"},
        {"name": "Cash Runway", "weight": 20, "score": round(s_runway),
         "raw": f"{runway_months:.1f} months of buffer"},
        {"name": "Debt Pressure", "weight": 20, "score": round(s_debt),
         "raw": f"{debt_ratio * 100:.1f}% of income on EMIs"},
        {"name": "Zombie Drain", "weight": 15, "score": round(s_zombie),
         "raw": f"{_fmt_inr(active_annual)}/yr on forgotten subscriptions"},
        {"name": "Spend Volatility", "weight": 15, "score": round(s_vol),
         "raw": f"CV {cv:.2f} (impulse proxy)"},
    ]

    # ---- dynamic, honest suggestions ----
    suggestions: list[str] = []
    if zombie_ratio > 0.02:
        suggestions.append(
            f"You're paying {_fmt_inr(active_annual)}/year to subscriptions you likely forgot — cancel the oldest active ones first.")
    if debt_ratio > 0.25:
        suggestions.append("EMI pressure is high: prepaying even one month of principal shortens the loan visibly.")
    if savings_rate < 0.15:
        suggestions.append("Savings rate under 15%: automate a standing transfer on salary day before spending starts.")
    if cv > 0.35:
        suggestions.append("Spend is spiky month to month — a weekly budget cap usually flattens this fast.")
    if runway_months < 3:
        suggestions.append("Cash runway under 3 months: build an emergency fund of 3 months' expenses as priority #1.")
    if not suggestions:
        suggestions.append("All ratios look healthy. Review the zombie list quarterly — dead subscriptions creep back.")

    return {"empty": False, "score": total, "grade": grade, "components": components,
            "suggestions": suggestions}
