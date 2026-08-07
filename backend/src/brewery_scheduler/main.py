import logging
import time

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from .api import locations, recipes, sude, tanks, verlauf
from .config import settings
from .db import angemeldeter_benutzer

app = FastAPI(title=settings.api_title, version="0.1.0")

app.include_router(tanks.router)
app.include_router(locations.router)
app.include_router(recipes.router)
app.include_router(sude.router)
app.include_router(verlauf.router)

log = logging.getLogger("brewery")

NUR_LESEND = frozenset({"GET", "HEAD", "OPTIONS"})


@app.middleware("http")
async def zugriffe_protokollieren(request: Request, call_next):
    """Technisches Gegenstück zum fachlichen Protokoll: eine Zeile je
    ändernder Anfrage und je Fehler, mit Benutzer und Dauer. Lesende
    Anfragen bleiben still, sonst ersäuft das Log im Abrufrauschen."""
    beginn = time.perf_counter()
    response = await call_next(request)
    if request.method not in NUR_LESEND or response.status_code >= 400:
        log.info(
            "%s %s %s -> %s (%.0f ms)",
            angemeldeter_benutzer(request),
            request.method,
            request.url.path,
            response.status_code,
            (time.perf_counter() - beginn) * 1000,
        )
    return response


# The GiST EXCLUDE constraint is the Phase-1 barrier against double-booking
# (CLAUDE.md domain rules) — translate its violation into a structured
# conflict response instead of leaking a 500. Phase 2 adds application-level
# validation in front of this; the handler stays as the last line of defense.
CONSTRAINT_RESPONSES: dict[str | None, tuple[int, str]] = {
    "ex_tank_occupancy_no_overlap": (
        409,
        "Tank is already occupied in the requested time window.",
    ),
    "ck_tank_occupancy_time_order": (422, "end_at must be after start_at."),
    "uq_sude_global_number": (409, "Duplicate global Sud number."),
    "ck_sude_no_self_merge": (422, "A Sud cannot be merged into itself."),
    "fk_sude_merged_into": (422, "The referenced lead Sud does not exist."),
    "uq_sude_style_year_number": (
        409,
        "A Sud with this number already exists for this style and year — retry.",
    ),
    "uq_tanks_name": (409, "A tank with this name already exists."),
    "uq_locations_name": (409, "A location with this name already exists."),
    "uq_recipes_style_version": (
        409,
        "This recipe version already exists for the style — retry.",
    ),
    "fk_tanks_location": (409, "The referenced location does not exist."),
}


@app.exception_handler(IntegrityError)
async def integrity_error_handler(request: Request, exc: IntegrityError) -> JSONResponse:
    diag = getattr(exc.orig, "diag", None)
    constraint = getattr(diag, "constraint_name", None)
    status_code, message = CONSTRAINT_RESPONSES.get(
        constraint, (409, "Database constraint violated.")
    )
    return JSONResponse(
        status_code=status_code,
        content={"detail": message, "constraint": constraint},
    )


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/ich", tags=["meta"])
def ich(request: Request) -> dict[str, str]:
    """Wer ist angemeldet — für die Profilanzeige. Die App kennt den Namen
    sonst nicht: Caddy prüft die Anmeldung und reicht ihn nur ans Backend
    weiter, der Browser sieht ihn nie."""
    return {"benutzer": angemeldeter_benutzer(request)}
