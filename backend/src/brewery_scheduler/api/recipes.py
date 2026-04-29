from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import Recipe
from ..schemas import RecipeOut

router = APIRouter(prefix="/api/recipes", tags=["recipes"])


@router.get("", response_model=list[RecipeOut])
def list_recipes(session: Session = Depends(get_session)) -> list[Recipe]:
    """List all recipes, latest version per beer_style first.

    Phase 1 returns the flat list so the frontend can populate a dropdown
    in the new-Sud form. Phase 3 will add filtering and version history.
    """
    stmt = select(Recipe).order_by(Recipe.beer_style, Recipe.version.desc())
    return list(session.scalars(stmt))
