"""Recipe API endpoints."""

import json
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field, ValidationError as PydanticValidationError
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from typing import Any, Optional

from ..auth import AuthUser, require_auth
from ..config import get_settings
from ..database import get_db
from ..models import Recipe, RecipeCulture, RecipeCreate, RecipeUpdate, RecipeResponse, RecipeDetailResponse, Style, StyleResponse
from ..services.brewsignal_format import BrewSignalRecipe, BeerJSONToBrewSignalConverter
from ..services.brewing import calculate_recipe_stats
from ..services.converters.recipe_to_brewfather import RecipeToBrewfatherConverter
from ..services.recipe_validation import validate_recipe_constraints

router = APIRouter(prefix="/api/recipes", tags=["recipes"])

# File upload constraints
MAX_FILE_SIZE = 1_000_000  # 1MB in bytes


def user_owns_recipe(user: AuthUser):
    """Create a SQLAlchemy condition for recipe ownership.

    In LOCAL deployment mode, includes:
    - Recipes explicitly owned by the user
    - Recipes owned by the dummy "local" user (pre-auth data)
    - Unclaimed recipes (user_id IS NULL) for backward compatibility

    In CLOUD deployment mode, strictly filters by user_id.
    """
    settings = get_settings()
    if settings.is_local:
        return or_(
            Recipe.user_id == user.user_id,
            Recipe.user_id == "local",
            Recipe.user_id.is_(None),
        )
    return Recipe.user_id == user.user_id


async def get_user_recipe(recipe_id: int, user: AuthUser, db: AsyncSession) -> Recipe:
    """Fetch a recipe with user ownership verification.

    Raises 404 if recipe not found or not owned by user.
    """
    result = await db.execute(
        select(Recipe)
        .options(
            selectinload(Recipe.style),
            selectinload(Recipe.fermentables),
            selectinload(Recipe.hops),
            selectinload(Recipe.cultures),
            selectinload(Recipe.miscs),
            selectinload(Recipe.mash_steps),
            selectinload(Recipe.fermentation_steps),
            selectinload(Recipe.water_profiles),
            selectinload(Recipe.water_adjustments),
        )
        .where(Recipe.id == recipe_id, user_owns_recipe(user))
    )
    recipe = result.scalar_one_or_none()
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")
    return recipe


class RecipeValidationRequest(BaseModel):
    format: str
    data: dict


class RecipeValidationError(BaseModel):
    field: str
    value: Optional[Any] = None
    error: str


class RecipeValidationWarning(BaseModel):
    field: str
    value: Optional[Any] = None
    warning: str


class RecipeValidationResponse(BaseModel):
    valid: bool
    errors: list[RecipeValidationError] = Field(default_factory=list)
    warnings: list[RecipeValidationWarning] = Field(default_factory=list)


def _coerce_brewsignal_recipe(data: dict) -> dict:
    """Extract BrewSignal recipe payload from either envelope or raw recipe."""
    if not isinstance(data, dict):
        raise ValueError("Recipe data must be a JSON object")
    if "recipe" in data:
        recipe = data.get("recipe")
        if not isinstance(recipe, dict):
            raise ValueError("Recipe field must be a JSON object")
        return recipe
    return data


def _pydantic_errors_to_payload(errors: list[dict]) -> list[RecipeValidationError]:
    payload = []
    for err in errors:
        loc = err.get("loc", ())
        field = ".".join(str(part) for part in loc) if loc else ""
        field = f"recipe.{field}" if field else "recipe"
        payload.append(
            RecipeValidationError(
                field=field,
                value=err.get("input"),
                error=err.get("msg", "Invalid value"),
            )
        )
    return payload


