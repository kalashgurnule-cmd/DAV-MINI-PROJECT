"""Shared pytest fixtures for the finance-tracker test suite."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    """Point the app's DB handle at a throwaway file so pipeline tests never
    touch the developer's real finance.db."""
    import backend.database as db
    uri = f"sqlite:///{(tmp_path / 'test_finance.db').as_posix()}"
    engine = create_engine(uri, future=True)
    monkeypatch.setattr(db, "_ENGINE", engine)
    monkeypatch.setattr(db, "_Session",
                        sessionmaker(bind=engine, expire_on_commit=False, future=True))
    db.init_db()
    return db
