from collections.abc import Iterator

from fastapi import Request
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .audit import benutzer_setzen
from .config import settings

engine = create_engine(settings.database_url, future=True, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

# Setzt ausschließlich Caddy nach erfolgreicher Anmeldung; was ein Client
# schickt, wird dort überschrieben (deploy/Caddyfile).
BENUTZER_HEADER = "X-Authenticated-User"


def angemeldeter_benutzer(request: Request) -> str:
    return request.headers.get(BENUTZER_HEADER) or settings.fallback_benutzer


def get_session(request: Request) -> Iterator[Session]:
    session = SessionLocal()
    benutzer_setzen(session, angemeldeter_benutzer(request))
    try:
        yield session
    finally:
        session.close()