def _append_warnings(recipe_data: dict, warnings: list[RecipeValidationWarning]) -> None:
    """Populate warnings for unusual values and missing recommended fields."""
    if not isinstance(recipe_data, dict):
        return

    def as_number(value: Any) -> Optional[float]:
        return value if isinstance(value, (int, float)) else None

    og = as_number(recipe_data.get("og"))
    abv = as_number(recipe_data.get("abv"))
    ibu = as_number(recipe_data.get("ibu"))
    boil_time = recipe_data.get("boil_time_minutes")

    if isinstance(boil_time, int):
        if boil_time < 30 or boil_time > 120:
            warnings.append(
                RecipeValidationWarning(
                    field="recipe.boil_time_minutes",
                    value=boil_time,
                    warning=f"Unusual boil time of {boil_time} minutes",
                )
            )

    if og is not None and (og < 1.030 or og > 1.100):
        warnings.append(
            RecipeValidationWarning(
                field="recipe.og",
                value=og,
                warning=f"Unusual original gravity of {og}",
            )
        )

    if ibu is not None and ibu > 100:
        warnings.append(
            RecipeValidationWarning(
                field="recipe.ibu",
                value=ibu,
                warning=f"Very high IBU of {ibu}",
            )
        )

    if abv is not None and abv > 12:
        warnings.append(
            RecipeValidationWarning(
                field="recipe.abv",
                value=abv,
                warning=f"Very high ABV of {abv}%",
            )
        )

    if recipe_data.get("batch_size_liters") is None:
        warnings.append(
            RecipeValidationWarning(
                field="recipe.batch_size_liters",
                warning="Missing batch size (recommended)",
            )
        )

    if recipe_data.get("efficiency_percent") is None:
        warnings.append(
            RecipeValidationWarning(
                field="recipe.efficiency_percent",
                warning="Missing brewhouse efficiency (recommended)",
            )
        )


# ============================================================================
# BJCP Styles API
# ============================================================================

