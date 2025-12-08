"""Recipe API endpoints."""


from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..database import get_db
from ..models import Recipe, RecipeCreate, RecipeUpdate, RecipeResponse, RecipeDetailResponse

router = APIRouter(prefix="/api/recipes", tags=["recipes"])

# File upload constraints
MAX_FILE_SIZE = 1_000_000  # 1MB in bytes


@router.get("", response_model=list[RecipeResponse])
async def list_recipes(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List all recipes."""
    query = (
        select(Recipe)
        .options(selectinload(Recipe.style))
        .order_by(Recipe.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{recipe_id}", response_model=RecipeDetailResponse)
async def get_recipe(recipe_id: int, db: AsyncSession = Depends(get_db)):
    """Get a specific recipe by ID with all ingredients."""
    query = (
        select(Recipe)
        .options(
            selectinload(Recipe.style),
            selectinload(Recipe.fermentables),
            selectinload(Recipe.hops),
            selectinload(Recipe.cultures),
            selectinload(Recipe.miscs),
        )
        .where(Recipe.id == recipe_id)
    )
    result = await db.execute(query)
    recipe = result.scalar_one_or_none()

    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")
    return recipe


@router.post("", response_model=RecipeResponse, status_code=201)
async def create_recipe(
    recipe: RecipeCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new recipe manually."""
    db_recipe = Recipe(
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
    await db.commit()
    await db.refresh(db_recipe)
    return db_recipe


@router.post("/import", response_model=RecipeResponse, status_code=201)
async def import_recipe(
    file: UploadFile = File(...),
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
    db: AsyncSession = Depends(get_db),
):
    """Update an existing recipe."""
    # Fetch existing recipe
    recipe = await db.get(Recipe, recipe_id)
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    # Update fields that are provided
    # Use explicit field assignment to prevent updating unintended fields
    update_data = recipe_update.model_dump(exclude_unset=True)

    # Whitelist of allowed update fields (matches RecipeUpdate model)
    allowed_fields = {
        'name', 'author', 'style_id', 'type', 'og', 'fg', 'abv', 'ibu',
        'color_srm', 'batch_size_liters', 'boil_time_minutes',
        'efficiency_percent', 'carbonation_vols', 'yeast_name', 'yeast_lab',
        'yeast_product_id', 'yeast_temp_min', 'yeast_temp_max',
        'yeast_attenuation', 'notes', 'format_extensions'
    }

    for field, value in update_data.items():
        if field in allowed_fields:
            setattr(recipe, field, value)

    await db.commit()

    # Eagerly load relationships for consistent API response format
    await db.refresh(recipe, ["style"])
    return recipe


@router.delete("/{recipe_id}")
async def delete_recipe(recipe_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a recipe."""
    recipe = await db.get(Recipe, recipe_id)
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    await db.delete(recipe)
    await db.commit()
    return {"status": "deleted"}
