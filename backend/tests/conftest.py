"""Smoke-test fixtures.

These tests need a real PostgreSQL — the schema relies on `EXCLUDE USING gist`
and `tstzrange`, which SQLite cannot emulate. Set `TEST_DATABASE_URL` to point
at a throwaway database; in CI, docker-compose boots one for us.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from brewery_scheduler import db as db_module
from brewery_scheduler.main import app
from brewery_scheduler.models import Base
from brewery_scheduler.seed import seed

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://brewery:brewery@localhost:5432/brewery_test",
)


@pytest.fixture(scope="session")
def engine():
    eng = create_engine(TEST_DATABASE_URL, future=True)
    with eng.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS btree_gist"))
        conn.commit()
    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    # The EXCLUDE constraint isn't expressible via SQLAlchemy core — add it manually
    # so smoke tests exercise the same defense-in-depth as production.
    with eng.begin() as conn:
        conn.execute(
            text(
                """
                ALTER TABLE tank_occupancy
                ADD CONSTRAINT ex_tank_occupancy_no_overlap
                EXCLUDE USING gist (
                    tank_id WITH =,
                    tstzrange(start_at, end_at, '[)') WITH &&
                )
                """
            )
        )
    yield eng
    Base.metadata.drop_all(eng)


@pytest.fixture()
def session(engine) -> Iterator[Session]:
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with SessionLocal() as s:
        for table in reversed(Base.metadata.sorted_tables):
            s.execute(table.delete())
        s.commit()
        seed(s)
        yield s


@pytest.fixture()
def client(engine, session, monkeypatch) -> TestClient:
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    monkeypatch.setattr(db_module, "SessionLocal", SessionLocal)
    monkeypatch.setattr(db_module, "engine", engine)
    return TestClient(app)
