from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from .api import recipes, sude, tanks
from .config import settings

app = FastAPI(title=settings.api_title, version="0.1.0")

app.include_router(tanks.router)
app.include_router(recipes.router)
app.include_router(sude.router)


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
