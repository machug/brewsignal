"""Recipe API endpoints."""

import json
import re
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field, ValidationError as PydanticValidationError
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from typing import Any, Optional

from ..auth import AuthUser, require_auth
from ..config import get_settings
from ..database import get_db
from ..models import (
    Recipe, RecipeCulture, RecipeCreate, RecipeUpdate, RecipeResponse, RecipeDetailResponse,
    Style, StyleResponse,
    RecipeMashStep, MashStepInput, MashStepResponse,
    RecipeMisc, MiscInput, MiscResponse,
    RecipeWaterAdjustment, WaterAdjustmentInput, WaterAdjustmentResponse,
    RecipeWaterProfile, WaterProfileInput, WaterProfileResponse,
    RecipeFermentationStep, FermentationStepInput, FermentationStepResponse,
)
from ..services.brewsignal_format import BrewSignalRecipe, BeerJSONToBrewSignalConverter
from ..services.brewing import calculate_og_from_fermentables, calculate_recipe_stats
from ..services.converters.brewsignal_v2 import RecipeToBrewSignalV2Converter, to_strict_beerjson
from ..services.converters.recipe_to_brewfather import RecipeToBrewfatherConverter
from ..services.recipe_ingredients import hydrate_recipe_ingredients
from ..services.recipe_validation import validate_recipe_constraints
from ..services.style_resolver import resolve_style_id

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
        # LOCAL mode: single-user Pi, no ownership filtering needed
        return True
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
        .options(selectinload(Recipe.style), selectinload(Recipe.fermentables))
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


async def _load_recipe_for_export(
    recipe_id: int, user: AuthUser, db: AsyncSession
) -> Recipe:
    """Load a recipe with every relationship any exporter needs."""
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
            selectinload(Recipe.water_profiles),
            selectinload(Recipe.water_adjustments),
        )
        .where(Recipe.id == recipe_id, user_owns_recipe(user))
    )
    result = await db.execute(query)
    recipe = result.scalar_one_or_none()
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")
    return recipe


def _safe_filename(name: str) -> str:
    """Sanitize a recipe-derived filename to an ASCII-safe subset.

    Recipe names are user/import-controlled and can contain characters that
    break the Content-Disposition header outright: a `"` breaks out of the
    quoted filename, and non-latin-1 characters (emoji, CJK, etc.) raise a
    UnicodeEncodeError when the ASGI server encodes response headers,
    turning a download into a 500. Keep only a conservative safe subset and
    collapse everything else, rather than trying to percent-encode or
    otherwise preserve the original name.
    """
    sanitized = re.sub(r'[^A-Za-z0-9._-]+', "_", name or "")
    sanitized = sanitized.strip("._")
    return sanitized or "recipe"


def _download_response(payload: dict, stem: str, ext: str) -> Response:
    """Build the download Response with `filename="<safe-stem>.<ext>"`.

    The stem (recipe name) is sanitized separately from the extension:
    sanitizing the joined "name.ext" string meant a fully-unsafe name
    collapsed to "_.<ext>" and _safe_filename's strip("._") then ate the
    extension's leading dot, producing an extension-less file
    (tilt_ui-4bwa item 1).
    """
    return Response(
        content=json.dumps(payload, indent=2),
        media_type="application/json",
        headers={
            "Content-Disposition":
                f'attachment; filename="{_safe_filename(stem)}.{ext}"'
        },
    )


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
    recipe = await _load_recipe_for_export(recipe_id, user, db)
    converter = RecipeToBrewfatherConverter()
    brewfather_json = converter.convert(recipe)

    if download:
        return _download_response(brewfather_json, recipe.name, "json")

    return brewfather_json


