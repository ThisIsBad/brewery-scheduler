from fastapi import FastAPI

from .api import recipes, sude, tanks
from .config import settings

app = FastAPI(title=settings.api_title, version="0.1.0")

app.include_router(tanks.router)
app.include_router(recipes.router)
app.include_router(sude.router)


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok"}