@router.get("/styles/search", response_model=list[StyleResponse])
async def search_styles(
    q: str = Query(..., min_length=2, description="Search query for style name or alias"),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """Search BJCP styles by name or alias (e.g., 'NEIPA' finds 'Hazy IPA')."""
    search_term = q.lower()
    query = (
        select(Style)
        .where(
            or_(
                func.lower(Style.name).contains(search_term),
                func.lower(Style.comments).contains(search_term),
            )
        )
        .order_by(Style.name)
        .limit(limit)
    )
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/styles/{style_id}", response_model=StyleResponse)
async def get_style(
    style_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get a specific BJCP style by ID."""
    result = await db.execute(select(Style).where(Style.id == style_id))
    style = result.scalar_one_or_none()
    if not style:
        raise HTTPException(status_code=404, detail="Style not found")
    return style


@router.get("/styles", response_model=list[StyleResponse])
async def list_styles(
    category: Optional[str] = Query(None, description="Filter by category"),
    type: Optional[str] = Query(None, description="Filter by type (Ale, Lager, etc.)"),
    limit: int = Query(100, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """List all BJCP styles, optionally filtered by category or type."""
    query = select(Style)
    if category:
        query = query.where(func.lower(Style.category).contains(category.lower()))
    if type:
        query = query.where(func.lower(Style.type) == type.lower())
    query = query.order_by(Style.category_number, Style.style_letter).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


# ============================================================================
# Recipes API
# ============================================================================

@router.get("", response_model=list[RecipeResponse])
async def list_recipes(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: AuthUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """List all recipes owned by the current user."""
    query = (
        select(Recipe)
        .options(selectinload(Recipe.style))
        .where(user_owns_recipe(user))
        .order_by(Recipe.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/validate", response_model=RecipeValidationResponse)
async def validate_recipe(request: RecipeValidationRequest):
    """Validate recipe data without creating or importing a recipe."""
    errors: list[RecipeValidationError] = []
    warnings: list[RecipeValidationWarning] = []

    format_value = request.format.strip().lower()
    if format_value not in {"brewsignal", "beerjson"}:
        raise HTTPException(status_code=400, detail=f"Unsupported format: {request.format}")

    if format_value == "beerjson":
        converter = BeerJSONToBrewSignalConverter()
        try:
            brewsignal = converter.convert(request.data)
            recipe_data = _coerce_brewsignal_recipe(brewsignal)
        except (KeyError, IndexError, ValueError, TypeError) as exc:
            errors.append(
                RecipeValidationError(
                    field="data",
                    value=None,
                    error=str(exc),
                )
            )
            return RecipeValidationResponse(valid=False, errors=errors, warnings=warnings)
    else:
        try:
            recipe_data = _coerce_brewsignal_recipe(request.data)
        except ValueError as exc:
            errors.append(
                RecipeValidationError(
                    field="data",
                    value=None,
                    error=str(exc),
                )
            )
            return RecipeValidationResponse(valid=False, errors=errors, warnings=warnings)

    try:
        BrewSignalRecipe(**recipe_data)
    except PydanticValidationError as exc:
        errors.extend(_pydantic_errors_to_payload(exc.errors()))

    _append_warnings(recipe_data, warnings)

    return RecipeValidationResponse(valid=len(errors) == 0, errors=errors, warnings=warnings)


@router.get("/{recipe_id}", response_model=RecipeDetailResponse)
async def get_recipe(
    recipe_id: int,
    user: AuthUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific recipe by ID with all ingredients."""
    return await get_user_recipe(recipe_id, user, db)


@router.get("/{recipe_id}/export/brewfather")
async def export_recipe_brewfather(
    recipe_id: int,
    download: bool = Query(False, description="Return as downloadable file"),
    user: AuthUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Export a recipe in Brewfather JSON format.

    Returns Brewfather-compatible JSON that can be imported directly into Brewfather.

    Args:
        recipe_id: The recipe ID to export
        download: If True, returns as a downloadable .json file
    """
    # Load recipe with all relationships and ownership check
    query = (
        select(Recipe)
        .options(
            selectinload(Recipe.style),
            selectinload(Recipe.fermentables),
            selectinload(Recipe.hops),
            selectinload(Recipe.cultures),
            selectinload(Recipe.miscs),
            selectinload(Recipe.mash_steps),
            selectinload(Recipe.fermentation_steps),
        )
        .where(Recipe.id == recipe_id, user_owns_recipe(user))
    )
    result = await db.execute(query)
    recipe = result.scalar_one_or_none()

    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    # Convert to Brewfather format
    converter = RecipeToBrewfatherConverter()
    brewfather_json = converter.convert(recipe)

    if download:
        # Return as downloadable file
        filename = f"{recipe.name or 'recipe'}.json".replace(" ", "_")
        content = json.dumps(brewfather_json, indent=2)
        return Response(
            content=content,
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            },
        )

    return brewfather_json


@router.post("", response_model=RecipeResponse, status_code=201)
async def create_recipe(
    recipe: RecipeCreate,
    user: AuthUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Create a new recipe manually."""
    # Validate business logic
    validate_recipe_constraints(
        og=recipe.og,
        fg=recipe.fg,
        batch_size_liters=recipe.batch_size_liters,
        abv=recipe.abv,
    )

    db_recipe = Recipe(
        user_id=user.user_id,
        name=recipe.name,
        author=recipe.author,
        style_id=recipe.style_id,
        type=recipe.type,
        og=recipe.og,
        fg=recipe.fg,
        abv=recipe.abv,
        ibu=recipe.ibu,
        color_srm=recipe.color_srm,
        batch_size_liters=recipe.batch_size_liters,
        boil_time_minutes=recipe.boil_time_minutes,
        efficiency_percent=recipe.efficiency_percent,
        carbonation_vols=recipe.carbonation_vols,
        yeast_name=recipe.yeast_name,
        yeast_lab=recipe.yeast_lab,
        yeast_product_id=recipe.yeast_product_id,
        yeast_temp_min=recipe.yeast_temp_min,
        yeast_temp_max=recipe.yeast_temp_max,
        yeast_attenuation=recipe.yeast_attenuation,
        notes=recipe.notes,
        format_extensions=recipe.format_extensions,
    )
    db.add(db_recipe)
    await db.flush()  # Get recipe ID without committing

    # Also create RecipeCulture record for BeerJSON compliance
    if recipe.yeast_name:
        culture = RecipeCulture(
            recipe_id=db_recipe.id,
            name=recipe.yeast_name,
            producer=recipe.yeast_lab,
            product_id=recipe.yeast_product_id,
            temp_min_c=recipe.yeast_temp_min,
            temp_max_c=recipe.yeast_temp_max,
            attenuation_min_percent=recipe.yeast_attenuation,
            attenuation_max_percent=recipe.yeast_attenuation,
        )
        db.add(culture)

    await db.commit()
    await db.refresh(db_recipe)
    return db_recipe


@router.post("/import", response_model=RecipeResponse, status_code=201)
async def import_recipe(
    file: UploadFile = File(...),
    user: AuthUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Import recipe from BeerXML, Brewfather JSON, or BeerJSON file.

    Supports:
    - BeerXML 1.0 (.xml)
    - Brewfather JSON (.json)
    - BeerJSON 1.0 (.json)

    Format is auto-detected from file content.
    """
    from backend.services.importers.recipe_importer import RecipeImporter

    # Validate file extension
    if file.filename:
        ext = file.filename.lower().split('.')[-1]
        if ext not in ('xml', 'json'):
            raise HTTPException(
                status_code=400,
                detail="Invalid file type. Only .xml and .json files are supported"
            )

    # Read file content with size validation
    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="File is empty")
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File too large (max 1MB)")

    # Decode content
    try:
        content_str = content.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File must be UTF-8 encoded")

    # Import using new orchestrator (auto-detects format)
    importer = RecipeImporter()
    result = await importer.import_recipe(content_str, None, db)

    # Handle import failure
    if not result.success:
        await db.rollback()
        # Note: detail is a list of error strings (List[str]) from ImportResult.errors
        raise HTTPException(
            status_code=400,
            detail=result.errors
        )

    # Set user_id on imported recipe
    result.recipe.user_id = user.user_id

    # Import succeeded - commit to database
    await db.commit()

    # Reload recipe with all relationships for response
    stmt = (
        select(Recipe)
        .where(Recipe.id == result.recipe.id)
        .options(
            selectinload(Recipe.fermentables),
            selectinload(Recipe.hops),
            selectinload(Recipe.cultures),
            selectinload(Recipe.miscs),
            selectinload(Recipe.mash_steps),
            selectinload(Recipe.fermentation_steps),
            selectinload(Recipe.water_profiles),
            selectinload(Recipe.water_adjustments),
            selectinload(Recipe.style)
        )
    )
    result_obj = await db.execute(stmt)
    recipe = result_obj.scalar_one()

    return recipe


@router.put("/{recipe_id}", response_model=RecipeResponse)
async def update_recipe(
    recipe_id: int,
    recipe_update: RecipeUpdate,
    user: AuthUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing recipe."""
    # Fetch existing recipe with ingredients and ownership check
    result = await db.execute(
        select(Recipe)
        .options(
            selectinload(Recipe.style),
            selectinload(Recipe.fermentables),
            selectinload(Recipe.hops),
            selectinload(Recipe.cultures),
        )
        .where(Recipe.id == recipe_id, user_owns_recipe(user))
    )
    existing_recipe = result.scalar_one_or_none()

    if not existing_recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    # Apply updates from request
    for field, value in recipe_update.model_dump(exclude_unset=True).items():
        setattr(existing_recipe, field, value)

    # Recalculate stats from ingredients if we have any
    if existing_recipe.fermentables or existing_recipe.hops:
        stats = calculate_recipe_stats(existing_recipe)
        existing_recipe.og = stats["og"]
        existing_recipe.fg = stats["fg"]
        existing_recipe.abv = stats["abv"]
        existing_recipe.ibu = stats["ibu"]
        existing_recipe.color_srm = stats["color_srm"]

    # Validate the final values
    validate_recipe_constraints(
        og=existing_recipe.og,
        fg=existing_recipe.fg,
        batch_size_liters=existing_recipe.batch_size_liters,
        abv=existing_recipe.abv,
    )

    await db.commit()
    await db.refresh(existing_recipe)

    return existing_recipe


@router.post("/{recipe_id}/recalculate", response_model=RecipeResponse)
async def recalculate_recipe_stats(
    recipe_id: int,
    user: AuthUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Recalculate a recipe's OG, FG, ABV, IBU, and color from its ingredients.

    Use this to update existing recipes with server-side calculated statistics.
    """
    result = await db.execute(
        select(Recipe)
        .options(
            selectinload(Recipe.style),
            selectinload(Recipe.fermentables),
            selectinload(Recipe.hops),
            selectinload(Recipe.cultures),
        )
        .where(Recipe.id == recipe_id, user_owns_recipe(user))
    )
    recipe = result.scalar_one_or_none()

    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    if not recipe.fermentables and not recipe.hops:
        raise HTTPException(
            status_code=400,
            detail="Recipe has no ingredients to calculate from"
        )

    stats = calculate_recipe_stats(recipe)
    recipe.og = stats["og"]
    recipe.fg = stats["fg"]
    recipe.abv = stats["abv"]
    recipe.ibu = stats["ibu"]
    recipe.color_srm = stats["color_srm"]

    await db.commit()
    await db.refresh(recipe)

    return recipe


@router.delete("/{recipe_id}")
async def delete_recipe(
    recipe_id: int,
    user: AuthUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Delete a recipe."""
    result = await db.execute(
        select(Recipe).where(Recipe.id == recipe_id, user_owns_recipe(user))
    )
    recipe = result.scalar_one_or_none()
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    await db.delete(recipe)
    await db.commit()
    return {"status": "deleted"}
