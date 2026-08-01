"""Smoke-test fixtures.

These tests need a real PostgreSQL — the schema relies on `EXCLUDE USING gist`
and `tstzrange`, which SQLite cannot emulate. Set `TEST_DATABASE_URL` to point
at a throwaway database; in CI, a service container provides one.

The schema is built by running the actual Alembic migrations, not
`Base.metadata.create_all` — so the migration SQL (including backfills and
hand-written DDL like the EXCLUDE constraint) is exercised on every test run
and cannot drift from what production gets.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic.config import Config as AlembicConfig
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from alembic import command
from brewery_scheduler import db as db_module
from brewery_scheduler.main import app
from brewery_scheduler.models import Base
from brewery_scheduler.seed import seed

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://brewery:brewery@localhost:5432/brewery_test",
)

BACKEND_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def engine():
    eng = create_engine(TEST_DATABASE_URL, future=True)

    # Nuke everything (tables, sequences, the btree_gist extension, the
    # alembic_version bookkeeping) so `upgrade head` always starts from a
    # genuinely empty database.
    with eng.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))

    cfg = AlembicConfig(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    command.upgrade(cfg, "head")

    yield eng
    eng.dispose()


@pytest.fixture()
def session(engine) -> Iterator[Session]:
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with SessionLocal() as s:
        for table in reversed(Base.metadata.sorted_tables):
            s.execute(table.delete())
        # Sequence values aren't reset by row deletion — restart so that
        # tests asserting specific global_number values stay deterministic
        # regardless of test ordering.
        s.execute(text("ALTER SEQUENCE sud_global_seq RESTART WITH 1"))
        s.commit()
        seed(s)
        yield s


@pytest.fixture()
def client(engine, session, monkeypatch) -> TestClient:
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    monkeypatch.setattr(db_module, "SessionLocal", SessionLocal)
    monkeypatch.setattr(db_module, "engine", engine)
    return TestClient(app)
