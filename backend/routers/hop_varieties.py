"""Hop variety API endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import HopVariety, HopVarietyCreate, HopVarietyResponse
from ..services.hop_seeder import seed_hop_varieties, get_hop_variety_count

router = APIRouter(prefix="/api/hop-varieties", tags=["hop-varieties"])


@router.get("", response_model=list[HopVarietyResponse])
async def list_hop_varieties(
    origin: Optional[str] = Query(None, description="Filter by origin/country"),
    purpose: Optional[str] = Query(None, description="Filter by purpose (bittering/aroma/dual)"),
    search: Optional[str] = Query(None, description="Search in name, origin, aroma_profile"),
    is_custom: Optional[bool] = Query(None, description="Filter by custom varieties only"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List all hop varieties with optional filters."""
    query = select(HopVariety).order_by(HopVariety.name)

    # Apply filters
    if origin:
        query = query.where(HopVariety.origin.ilike(f"%{origin}%"))
    if purpose:
        query = query.where(HopVariety.purpose == purpose)
    if is_custom is not None:
        query = query.where(HopVariety.is_custom == is_custom)
    if search:
        search_pattern = f"%{search}%"
        query = query.where(
            or_(
                HopVariety.name.ilike(search_pattern),
                HopVariety.origin.ilike(search_pattern),
                HopVariety.aroma_profile.ilike(search_pattern),
            )
        )

    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/stats")
async def get_hop_variety_stats(db: AsyncSession = Depends(get_db)):
    """Get statistics about hop varieties."""
    counts = await get_hop_variety_count(db)
    return counts


@router.get("/origins")
async def list_hop_origins(db: AsyncSession = Depends(get_db)):
    """Get list of unique origins/countries."""
    result = await db.execute(
        select(HopVariety.origin)
        .where(HopVariety.origin.isnot(None))
        .distinct()
        .order_by(HopVariety.origin)
    )
    origins = [row[0] for row in result.all()]
    return {"origins": origins}


@router.get("/{variety_id}", response_model=HopVarietyResponse)
async def get_hop_variety(variety_id: int, db: AsyncSession = Depends(get_db)):
    """Get a specific hop variety by ID."""
    variety = await db.get(HopVariety, variety_id)
    if not variety:
        raise HTTPException(status_code=404, detail="Hop variety not found")
    return variety


@router.post("", response_model=HopVarietyResponse, status_code=201)
async def create_hop_variety(
    variety: HopVarietyCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a custom hop variety.

    Custom varieties are marked as is_custom=True and source='custom'.
    They are preserved when refreshing the database from the seed file.
    """
    db_variety = HopVariety(
        name=variety.name,
        origin=variety.origin,
        alpha_acid_low=variety.alpha_acid_low,
        alpha_acid_high=variety.alpha_acid_high,
        beta_acid_low=variety.beta_acid_low,
        beta_acid_high=variety.beta_acid_high,
        purpose=variety.purpose,
        aroma_profile=variety.aroma_profile,
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
async def delete_hop_variety(variety_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a custom hop variety.

    Only custom varieties (is_custom=True) can be deleted.
    Built-in varieties cannot be deleted but will be restored on refresh.
    """
    variety = await db.get(HopVariety, variety_id)
    if not variety:
        raise HTTPException(status_code=404, detail="Hop variety not found")

    if not variety.is_custom:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete built-in hop variety. Use /refresh to restore defaults."
        )

    await db.delete(variety)
    await db.commit()
    return {"status": "deleted", "id": variety_id}


@router.post("/refresh")
async def refresh_hop_varieties(db: AsyncSession = Depends(get_db)):
    """Refresh hop varieties from seed file.

    Re-loads all non-custom varieties from the seed JSON file.
    Custom varieties (is_custom=True) are preserved.
    """
    result = await seed_hop_varieties(db, force=True)
    if not result["success"]:
        raise HTTPException(
            status_code=500,
            detail=result.get("error", "Refresh failed")
        )
    return result
