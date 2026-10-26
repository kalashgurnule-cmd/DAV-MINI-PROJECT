"""SQLAlchemy models + session helpers (SQLite storage layer).

Ties directly to DAV Practical 5 concepts: pandas <-> SQL persistence
(sqlite3 / SQLAlchemy / to_sql / read_sql).
"""
from pathlib import Path

import pandas as pd
from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

import config


class Base(DeclarativeBase):
    pass


class Transaction(Base):
    """One parsed + cleaned financial event (debit or credit)."""

    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    txn_date = Column(DateTime, nullable=False, index=True)
    direction = Column(String(10), nullable=False, index=True)   # debit | credit
    amount = Column(Float, nullable=False)
    merchant = Column(String(120), nullable=False, index=True)
    category = Column(String(40), nullable=False, index=True)
    balance = Column(Float, nullable=True)                       # running balance, if SMS had it
    raw_text = Column(Text, nullable=True)                       # original SMS (synthetic)
    source = Column(String(10), nullable=False, default="sms")   # sms | csv
    created_at = Column(DateTime, nullable=True)

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "date": self.txn_date.strftime("%Y-%m-%d"),
            "direction": self.direction,
            "amount": round(self.amount, 2),
            "merchant": self.merchant,
            "category": self.category,
            "balance": round(self.balance, 2) if self.balance is not None else None,
            "source": self.source,
            "raw_text": (self.raw_text or ""),
        }


_ENGINE = create_engine(config.SQLALCHEMY_URI, future=True)
_Session = sessionmaker(bind=_ENGINE, expire_on_commit=False, future=True)


def init_db() -> None:
    """Create tables if they do not exist."""
    Path(config.DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(_ENGINE)


def reset_db() -> None:
    """Drop all rows (used by the 'regenerate data' button)."""
    init_db()
    with _Session() as s:  # type: Session
        s.query(Transaction).delete()
        s.commit()


def insert_rows(rows: list[dict]) -> int:
    """Bulk insert cleaned transaction dicts. Returns count."""
    if not rows:
        return 0
    init_db()
    objs = [Transaction(**r) for r in rows]
    with _Session() as s:  # type: Session
        s.add_all(objs)
        s.commit()
    return len(objs)


def load_df() -> pd.DataFrame:
    """Whole table as a pandas DataFrame (one-shot; data is tiny)."""
    init_db()
    return pd.read_sql("SELECT * FROM transactions", _ENGINE)


def dup_keys() -> set[tuple]:
    """(date, direction, amount, merchant) keys of everything stored —
    seed.py uses this to skip re-storing identical transactions."""
    init_db()
    with _Session() as s:  # type: Session
        rows = s.query(Transaction.txn_date, Transaction.direction,
                       Transaction.amount, Transaction.merchant).all()
    return {(t.strftime("%Y-%m-%d"), d, round(a, 2), m) for t, d, a, m in rows}


def row_count() -> int:
    init_db()
    with _Session() as s:  # type: Session
        return s.query(Transaction).count()
