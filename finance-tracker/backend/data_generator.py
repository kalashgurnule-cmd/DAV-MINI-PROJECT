"""Synthetic "dirty" bank SMS generator.

Produces ~3 years of realistic Indian bank SMS messages FULL of deliberate
data-quality problems (the whole project demonstrates cleaning them):

  noise planted on purpose
  ------------------------
  * mixed currency styles: Rs / Rs. / INR / Rs.
  * letter-O for zero: "8O0", "18O00" etc.
  * 5 different date formats (12-Mar-25, 03/04/25, 2025-04-12, 15th Nov 25, ...)
  * exact duplicate SMS (~2%)
  * missing merchant (~3%, uses a dedicated no-merchant SMS template)
  * inconsistent spacing/caps, phone codes in merchant ("SWIGGY*NOODLEHOUSE")
  * occasionally missing balance

Real-life roles baked in so the analytics have something to find:
  * monthly salary credit 65k, rent debit 18k, bike EMI 4.8k (Debt metrics)
  * forgotten "zombie" subscriptions every month: Gold's Gym 2400,
    Netflix 499, Spotify 119, plus ONE yearly zombie: Prime Video 1499
  * everyday variable spends (food, groceries, fuel, transport...)

Price model (so Personal Inflation has recoverable ground truth):
  amount = BASE_PRICE[merchant] * small_cart_jitter(0.88-1.18) * month_drift
  where month_drift = 1 + 5.5%/year * months_elapsed  (engineered inflation).
  Base prices are kept within a narrow band inside each BASKET category
  (Food & Dining / Groceries) so a category's monthly median tracks the
  PRICE level, not a random composition of differently-priced merchants.
  Transport & Fuel intentionally mixes cheap rides with rail/fuel tickets:
  it is excluded from the index basket and documented as a composition.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta

from faker import Faker

import config

fake = Faker("en_IN")

# engineered micro-inflation: variable spends grow ~+5.5%/year
ANNUAL_DRIFT = 0.055

_CART_JITTER = (0.90, 1.12)   # small cart-size variation around base price


def _shift_months(dt: datetime, n: int) -> datetime:
    """dt shifted back n months, day=1."""
    y, m = dt.year, dt.month - n
    while m <= 0:
        m += 12
        y -= 1
    return dt.replace(year=y, month=m, day=1, hour=9, minute=0)


# ----------------------------------------------------------------- noise helpers
def _currency_style(rng: random.Random) -> str:
    return rng.choice(["Rs.", "Rs ", "INR ", "₹", "Rs. ", "INR"])


def _amount_str(amount: float, rng: random.Random) -> str:
    """Format amount, sometimes with commas, sometimes with an O-for-0 typo."""
    s = f"{amount:.0f}" if amount == int(amount) else f"{amount:.2f}"
    whole = s.split(".")[0]
    if rng.random() < 0.5 and len(whole) >= 3:
        whole = f"{int(whole.replace(',', '')):,}"
    s = whole + ("." + s.split(".")[1] if "." in s else "")
    if rng.random() < 0.08 and "0" in s:            # plant the classic 'O' typo
        s = s.replace("0", "O", 1)
    return s


def _date(rng: random.Random, dt: datetime) -> str:
    """Render date in one of the parser-supported formats."""
    ordinal = {1: "st", 2: "nd", 3: "rd"}.get(dt.day, "th")
    options = [
        dt.strftime("%d-%b-%y"),
        dt.strftime("%d-%m-%y"),
        dt.strftime("%Y-%m-%d"),
        f"{dt.day}{ordinal} {dt.strftime('%b %y')}",
        dt.strftime("%d/%m/%y"),
    ]
    return rng.choice(options)


# ----------------------------------------------------------------- SMS builders
def _sms_debit(rng, dt, amount, merchant, bank, acct, with_balance):
    amt = _amount_str(amount, rng)
    date_str = _date(rng, dt)
    bal = f" Avl Bal Rs.{int(rng.uniform(5_000, 90_000)):,}" if with_balance else ""
    if not merchant:  # missing-merchant noise: dedicated template
        return (f"{_currency_style(rng)}{amt} debited on {date_str}. "
                f"Ref {rng.randint(100000, 999999)}{bal}")
    m = merchant
    templates = [
        f"{_currency_style(rng)}{amt} debited from {bank} a/c {acct} on {date_str} towards {m}. Ref {rng.randint(100000, 999999)}{bal}",
        f"{_currency_style(rng)}{amt} debited on {date_str} to {m}. Avl Bal Rs{int(rng.uniform(5_000, 90_000)):,}",
        f"₹{amt} debited from {bank} A/c {acct} on {date_str} for {m}{bal}",
        f"Your {bank} card {acct} used for {_currency_style(rng)}{amt} at {m} on {date_str}{bal}",
        f"{_currency_style(rng)} {amt} debited on {date_str} toward {m} Ref{rng.randint(100000, 999999)}{bal}",
    ]
    return rng.choice(templates)


def _sms_credit(rng, dt, amount, trade, bank, acct, with_balance):
    amt = _amount_str(amount, rng)
    date_str = _date(rng, dt)
    bal = f" Avl Bal Rs.{int(rng.uniform(20_000, 1_40_000)):,}" if with_balance else ""
    if "cashback" in trade.lower():
        templates = [
            f"{_currency_style(rng)}{amt} credited to your {bank} a/c {acct} on {date_str} - CASHBACK {trade}{bal}",
            f"INR {amt} credited to your account on {date_str}. Reason: {trade}{bal}",
        ]
    else:
        templates = [
            f"INR {amt} credited to your {bank} A/c {acct} on {date_str} {trade}{bal}",
            f"{_currency_style(rng)}{amt} credited to your account on {date_str} {trade}. Ref {rng.randint(100000, 999999)}{bal}",
        ]
    return rng.choice(templates)


# ----------------------------------------------------------------- main
def generate_sms(seed: int = config.SEED, months: int = config.DATA_MONTHS) -> list[str]:
    """Return raw (dirty) SMS strings spanning `months` months ending THIS month."""
    rng = random.Random(seed)
    fake.seed_instance(seed)

    bank = rng.choice(["HDFC", "SBI", "ICICI", "Axis"])
    acct = f"XX{rng.randint(1000, 9999)}"
    salary = 65_000.0
    rent = 18_000.0
    emi = 4_800.0
    salary_trader = "SALARY ABC TECH PVT LTD"

    recurring_day = {          # reliable auto-debits (some are zombies!)
        "GOLDS GYM SUBSCRIPTION": 7,
        "NETFLIX.COM": 4,
        "SPOTIFY INDIA": 11,
        "BIKESLOAN EMI": 5,
        "AIRTEL POSTPAID": 18,
        "BESCOM ELECTRICITY": 22,
        "PRIMEVIDEO SUBSCRIPTION": 9,   # yearly!
    }
    recurring_amount = {
        "GOLDS GYM SUBSCRIPTION": 2_400.0,
        "NETFLIX.COM": 499.0,
        "SPOTIFY INDIA": 119.0,
        "BIKESLOAN EMI": 4_800.0,
        "BESCOM ELECTRICITY": None,          # random each month
        "AIRTEL POSTPAID": None,
    }

    # base price per merchant (INR). The inflation basket categories use ONE
    # category-level base so the monthly median tracks the PRICE level, not a
    # random composition of differently-priced merchants (composition noise
    # would drown the drift). Cart size still jitters +-15% per transaction.
    # Non-basket categories may vary freely.
    BASE_PRICE = {
        # Food & Dining — homogeneous base 250
        "SWIGGY": 250, "ZOMATO": 250, "DOMINOS": 250, "STARBUCKS": 250,
        "HALDIRAMS": 250, "CAFE": 250,
        # Groceries — homogeneous base 480
        "BLINKIT": 480, "ZEPTO": 480, "DMART": 480, "BIGBASKET": 480,
        # everything else (not in the inflation basket)
        "AMZPAY": 700, "FLIPKART": 1200, "MYNTRA": 1000,
        "UBER": 140, "OLA": 110, "RAPIDO": 70, "PETROL": 850, "IRCTC": 900,
        "APOLLO": 350, "HOSPITAL": 900, "BOOKMYSHOW": 350, "PVR": 320,
        "UDEMY": 549, "INDANE": 900, "GENERAL": 280, "SALOON": 380,
        "STATIONERY": 120,
    }
    variable_merchants = [
        # food & grocery appear more often (people order food a lot) ->
        # higher basket sample counts for the inflation index
        "SWIGGY*NOODLEHOUSE", "SWIGGY*BIRYANI BLUES", "SWIGGY*DRAGON WOK",
        "SWIGGY*IDLI COMPANY", "ZOMATO*PIZZA POINT", "ZOMATO*CHAYOS 945",
        "ZOMATO*BURGER FARM", "ZOMATO*WAFFLE WAALA", "DOMINOS PIZZA 789",
        "STARBUCKS COFFEE 112", "HALDIRAMS RESTAURANT", "CAFE COFFEE DAY 31",
        "BLINKIT GROCERY 4421", "BLINKIT GROCERY 9002", "BLINKIT GROCERY 2210",
        "ZEPTO GROCERY 1123", "ZEPTO GROCERY 4410", "DMART READY BTM",
        "BIGBASKET GROCERY",
        "AMZPAY*1243", "FLIPKART 9456", "MYNTRA 3321", "UBER TRIP HELP.MBI",
        "OLA CABS BLR", "RAPIDO BIKE TAXI", "PETROL PUMP HP CLUBLINK",
        "IRCTC RAIL TICKET", "APOLLO PHARMACY 3456", "HOSPITAL CASH COUNTER",
        "BOOKMYSHOW CINE 22", "PVR CINEMAS BLR",
        "UDEMY COURSE FEE", "INDANE GAS AGENCY", "GENERAL MERCHANT STORE",
        "SALOON & SPA 22", "STATIONERY SHOP 90",
    ]

    today = datetime.now()
    start = _shift_months(today, months - 1)          # ends at current month
    out: list[str] = []

    cur = start.replace(day=1)
    months_elapsed = 0
    while cur <= today.replace(day=1, hour=9):
        month_first = cur.replace(day=1)
        days_in_month = ((cur + timedelta(days=31)).replace(day=1) - month_first).days
        # spend this month with the engineered drift factor
        drift = 1 + ANNUAL_DRIFT * (months_elapsed / 12.0)

        # --- monthly salary (day 1, tiny variation) ---
        out.append(_sms_credit(rng, month_first, salary + rng.choice([0, 0, 1500, -800]),
                               salary_trader, bank, acct, with_balance=rng.random() < 0.8))

        # --- reliable recurring debits ---
        for merchant, day in recurring_day.items():
            if merchant == "PRIMEVIDEO SUBSCRIPTION":      # yearly zombie in July
                if cur.month != 7:
                    continue
                amount = 1_499.0
            elif recurring_amount[merchant] is None:
                amount = (900 + float(rng.randint(0, 800)) if merchant == "BESCOM ELECTRICITY"
                          else 599.0 + rng.choice([0, 0, 0, 50]))
            else:
                amount = recurring_amount[merchant]
            dt = month_first + timedelta(days=min(day - 1, days_in_month - 1))
            if dt > today:                                  # never print future SMS
                continue
            out.append(_sms_debit(rng, dt, amount, merchant, bank, acct,
                                  with_balance=rng.random() < 0.7))

        # --- rent (day 5) ---
        dt_rent = month_first + timedelta(days=4)
        if dt_rent <= today:
            out.append(_sms_debit(rng, dt_rent, rent, "RENT PAYMENT-LANDLORD", bank, acct,
                                  with_balance=rng.random() < 0.6))

        # --- variable spends, capped at today for the current month ---
        end_of_span = min(month_first + timedelta(days=days_in_month), today)
        d = month_first
        while d < end_of_span:
            n_txns = rng.choices([0, 1, 2, 3, 4], weights=[16, 36, 28, 13, 7])[0]
            if d.weekday() >= 5:
                n_txns = rng.choices([0, 1, 2, 3], weights=[14, 38, 32, 16])[0]
            for _ in range(n_txns):
                merchant = rng.choice(variable_merchants)
                base = BASE_PRICE[merchant.upper().split("*")[0].split(" ")[0]]
                jitter = rng.uniform(*_CART_JITTER)
                amount = round(base * jitter * drift) + rng.choice([0, 0, 0, 0.5, 0.9])
                dt = d + timedelta(hours=rng.randint(8, 22), minutes=rng.randint(0, 59))
                # sometimes merchant is missing entirely (dirty!)
                merchant_out = merchant if rng.random() > 0.03 else ""
                out.append(_sms_debit(rng, dt, amount, merchant_out, bank, acct,
                                      with_balance=rng.random() < 0.55))
            d += timedelta(days=1)

        # --- occasional cashback credit (spiky noise on income) ---
        for _ in range(rng.randint(0, 2)):
            if end_of_span > month_first:
                dt = month_first + timedelta(days=rng.randint(1, days_in_month - 1))
                dt = min(dt, end_of_span - timedelta(hours=1))
                cb = float(rng.choice([25, 50, 87, 120, 250]))
                out.append(_sms_credit(rng, dt, cb, "CASHBACK AMAZON PAY", bank, acct,
                                       with_balance=True))

        # advance month
        months_elapsed += 1
        cur = month_first + timedelta(days=days_in_month)

    # --- exact duplicates (~2%) ---
    dup_count = int(len(out) * 0.02)
    for src in rng.sample(out, dup_count):
        out.append(src)

    rng.shuffle(out)
    return out
