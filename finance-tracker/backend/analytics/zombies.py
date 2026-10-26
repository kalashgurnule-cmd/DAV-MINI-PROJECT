"""Subscription Zombie Detector.

Algorithm (time-series gap analysis):
  1. group debit transactions by merchant
  2. keep merchants with >= 3 debits
  3. inter-transaction interval (days); if median interval ~ monthly
     (26-37 d) -> 'monthly'; ~ yearly (340-380 d) -> 'yearly'
  4. recompute last_seen vs the expected cycle
  5. status: 'active'  -> it is STILL charging you (last seen within 1.6 cycles)
             'dormant' -> stopped (but watch out for auto-debit revival)
  6. rank by annualized cost, active first

Scope note: only *forgotten-charge risk* categories are surfaced as zombies
(Subscriptions, Health & Fitness). Rent, EMIs and utility bills are also
recurring — but they are deliberate commitments, so they are counted in
'other_recurring' instead of alarming the user.
"""
from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd

from backend.database import load_df

_MONTHLY = (26, 37)
_YEARLY = (340, 380)
_ZOMBIE_RISK_CATEGORIES = {"Subscriptions", "Health & Fitness"}


def compute_zombies() -> dict:
    df = load_df()
    if df.empty:
        return {"empty": True}

    df["txn_date"] = pd.to_datetime(df["txn_date"])
    ref_date = df["txn_date"].max()  # freeze "now" to the latest datum for stability
    df = df[df["direction"] == "debit"]

    items: list[dict] = []
    other_recurring: list[str] = []
    for merchant, g in df.groupby("merchant"):
        if len(g) < 3 or merchant == "Unknown":
            continue
        dates = sorted(g["txn_date"].tolist())
        diffs = np.diff([d.value // 86_400_000_000_000 for d in dates]).astype(float)  # days

        med = float(np.median(diffs))
        freq = None
        interval_days = None
        if _MONTHLY[0] <= med <= _MONTHLY[1]:
            freq, interval_days = "monthly", med
        elif _YEARLY[0] <= med <= _YEARLY[1]:
            freq, interval_days = "yearly", med
        if freq is None:
            continue

        amounts = g["amount"].tolist()
        median_amt = float(np.median(amounts))
        monthly_cost = median_amt if freq == "monthly" else median_amt / 12.0
        annualized = monthly_cost * 12.0
        lifetime = float(sum(amounts))

        last_seen = dates[-1]
        last_seen_days = (ref_date - last_seen).days
        active = last_seen_days <= interval_days * 1.6 + 15
        status = "active" if active else "dormant"

        item = {
            "merchant": str(g["merchant"].iloc[0]),
            "category": str(g["category"].iloc[0]),
            "frequency": freq,
            "interval_days": round(med, 1),
            "txn_count": int(len(g)),
            "monthly_cost": round(monthly_cost, 2),
            "annualized": round(annualized, 2),
            "lifetime_spend": round(lifetime, 2),
            "first_seen": dates[0].strftime("%b %y"),
            "last_seen": last_seen.strftime("%d %b %y"),
            "last_seen_days": int(last_seen_days),
            "status": status,
        }
        if item["category"] in _ZOMBIE_RISK_CATEGORIES:
            items.append(item)
        else:
            other_recurring.append(f"{item['merchant']} ({item['frequency']})")

    items.sort(key=lambda x: (x["status"] != "active", -x["annualized"]))
    active_monthly = round(sum(i["monthly_cost"] for i in items if i["status"] == "active"), 2)
    dormant = [i for i in items if i["status"] == "dormant"]

    return {
        "empty": False,
        "items": items,
        "active_monthly_drain": active_monthly,
        "active_annual_drain": round(active_monthly * 12, 2),
        "dormant_names": [i["merchant"] for i in dormant],
        "other_recurring": other_recurring[:8],
        "count": len(items),
    }
