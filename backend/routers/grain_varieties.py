"""Grain variety API endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import GrainVariety, GrainVarietyCreate, GrainVarietyResponse
from ..services.grain_seeder import seed_grain_varieties, get_grain_variety_count

router = APIRouter(prefix="/api/grain-varieties", tags=["grain-varieties"])


@router.get("", response_model=list[GrainVarietyResponse])
async def list_grain_varieties(
    type: Optional[str] = Query(None, description="Filter by type (base/specialty/adjunct/sugar/extract/fruit/other)"),
    origin: Optional[str] = Query(None, description="Filter by origin/country"),
    maltster: Optional[str] = Query(None, description="Filter by maltster/manufacturer"),
    search: Optional[str] = Query(None, description="Search in name, origin, maltster, flavor_profile"),
    is_custom: Optional[bool] = Query(None, description="Filter by custom varieties only"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List all grain varieties with optional filters."""
    query = select(GrainVariety).order_by(GrainVariety.name)

    # Apply filters
    if type:
        query = query.where(GrainVariety.type == type)
    if origin:
        query = query.where(GrainVariety.origin.ilike(f"%{origin}%"))
    if maltster:
        query = query.where(GrainVariety.maltster.ilike(f"%{maltster}%"))
    if is_custom is not None:
        query = query.where(GrainVariety.is_custom == is_custom)
    if search:
        search_pattern = f"%{search}%"
        query = query.where(
            or_(
                GrainVariety.name.ilike(search_pattern),
                GrainVariety.origin.ilike(search_pattern),
                GrainVariety.maltster.ilike(search_pattern),
                GrainVariety.flavor_profile.ilike(search_pattern),
            )
        )

    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/stats")
async def get_grain_variety_stats(db: AsyncSession = Depends(get_db)):
    """Get statistics about grain varieties."""
    counts = await get_grain_variety_count(db)
    return counts


@router.get("/types")
async def list_grain_types(db: AsyncSession = Depends(get_db)):
    """Get list of unique grain types."""
    result = await db.execute(
        select(GrainVariety.type)
        .where(GrainVariety.type.isnot(None))
        .distinct()
        .order_by(GrainVariety.type)
    )
    types = [row[0] for row in result.all()]
    return {"types": types}


@router.get("/origins")
async def list_grain_origins(db: AsyncSession = Depends(get_db)):
    """Get list of unique origins/countries."""
    result = await db.execute(
        select(GrainVariety.origin)
        .where(GrainVariety.origin.isnot(None))
        .distinct()
        .order_by(GrainVariety.origin)
    )
    origins = [row[0] for row in result.all()]
    return {"origins": origins}


@router.get("/maltsters")
async def list_maltsters(db: AsyncSession = Depends(get_db)):
    """Get list of unique maltsters/manufacturers."""
    result = await db.execute(
        select(GrainVariety.maltster)
        .where(GrainVariety.maltster.isnot(None))
        .distinct()
        .order_by(GrainVariety.maltster)
    )
    maltsters = [row[0] for row in result.all()]
    return {"maltsters": maltsters}


@router.get("/{variety_id}", response_model=GrainVarietyResponse)
async def get_grain_variety(variety_id: int, db: AsyncSession = Depends(get_db)):
    """Get a specific grain variety by ID."""
    variety = await db.get(GrainVariety, variety_id)
    if not variety:
        raise HTTPException(status_code=404, detail="Grain variety not found")
    return variety


@router.post("", response_model=GrainVarietyResponse, status_code=201)
async def create_grain_variety(
    variety: GrainVarietyCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a custom grain variety.

    Custom varieties are marked as is_custom=True and source='custom'.
    They are preserved when refreshing the database from the seed file.
    """
    db_variety = GrainVariety(
        name=variety.name,
        type=variety.type,
        origin=variety.origin,
        maltster=variety.maltster,
        color_srm=variety.color_srm,
        potential_sg=variety.potential_sg,
        max_in_batch_percent=variety.max_in_batch_percent,
        diastatic_power=variety.diastatic_power,
        flavor_profile=variety.flavor_profile,
        substitutes=variety.substitutes,
        description=variety.description,
        source="custom",
        is_custom=True,
    )
    db.add(db_variety)
    await db.commit()
    await db.refresh(db_variety)
    return db_variety


@router.delete("/{variety_id}")
async def delete_grain_variety(variety_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a custom grain variety.

    Only custom varieties (is_custom=True) can be deleted.
    Built-in varieties cannot be deleted but will be restored on refresh.
    """
    variety = await db.get(GrainVariety, variety_id)
    if not variety:
        raise HTTPException(status_code=404, detail="Grain variety not found")

    if not variety.is_custom:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete built-in grain variety. Use /refresh to restore defaults."
        )

    await db.delete(variety)
    await db.commit()
    return {"status": "deleted", "id": variety_id}


@router.post("/refresh")
async def refresh_grain_varieties(db: AsyncSession = Depends(get_db)):
    """Refresh grain varieties from seed file.

    Re-loads all non-custom varieties from the seed JSON file.
    Custom varieties (is_custom=True) are preserved.
    """
    result = await seed_grain_varieties(db, force=True)
    if not result["success"]:
        raise HTTPException(
            status_code=500,
            detail=result.get("error", "Refresh failed")
        )
    return result
