"""Parser unit tests — dirty Indian bank SMS formats.

Run from project root:  pytest tests/ -q
"""
from datetime import datetime

import pytest

from backend.parser import parse_sms

DEBIT_CASES = [
    # (sms, expected_amount, expected_merchant_hint, expected_date)
    ("Rs.1,250 debited from HDFC a/c XX4521 on 12-Mar-25 towards AMZPAY*1243. Ref 554212",
     1250.0, "amzpay", datetime(2025, 3, 12)),
    ("INR 499 debited on 03-Apr-25 to NETFLIX.COM. Avl Bal Rs.45,320",
     499.0, "netflix", datetime(2025, 4, 3)),
    ("Rs.18O00 debited on 01-May-25 toward RENT PAYMENT-LANDLORD",
     18000.0, "rent", datetime(2025, 5, 1)),
    ("Your HDFC card XX4821 used for Rs.85O at SWIGGY*NOODLEHOUSE on 2025-04-12 14:22",
     850.0, "swiggy", datetime(2025, 4, 12)),
    ("Rs.2,400 debited from HDFC a/c XX4521 on 15th Nov 25 for GOLDS GYM SUBSCRIPTION",
     2400.0, "gym", datetime(2025, 11, 15)),
    # regression: comma-less 4+ digit amounts must NOT be truncated to 3 digits
    ("Rs.12O0 debited on 03-Aug-25 to FLIPKART 9456. Avl Bal Rs.30,000",
     1200.0, "flipkart", datetime(2025, 8, 3)),
    ("Rs.1850 debited on 09-Sep-25 toward UBER TRIP HELP. Ref 234",
     1850.0, "uber", datetime(2025, 9, 9)),
]

CREDIT_CASES = [
    ("INR 65,O00 credited to your HDFC A/c XX4521 on 01-Apr-25 SALARY ABC TECH PVT LTD",
     65000.0, "salary", datetime(2025, 4, 1)),
    ("Rs.120 credited to your AXIS a/c XX4521 on 05-06-25 - CASHBACK AMAZON PAY. Avl Bal Rs.32,110",
     120.0, "cashback", datetime(2025, 6, 5)),
    # regression: comma-less salary amount must parse fully (was 650 instead of 65000)
    ("Rs. 65000 credited to your account on 01-Dec-23 SALARY ABC TECH PVT LTD. Ref 352153",
     65000.0, "salary", datetime(2023, 12, 1)),
]

NEGATIVE_CASES = [
    "",
    "   ",
    "Ref 441245 confirmed. Register for UPI today!",
    "Rs. debited from HDFC a/c on 12-Mar-25",
    "12-Mar-25 something random",
]


@pytest.mark.parametrize("sms,amount,hint,date", DEBIT_CASES)
def test_debit_parsing(sms, amount, hint, date):
    row = parse_sms(sms)
    assert row is not None, f"failed to parse: {sms}"
    assert row["direction"] == "debit"
    assert row["amount"] == pytest.approx(amount), sms
    assert hint in row["merchant"].lower(), f"merchant={row['merchant']!r}"
    assert row["txn_date"] == date, sms


@pytest.mark.parametrize("sms,amount,hint,date", CREDIT_CASES)
def test_credit_parsing(sms, amount, hint, date):
    row = parse_sms(sms)
    assert row is not None, f"failed to parse: {sms}"
    assert row["direction"] == "credit"
    assert row["amount"] == pytest.approx(amount)
    assert hint in row["merchant"].lower()
    assert row["txn_date"] == date


@pytest.mark.parametrize("sms", NEGATIVE_CASES)
def test_garbage_rejected(sms):
    assert parse_sms(sms) is None


def test_balance_captured_when_present():
    row = parse_sms("INR 499 debited on 03-Apr-25 to NETFLIX.COM. Avl Bal Rs.45,320")
    assert row["balance"] == pytest.approx(45320.0)


def test_missing_merchant_becomes_empty_for_cleaner_to_fill():
    row = parse_sms("Rs.450 debited on 09-Sep-25. Ref 112233")
    assert row is not None
    assert row["merchant"] == ""  # cleaner.py turns this into "Unknown"


# ------------------------------------------ real JioPay / BOB SMS formats ----
# These are the formats found in the project owner's actual SMS backup XML:
# bodies usually carry NO date (the SMS-Backup XML `date=` attribute does),
# so parse_sms takes an epoch-ms fallback parameter.

JIO_DEBIT = ("Your VPA 7620687415@ibl linked to your a/c no. XXXXXX5884 is debited "
             "for Rs. 250.0 and credited to VPA paytmqr2810050501b41 UPI Ref no 223421924524.")
BOB_DEBIT = ("Rs 5000.00 debited from A/C XXXXXX5884 and credited to "
             "sachinhiwale424-2@oksbi UPI Ref: 423424235643. -BOB")
BOB_TRANSFER = ("Rs.1 transferred from A/c ...5884 to:UPI/22909831341. "
                "Total Bal:Rs.30688.2CR. Avlbl Amt:Rs.30687.2(17-10-2022 18:24:50) - Bank of Baroda")
