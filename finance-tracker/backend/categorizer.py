"""Transparent keyword rule engine: merchant text -> spending category.

Rules are kept in one dictionary so students can read/extend them easily
(good viva material: "classification is explainable, not a black box").
"""
from __future__ import annotations

# keyword (lowercase substring) -> category
RULES: dict[str, str] = {
    # Food & Dining
    "swiggy": "Food & Dining",
    "zomato": "Food & Dining",
    "domino": "Food & Dining",
    "restaurant": "Food & Dining",
    "cafe": "Food & Dining",
    "starbucks": "Food & Dining",
    "chayos": "Food & Dining",
    "haldiram": "Food & Dining",
    "haldirams": "Food & Dining",
    # Groceries
    "blinkit": "Groceries",
    "zepto": "Groceries",
    "bigbasket": "Groceries",
    "dmart": "Groceries",
    "grocery": "Groceries",
    "kirana": "Groceries",
    # Subscriptions
    "netflix": "Subscriptions",
    "spotify": "Subscriptions",
    "prime video": "Subscriptions",
    "primevideo": "Subscriptions",
    "hotstar": "Subscriptions",
    "youtube": "Subscriptions",
    "adobe": "Subscriptions",
    "canonical": "Subscriptions",
    # Transport & Fuel
    "uber": "Transport & Fuel",
    "ola ": "Transport & Fuel",
    "rapido": "Transport & Fuel",
    "petrol": "Transport & Fuel",
    "fuel": "Transport & Fuel",
    "irctc": "Transport & Fuel",
    "metro": "Transport & Fuel",
    "parking": "Transport & Fuel",
    # Utilities & Phone
    "airtel": "Utilities & Phone",
    "jio ": "Utilities & Phone",
    "vodafone": "Utilities & Phone",
    "bescom": "Utilities & Phone",
    "electricity": "Utilities & Phone",
    "gas": "Utilities & Phone",
    "wifi": "Utilities & Phone",
    "broadband": "Utilities & Phone",
    # Rent & Housing
    "rent": "Rent & Housing",
    "landlord": "Rent & Housing",
    "maintenance": "Rent & Housing",
    # Debt & Loans
    "emi": "Debt & Loans",
    "loan": "Debt & Loans",
    "bikesloan": "Debt & Loans",
    "credit card payment": "Debt & Loans",
    # Health
    "pharmacy": "Health",
    "apollo": "Health",
    "hospital": "Health",
    "gym": "Health & Fitness",
    "fitness": "Health & Fitness",
    "cult.fit": "Health & Fitness",
    # Shopping
    "amazon": "Shopping",
    "amzpay": "Shopping",
    "flipkart": "Shopping",
    "myntra": "Shopping",
    "croma": "Shopping",
    "dmart ready": "Shopping",
    # Entertainment
    "bookmyshow": "Entertainment",
    "pvr": "Entertainment",
    "inox": "Entertainment",
    "cinema": "Entertainment",
    # Education
    "udemy": "Education",
    "coursera": "Education",
    "course": "Education",
    "exam fee": "Education",
    # Real-bank merchants (JioPay UPI / Bank of Baroda dumps)
    "paytm": "Shopping",          # Paytm QR / Paytm UPI purchases
    "jio recharge": "Utilities & Phone",
}


def categorize(merchant: str, direction: str) -> str:
    """Assign a category from merchant text + transaction direction."""
    m = (merchant or "").lower()
    if direction == "credit":
        if "cashback" in m:
            return "Income"
        if "interest" in m:
            return "Income"
        return "Income"
    if not m or m == "unknown":
        return "Uncategorized"
    for keyword, category in RULES.items():
        if keyword in m:
            return category
    return "Others"


def categorize_rows(rows: list[dict]) -> list[dict]:
    """Add a 'category' key to each parsed row (mutates copies)."""
    out = []
    for r in rows:
        r = dict(r)
        r["category"] = categorize(r.get("merchant", ""), r.get("direction", "debit"))
        out.append(r)
    return out
