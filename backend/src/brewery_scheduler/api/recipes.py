from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import Recipe
from ..schemas import RecipeCreateIn, RecipeOut

router = APIRouter(prefix="/api/recipes", tags=["recipes"])


def _recipe_out(recipe: Recipe) -> RecipeOut:
    """Serialize a recipe incl. the JSONB-backed grain bill and hop
    additions (ingredients["malts"] / hop_additions["gaben"])."""
    out = RecipeOut.model_validate(recipe)
    out.malts = (recipe.ingredients or {}).get("malts", [])
    out.hop_gaben = (recipe.hop_additions or {}).get("gaben", [])
    return out


@router.get("", response_model=list[RecipeOut])
def list_recipes(session: Session = Depends(get_session)) -> list[RecipeOut]:
    """List all recipe versions, latest version per beer_style first.

    The full history is returned on purpose: the Rezepte tab renders the
    version timeline from it, and the new-Sud form filters to the latest
    version per style client-side.
    """
    stmt = select(Recipe).order_by(Recipe.beer_style, Recipe.version.desc())
    return [_recipe_out(r) for r in session.scalars(stmt)]


@router.post("", response_model=RecipeOut, status_code=status.HTTP_201_CREATED)
def create_recipe_version(
    payload: RecipeCreateIn, session: Session = Depends(get_session)
) -> Recipe:
    """Create a NEW version of a beer style's recipe — never edits in place.

    Recipes are versioned and immutable (ROADMAP §4): the server assigns
    max(version)+1 for the style. Already-scheduled Sude keep their original
    recipe link; new Sude pick up the latest version (issue #4).
    """
    if payload.open_fermentation_required and payload.open_fermentation_duration_days is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Offene Gärung ist Pflicht für dieses Rezept — bitte die "
                "Dauer der offenen Gärung angeben."
            ),
        )
    if payload.max_storage_duration_days < payload.storage_duration_days:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Die maximale Lagerdauer kann nicht kürzer sein als die "
                "reguläre Lagerdauer."
            ),
        )

    next_version = (
        session.scalar(
            select(func.coalesce(func.max(Recipe.version), 0)).where(
                Recipe.beer_style == payload.beer_style
            )
        )
        or 0
    ) + 1
    recipe = Recipe(
        beer_style=payload.beer_style,
        version=next_version,
        name=payload.name,
        fermentation_duration_days=payload.fermentation_duration_days,
        open_fermentation_required=payload.open_fermentation_required,
        open_fermentation_duration_days=payload.open_fermentation_duration_days,
        storage_duration_days=payload.storage_duration_days,
        max_storage_duration_days=payload.max_storage_duration_days,
        notes=payload.notes,
        created_by=payload.created_by,
        ingredients={"malts": [m.model_dump() for m in payload.malts]},
        hop_additions={"gaben": [g.model_dump() for g in payload.hop_gaben]},
        yeast=payload.yeast,
        original_gravity_plato=payload.original_gravity_plato,
        ibu=payload.ibu,
        color_ebc=payload.color_ebc,
    )
    session.add(recipe)
    session.commit()
    session.refresh(recipe)
    return _recipe_out(recipe)