@router.get("/{recipe_id}/export/brewsignal")
async def export_recipe_brewsignal(
    recipe_id: int,
    download: bool = Query(False, description="Return as downloadable file"),
    user: AuthUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Export a recipe as a native BrewSignal v2 document (tilt_ui-0jkg)."""
    recipe = await _load_recipe_for_export(recipe_id, user, db)
    doc = RecipeToBrewSignalV2Converter().convert(recipe)

    if download:
        return _download_response(doc, recipe.name, "brewsignal")

    return doc


@router.get("/{recipe_id}/export/beerjson")
async def export_recipe_beerjson(
    recipe_id: int,
    download: bool = Query(False, description="Return as downloadable file"),
    user: AuthUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Export a recipe as strict BeerJSON 1.0 (no brewsignal namespace) for
    interchange with other BeerJSON tools.

    The v2 `recipe` block uses a serializer-dialect shape so BrewSignal
    round-trips losslessly; this endpoint post-processes a copy of it into
    strict BeerJSON that validates against the official schemas
    (`additionalProperties: false`) — see
    `services.converters.brewsignal_v2.to_strict_beerjson`. Schema-required
    fields with no source data (e.g. an extract hop's alpha_acid, or a
    culture's amount) are filled with documented placeholder values rather
    than omitted, since the schema requires them but BrewSignal has no
    equivalent to carry over.
    """
    recipe = await _load_recipe_for_export(recipe_id, user, db)
    doc = RecipeToBrewSignalV2Converter().convert(recipe)
    strict_recipe = to_strict_beerjson(doc["recipe"], doc.get("notes"))
    beerjson = {"beerjson": {"version": 1.0, "recipes": [strict_recipe]}}

    if download:
        return _download_response(beerjson, recipe.name, "beerjson.json")

    return beerjson


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

    # Resolve free-text "style" (e.g. "American IPA") to a styles.id FK when
    # the client didn't send an explicit style_id. Same helper feeds the
    # LLM save_recipe path so behavior matches.
    resolved_style_id = recipe.style_id
    if resolved_style_id is None and recipe.style:
        resolved_style_id = await resolve_style_id(db, recipe.style)

    db_recipe = Recipe(
        user_id=user.user_id,
        name=recipe.name,
        author=recipe.author,
        style_id=resolved_style_id,
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
    # Persist ingredients to the relationship tables (source of truth) from the
    # editor's format_extensions cache, enriching grain colors from the
    # reference table. Without this, UI-created recipes leave recipe_hops /
    # recipe_fermentables empty (tilt_ui-9y7) and color-less (tilt_ui-hfi).
    # Hydrate while db_recipe is still transient (not yet added): the color
    # lookup's SELECT would otherwise autoflush the pending row to persistent,
    # and the subsequent collection .append would lazy-load and raise
    # MissingGreenlet. Children cascade-insert when the parent is added+flushed.
    rebuilt = await hydrate_recipe_ingredients(
        db, db_recipe, recipe.format_extensions
    )
    if rebuilt and db_recipe.fermentables:
        # The grain bill now carries real colors — recompute color_srm so the
        # card matches reality even when the editor sent a pale default. Use
        # the fermentables-only calc to avoid touching cultures/hops.
        _eff = db_recipe.efficiency_percent or 75
        _, _color = calculate_og_from_fermentables(
            db_recipe.fermentables,
            db_recipe.batch_size_liters or 20,
            _eff / 100 if _eff > 1 else _eff,
        )
        db_recipe.color_srm = round(_color, 1)

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
    # Re-query with eager loading for response serialization
    result = await db.execute(
        select(Recipe)
        .options(selectinload(Recipe.style), selectinload(Recipe.fermentables))
        .where(Recipe.id == db_recipe.id)
    )
    return result.scalar_one()


@router.post("/import", response_model=RecipeResponse, status_code=201)
async def import_recipe(
    file: UploadFile = File(...),
    source_format: Optional[str] = Query(
        None,
        description=(
            "Optional explicit format hint: beerxml, brewfather, beerjson, "
            "brewsignal. When omitted, format is auto-detected from content."
        ),
    ),
    user: AuthUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Import recipe from BeerXML, Brewfather JSON, BeerJSON, or native
    BrewSignal JSON file.

    Supports:
    - BeerXML 1.0 (.xml)
    - Brewfather JSON (.json)
    - BeerJSON 1.0 (.json)
    - BrewSignal native (.json)

    Format is auto-detected from file content. Pass ?source_format=brewsignal
    to skip detection (tilt_ui-kew).
    """
    from backend.services.importers.recipe_importer import RecipeImporter

    # Validate file extension
    if file.filename:
        ext = file.filename.lower().split('.')[-1]
        if ext not in ('xml', 'json', 'brewsignal'):
            raise HTTPException(
                status_code=400,
                detail=(
                    "Invalid file type. Only .xml, .json, and .brewsignal "
                    "files are supported"
                ),
            )

    # Validate source_format hint if provided
    if source_format is not None:
        normalized = source_format.lower()
        if normalized not in ("beerxml", "brewfather", "beerjson", "brewsignal"):
            raise HTTPException(
                status_code=400,
                detail=(
                    "Invalid source_format. Must be one of: "
                    "beerxml, brewfather, beerjson, brewsignal"
                ),
            )
        source_format = normalized

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

    # Import using new orchestrator (auto-detects format unless overridden)
    importer = RecipeImporter()
    result = await importer.import_recipe(content_str, source_format, db)

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
    recalculate: bool = Query(
        False,
        description=(
            "If true, server recomputes og/fg/abv/ibu/color_srm from "
            "ingredients and overwrites those fields on save. Default false "
            "preserves brewer-declared targets from imported recipes."
        ),
    ),
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

    # Apply updates from request. "style" is a transient free-text resolver
    # hint — not a column. Pop it before the setattr loop and resolve it to
    # styles.id below when the client didn't explicitly send a non-null
    # style_id.
    update_data = recipe_update.model_dump(exclude_unset=True)
    style_in_payload = "style" in update_data
    style_free_text = update_data.pop("style", None)
    # A non-null style_id from the client is authoritative. style_id=null
    # by itself is also explicit clear, BUT when accompanied by a style
    # free-text the text wins (typed-into-autocomplete-without-selecting
    # case — RecipeBuilder emits style_id=null + style="American IPA").
    explicit_style_id = (
        "style_id" in update_data and update_data["style_id"] is not None
    )
    for field, value in update_data.items():
        setattr(existing_recipe, field, value)

    # Resolve free-text "style" (e.g. "American IPA") to a styles.id FK.
    # Mirrors the LLM save_recipe path (services/llm/tools/recipe.py).
    if style_in_payload and not explicit_style_id:
        existing_recipe.style_id = await resolve_style_id(db, style_free_text)

    # Rebuild the relationship ingredient tables from the editor's
    # format_extensions cache so recipe_hops / recipe_fermentables remain the
    # source of truth on UI edits (tilt_ui-9y7 / tilt_ui-hfi).
    if "format_extensions" in update_data:
        rebuilt = await hydrate_recipe_ingredients(
            db, existing_recipe, update_data["format_extensions"]
        )
        # Recompute color_srm from the now-colored grain bill so the card is
        # correct, but only when full recalculation isn't already running
        # below — that preserves brewer-declared OG/FG/IBU targets (tilt_ui-5no).
        if rebuilt and existing_recipe.fermentables and not recalculate:
            _eff = existing_recipe.efficiency_percent or 75
            _, _color = calculate_og_from_fermentables(
                existing_recipe.fermentables,
                existing_recipe.batch_size_liters or 20,
                _eff / 100 if _eff > 1 else _eff,
            )
            existing_recipe.color_srm = round(_color, 1)

    # Recalculation is opt-in via ?recalculate=true. Without this gate,
    # imported recipes lose brewer-declared OG/FG/ABV/IBU/SRM targets on
    # any subsequent PUT (tilt_ui-5no).
    if recalculate and (existing_recipe.fermentables or existing_recipe.hops):
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
    # Session uses expire_on_commit=False, so the in-session instance still
    # holds the pre-update relationship cache (e.g. .style points at the old
    # row when style_id just changed). Expire the FK relationships so the
    # re-query's selectinload actually reloads them.
    db.expire(existing_recipe, ["style", "fermentables", "hops", "cultures"])
    # Re-query with eager loading for response serialization
    result = await db.execute(
        select(Recipe)
        .options(
            selectinload(Recipe.style),
            selectinload(Recipe.fermentables),
            selectinload(Recipe.hops),
            selectinload(Recipe.cultures),
        )
        .where(Recipe.id == existing_recipe.id)
    )
    return result.scalar_one()


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
    # Re-query with eager loading for response serialization
    result = await db.execute(
        select(Recipe)
        .options(
            selectinload(Recipe.style),
            selectinload(Recipe.fermentables),
            selectinload(Recipe.hops),
            selectinload(Recipe.cultures),
        )
        .where(Recipe.id == recipe.id)
    )
    return result.scalar_one()


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


# ============================================================================
# Recipe Mash Steps Sub-Resource API
# ============================================================================

@router.get("/{recipe_id}/mash-steps", response_model=list[MashStepResponse])
async def get_recipe_mash_steps(
    recipe_id: int,
    user: AuthUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Get all mash steps for a recipe."""
    result = await db.execute(
        select(Recipe)
        .options(selectinload(Recipe.mash_steps))
        .where(Recipe.id == recipe_id, user_owns_recipe(user))
    )
    recipe = result.scalar_one_or_none()
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    return sorted(recipe.mash_steps, key=lambda s: s.step_number)


@router.put("/{recipe_id}/mash-steps", response_model=list[MashStepResponse])
async def replace_recipe_mash_steps(
    recipe_id: int,
    steps: list[MashStepInput],
    user: AuthUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Replace all mash steps for a recipe."""
    result = await db.execute(
        select(Recipe)
        .options(selectinload(Recipe.mash_steps))
        .where(Recipe.id == recipe_id, user_owns_recipe(user))
    )
    recipe = result.scalar_one_or_none()
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    # Delete existing steps
    await db.execute(
        delete(RecipeMashStep).where(RecipeMashStep.recipe_id == recipe_id)
    )

    # Create new steps
    new_steps = []
    for step_data in steps:
        step = RecipeMashStep(
            recipe_id=recipe_id,
            step_number=step_data.step_number,
            name=step_data.name,
            type=step_data.type,
            temp_c=step_data.temp_c,
            time_minutes=step_data.time_minutes,
            infusion_amount_liters=step_data.infusion_amount_liters,
            infusion_temp_c=step_data.infusion_temp_c,
            ramp_time_minutes=step_data.ramp_time_minutes,
        )
        db.add(step)
        new_steps.append(step)

    await db.commit()

    for step in new_steps:
        await db.refresh(step)

    return sorted(new_steps, key=lambda s: s.step_number)


@router.delete("/{recipe_id}/mash-steps", response_model=dict)
async def delete_recipe_mash_steps(
    recipe_id: int,
    user: AuthUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Delete all mash steps for a recipe."""
    result = await db.execute(
        select(Recipe).where(Recipe.id == recipe_id, user_owns_recipe(user))
    )
    recipe = result.scalar_one_or_none()
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    await db.execute(
        delete(RecipeMashStep).where(RecipeMashStep.recipe_id == recipe_id)
    )
    await db.commit()

    return {"status": "deleted", "recipe_id": recipe_id}


# ============================================================================
# Recipe Fermentation Steps Sub-Resource API
# ============================================================================

@router.get("/{recipe_id}/fermentation-steps", response_model=list[FermentationStepResponse])
async def get_recipe_fermentation_steps(
    recipe_id: int,
    user: AuthUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Get all fermentation steps for a recipe."""
    result = await db.execute(
        select(Recipe)
        .options(selectinload(Recipe.fermentation_steps))
        .where(Recipe.id == recipe_id, user_owns_recipe(user))
    )
    recipe = result.scalar_one_or_none()
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    return sorted(recipe.fermentation_steps, key=lambda s: s.step_number)


@router.put("/{recipe_id}/fermentation-steps", response_model=list[FermentationStepResponse])
async def replace_recipe_fermentation_steps(
    recipe_id: int,
    steps: list[FermentationStepInput],
    user: AuthUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Replace all fermentation steps for a recipe."""
    result = await db.execute(
        select(Recipe)
        .options(selectinload(Recipe.fermentation_steps))
        .where(Recipe.id == recipe_id, user_owns_recipe(user))
    )
    recipe = result.scalar_one_or_none()
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    # Delete existing steps
    await db.execute(
        delete(RecipeFermentationStep).where(RecipeFermentationStep.recipe_id == recipe_id)
    )

    # Create new steps
    new_steps = []
    for step_data in steps:
        step = RecipeFermentationStep(
            recipe_id=recipe_id,
            step_number=step_data.step_number,
            type=step_data.type,
            temp_c=step_data.temp_c,
            time_days=step_data.time_days,
        )
        db.add(step)
        new_steps.append(step)

    await db.commit()

    for step in new_steps:
        await db.refresh(step)

    return sorted(new_steps, key=lambda s: s.step_number)


@router.delete("/{recipe_id}/fermentation-steps", response_model=dict)
async def delete_recipe_fermentation_steps(
    recipe_id: int,
    user: AuthUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Delete all fermentation steps for a recipe."""
    result = await db.execute(
        select(Recipe).where(Recipe.id == recipe_id, user_owns_recipe(user))
    )
    recipe = result.scalar_one_or_none()
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    await db.execute(
        delete(RecipeFermentationStep).where(RecipeFermentationStep.recipe_id == recipe_id)
    )
    await db.commit()

    return {"status": "deleted", "recipe_id": recipe_id}


# ============================================================================
# Recipe Water Adjustments Sub-Resource API
# ============================================================================

@router.get("/{recipe_id}/water-adjustments", response_model=list[WaterAdjustmentResponse])
async def get_recipe_water_adjustments(
    recipe_id: int,
    user: AuthUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Get all water adjustments for a recipe."""
    result = await db.execute(
        select(Recipe)
        .options(selectinload(Recipe.water_adjustments))
        .where(Recipe.id == recipe_id, user_owns_recipe(user))
    )
    recipe = result.scalar_one_or_none()
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    return recipe.water_adjustments


@router.put("/{recipe_id}/water-adjustments", response_model=list[WaterAdjustmentResponse])
async def replace_recipe_water_adjustments(
    recipe_id: int,
    adjustments: list[WaterAdjustmentInput],
    user: AuthUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Replace all water adjustments for a recipe."""
    result = await db.execute(
        select(Recipe)
        .options(selectinload(Recipe.water_adjustments))
        .where(Recipe.id == recipe_id, user_owns_recipe(user))
    )
    recipe = result.scalar_one_or_none()
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    # Delete existing adjustments
    await db.execute(
        delete(RecipeWaterAdjustment).where(RecipeWaterAdjustment.recipe_id == recipe_id)
    )

    # Create new adjustments
    new_adjustments = []
    for adj_data in adjustments:
        adj = RecipeWaterAdjustment(
            recipe_id=recipe_id,
            stage=adj_data.stage,
            volume_liters=adj_data.volume_liters,
            calcium_sulfate_g=adj_data.calcium_sulfate_g,
            calcium_chloride_g=adj_data.calcium_chloride_g,
            magnesium_sulfate_g=adj_data.magnesium_sulfate_g,
            sodium_bicarbonate_g=adj_data.sodium_bicarbonate_g,
            calcium_carbonate_g=adj_data.calcium_carbonate_g,
            calcium_hydroxide_g=adj_data.calcium_hydroxide_g,
            magnesium_chloride_g=adj_data.magnesium_chloride_g,
            sodium_chloride_g=adj_data.sodium_chloride_g,
            acid_type=adj_data.acid_type,
            acid_ml=adj_data.acid_ml,
            acid_concentration_percent=adj_data.acid_concentration_percent,
        )
        db.add(adj)
        new_adjustments.append(adj)

    await db.commit()

    for adj in new_adjustments:
        await db.refresh(adj)

    return new_adjustments


@router.delete("/{recipe_id}/water-adjustments", response_model=dict)
async def delete_recipe_water_adjustments(
    recipe_id: int,
    user: AuthUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Delete all water adjustments for a recipe."""
    result = await db.execute(
        select(Recipe).where(Recipe.id == recipe_id, user_owns_recipe(user))
    )
    recipe = result.scalar_one_or_none()
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    await db.execute(
        delete(RecipeWaterAdjustment).where(RecipeWaterAdjustment.recipe_id == recipe_id)
    )
    await db.commit()

    return {"status": "deleted", "recipe_id": recipe_id}


# ============================================================================
# Recipe Miscs Sub-Resource API
# ============================================================================

@router.get("/{recipe_id}/miscs", response_model=list[MiscResponse])
async def get_recipe_miscs(
    recipe_id: int,
    user: AuthUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Get all misc ingredients for a recipe."""
    result = await db.execute(
        select(Recipe)
        .options(selectinload(Recipe.miscs))
        .where(Recipe.id == recipe_id, user_owns_recipe(user))
    )
    recipe = result.scalar_one_or_none()
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    return recipe.miscs


@router.put("/{recipe_id}/miscs", response_model=list[MiscResponse])
async def replace_recipe_miscs(
    recipe_id: int,
    miscs: list[MiscInput],
    user: AuthUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Replace all misc ingredients for a recipe."""
    result = await db.execute(
        select(Recipe)
        .options(selectinload(Recipe.miscs))
        .where(Recipe.id == recipe_id, user_owns_recipe(user))
    )
    recipe = result.scalar_one_or_none()
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    # Delete existing miscs
    await db.execute(
        delete(RecipeMisc).where(RecipeMisc.recipe_id == recipe_id)
    )

    # Create new miscs
    new_miscs = []
    for misc_data in miscs:
        misc = RecipeMisc(
            recipe_id=recipe_id,
            name=misc_data.name,
            type=misc_data.type,
            use=misc_data.use,
            time_min=misc_data.time_min,
            amount_kg=misc_data.amount_kg,
            amount_unit=misc_data.amount_unit,
            use_for=misc_data.use_for,
            notes=misc_data.notes,
        )
        db.add(misc)
        new_miscs.append(misc)

    await db.commit()

    for misc in new_miscs:
        await db.refresh(misc)

    return new_miscs


@router.delete("/{recipe_id}/miscs", response_model=dict)
async def delete_recipe_miscs(
    recipe_id: int,
    user: AuthUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Delete all misc ingredients for a recipe."""
    result = await db.execute(
        select(Recipe).where(Recipe.id == recipe_id, user_owns_recipe(user))
    )
    recipe = result.scalar_one_or_none()
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    await db.execute(
        delete(RecipeMisc).where(RecipeMisc.recipe_id == recipe_id)
    )
    await db.commit()

    return {"status": "deleted", "recipe_id": recipe_id}


# ============================================================================
# Recipe Water Profiles Sub-Resource API
# ============================================================================

@router.get("/{recipe_id}/water-profiles", response_model=list[WaterProfileResponse])
async def get_recipe_water_profiles(
    recipe_id: int,
    user: AuthUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Get all water profiles for a recipe."""
    result = await db.execute(
        select(Recipe)
        .options(selectinload(Recipe.water_profiles))
        .where(Recipe.id == recipe_id, user_owns_recipe(user))
    )
    recipe = result.scalar_one_or_none()
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    return recipe.water_profiles


@router.put("/{recipe_id}/water-profiles", response_model=list[WaterProfileResponse])
async def replace_recipe_water_profiles(
    recipe_id: int,
    profiles: list[WaterProfileInput],
    user: AuthUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Replace all water profiles for a recipe."""
    result = await db.execute(
        select(Recipe)
        .options(selectinload(Recipe.water_profiles))
        .where(Recipe.id == recipe_id, user_owns_recipe(user))
    )
    recipe = result.scalar_one_or_none()
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    # Delete existing profiles
    await db.execute(
        delete(RecipeWaterProfile).where(RecipeWaterProfile.recipe_id == recipe_id)
    )

    # Create new profiles
    new_profiles = []
    for profile_data in profiles:
        profile = RecipeWaterProfile(
            recipe_id=recipe_id,
            profile_type=profile_data.profile_type,
            name=profile_data.name,
            calcium_ppm=profile_data.calcium_ppm,
            magnesium_ppm=profile_data.magnesium_ppm,
            sodium_ppm=profile_data.sodium_ppm,
            chloride_ppm=profile_data.chloride_ppm,
            sulfate_ppm=profile_data.sulfate_ppm,
            bicarbonate_ppm=profile_data.bicarbonate_ppm,
            ph=profile_data.ph,
            alkalinity=profile_data.alkalinity,
        )
        db.add(profile)
        new_profiles.append(profile)

    await db.commit()

    for profile in new_profiles:
        await db.refresh(profile)

    return new_profiles


@router.delete("/{recipe_id}/water-profiles", response_model=dict)
async def delete_recipe_water_profiles(
    recipe_id: int,
    user: AuthUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Delete all water profiles for a recipe."""
    result = await db.execute(
        select(Recipe).where(Recipe.id == recipe_id, user_owns_recipe(user))
    )
    recipe = result.scalar_one_or_none()
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    await db.execute(
        delete(RecipeWaterProfile).where(RecipeWaterProfile.recipe_id == recipe_id)
    )
    await db.commit()

    return {"status": "deleted", "recipe_id": recipe_id}