BOB_CREDIT_BY = "Rs.1 Credited to A/c ...5884 thru UPI/229098313411 by RSAL. Total Bal:Rs.30688.2CR."
BOB_CREDIT_DATED = ("Dear BOB UPI User, your account is credited INR 110.00 on Date "
                    "2025-05-13 01:46:30 PM by UPI Ref No 608234-B0B")
CASH_DEPOSIT = ("Rs.20000 deposited in cash to A/c ...5884. Total Bal:Rs.42052.1CR. "
                "Avlbl Amt:Rs.42052.1(04-08-2022 15:10:43) - Bank of Baroda")
BOB_SHORTHAND = ("Rs.200.00 Dr. from A/C XXXXXX5884 and Cr. to "
                 "bharatpe9p0x7j2o8b808173@yesbankltd. Ref:520336784725. "
                 "AvlBal:Rs37613.07(2025:07:22 06:30:56). Not you? Call 18001024455")

REAL_PROMOS = [
    "Your Rs.8850 welcome bonus is ready to be credited. Download Junglee Rummy now. "
    "Claim bonus: http://2lm.in/AsM2Oa",
    "Dear 7620687415, Amount of Rs.96,576 successfully transferred to your Rummy account "
    "on date 17-Jan. Withdraw Now. c3m.me/4aaub",
    "BIG BASKET has requested money through Google-pay. On approval, Rs 166.00 will be "
    "debited from your Bank Account-ICICI Bank.",
    "50% Data quota used as on 30-Jul-22 17:55. Balance Data : 2.93 GB Plan Name : MRP 61",
]


def test_jiopay_debit_uses_container_date_ms():
    row = parse_sms(JIO_DEBIT, 1698000000000)   # 2023-10-23 (IST)
    assert row is not None
    assert row["direction"] == "debit"
    assert row["amount"] == pytest.approx(250.0)
    assert "paytmqr" in row["merchant"].lower()
    assert row["txn_date"].strftime("%Y-%m-%d") == "2023-10-23"
    assert row["balance"] is None              # body has no balance


def test_bob_debit_to_digit_leading_vpa():
    body = ("Your VPA 7620687415@ibl linked a/c no. XXXXXX5884 is debited for Rs. 400.0 "
            "and credited to VPA 8668376143@ybl UPI Ref no 226642365464-BOB")
    row = parse_sms(body, 1750000000000)
    assert row is not None
    assert row["direction"] == "debit"
    assert "8668376143" in row["merchant"]     # payee captured, not "VPA ..."


def test_bob_debit_person_vpa():
    row = parse_sms(BOB_DEBIT, 1717000000000)
    assert row is not None
    assert row["direction"] == "debit"
    assert row["amount"] == pytest.approx(5000.0)
    assert "sachinhiwale" in row["merchant"].lower()


def test_bob_transfer_date_in_body_and_both_balances():
    row = parse_sms(BOB_TRANSFER)              # date inside the parens
    assert row is not None
    assert row["direction"] == "debit"
    assert row["amount"] == pytest.approx(1.0)
    assert row["txn_date"] == datetime(2022, 10, 17)
    assert row["balance"] == pytest.approx(30687.2)   # available, not total
    assert "transfer" in row["merchant"].lower()


def test_bob_credited_by_remitter():
    row = parse_sms(BOB_CREDIT_BY, 1698000000000)
    assert row is not None
    assert row["direction"] == "credit"
    assert row["merchant"].lower() == "rsal"
    assert row["txn_date"].strftime("%Y-%m-%d") == "2023-10-23"


def test_bob_credit_with_body_date():
    row = parse_sms(BOB_CREDIT_DATED)
    assert row is not None
    assert row["direction"] == "credit"
    assert row["amount"] == pytest.approx(110.0)
    assert row["txn_date"] == datetime(2025, 5, 13)


def test_cash_deposit_is_credit():
    row = parse_sms(CASH_DEPOSIT)
    assert row is not None
    assert row["direction"] == "credit"
    assert row["amount"] == pytest.approx(20000.0)
    assert row["balance"] == pytest.approx(42052.1)
    assert "cash deposit" in row["merchant"].lower()


def test_bob_shorthand_dr_cr_format():
    """2025+ BOB format: 'Rs.200.00 Dr. from A/C … Cr. to <vpa> … (2025:07:22 …)'."""
    row = parse_sms(BOB_SHORTHAND)
    assert row is not None
    assert row["direction"] == "debit"
    assert row["amount"] == pytest.approx(200.0)
    assert row["txn_date"].date() == datetime(2025, 7, 22).date()
    assert row["balance"] == pytest.approx(37613.07)     # AvlBal, comma-less
    assert "bharatpe" in row["merchant"].lower()


def test_no_date_and_no_container_ts_is_rejected():
    assert parse_sms(JIO_DEBIT) is None        # needs the XML timestamp


@pytest.mark.parametrize("sms", REAL_PROMOS)
def test_promo_and_mandate_requests_rejected(sms):
    # even WITH a container timestamp (which XML would provide) these are junk
    assert parse_sms(sms, 1750000000000) is None
