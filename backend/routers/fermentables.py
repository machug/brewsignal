"""Fermentable API endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Fermentable, FermentableCreate, FermentableResponse
from ..services.fermentable_seeder import seed_fermentables, get_fermentable_count

router = APIRouter(prefix="/api/fermentables", tags=["fermentables"])


@router.get("", response_model=list[FermentableResponse])
async def list_fermentables(
    type: Optional[str] = Query(None, description="Filter by type (base/specialty/adjunct/sugar/extract/fruit/other)"),
    origin: Optional[str] = Query(None, description="Filter by origin/country"),
    maltster: Optional[str] = Query(None, description="Filter by maltster/manufacturer"),
    search: Optional[str] = Query(None, description="Search in name, origin, maltster, flavor_profile"),
    is_custom: Optional[bool] = Query(None, description="Filter by custom fermentables only"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List all fermentables with optional filters."""
    query = select(Fermentable).order_by(Fermentable.name)

    # Apply filters
    if type:
        query = query.where(Fermentable.type == type)
    if origin:
        query = query.where(Fermentable.origin.ilike(f"%{origin}%"))
    if maltster:
        query = query.where(Fermentable.maltster.ilike(f"%{maltster}%"))
    if is_custom is not None:
        query = query.where(Fermentable.is_custom == is_custom)
    if search:
        search_pattern = f"%{search}%"
        query = query.where(
            or_(
                Fermentable.name.ilike(search_pattern),
                Fermentable.origin.ilike(search_pattern),
                Fermentable.maltster.ilike(search_pattern),
                Fermentable.flavor_profile.ilike(search_pattern),
            )
        )

    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/stats")
async def get_fermentable_stats(db: AsyncSession = Depends(get_db)):
    """Get statistics about fermentables."""
    counts = await get_fermentable_count(db)
    return counts


@router.get("/types")
async def list_fermentable_types(db: AsyncSession = Depends(get_db)):
    """Get list of unique fermentable types."""
    result = await db.execute(
        select(Fermentable.type)
        .where(Fermentable.type.isnot(None))
        .distinct()
        .order_by(Fermentable.type)
    )
    types = [row[0] for row in result.all()]
    return {"types": types}


@router.get("/origins")
async def list_fermentable_origins(db: AsyncSession = Depends(get_db)):
    """Get list of unique origins/countries."""
    result = await db.execute(
        select(Fermentable.origin)
        .where(Fermentable.origin.isnot(None))
        .distinct()
        .order_by(Fermentable.origin)
    )
    origins = [row[0] for row in result.all()]
    return {"origins": origins}


@router.get("/maltsters")
async def list_maltsters(db: AsyncSession = Depends(get_db)):
    """Get list of unique maltsters/manufacturers."""
    result = await db.execute(
        select(Fermentable.maltster)
        .where(Fermentable.maltster.isnot(None))
        .distinct()
        .order_by(Fermentable.maltster)
    )
    maltsters = [row[0] for row in result.all()]
    return {"maltsters": maltsters}


@router.get("/{fermentable_id}", response_model=FermentableResponse)
async def get_fermentable(fermentable_id: int, db: AsyncSession = Depends(get_db)):
    """Get a specific fermentable by ID."""
    fermentable = await db.get(Fermentable, fermentable_id)
    if not fermentable:
        raise HTTPException(status_code=404, detail="Fermentable not found")
    return fermentable


@router.post("", response_model=FermentableResponse, status_code=201)
async def create_fermentable(
    fermentable: FermentableCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a custom fermentable.

    Custom fermentables are marked as is_custom=True and source='custom'.
    They are preserved when refreshing the database from the seed file.
    """
    db_fermentable = Fermentable(
        name=fermentable.name,
        type=fermentable.type,
        origin=fermentable.origin,
        maltster=fermentable.maltster,
        color_srm=fermentable.color_srm,
        potential_sg=fermentable.potential_sg,
        max_in_batch_percent=fermentable.max_in_batch_percent,
        diastatic_power=fermentable.diastatic_power,
        flavor_profile=fermentable.flavor_profile,
        substitutes=fermentable.substitutes,
        description=fermentable.description,
        source="custom",
        is_custom=True,
    )
    db.add(db_fermentable)
    await db.commit()
    await db.refresh(db_fermentable)
    return db_fermentable


@router.delete("/{fermentable_id}")
async def delete_fermentable(fermentable_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a custom fermentable.

    Only custom fermentables (is_custom=True) can be deleted.
    Built-in fermentables cannot be deleted but will be restored on refresh.
    """
    fermentable = await db.get(Fermentable, fermentable_id)
    if not fermentable:
        raise HTTPException(status_code=404, detail="Fermentable not found")

    if not fermentable.is_custom:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete built-in fermentable. Use /refresh to restore defaults."
        )

    await db.delete(fermentable)
    await db.commit()
    return {"status": "deleted", "id": fermentable_id}


@router.post("/refresh")
async def refresh_fermentables(db: AsyncSession = Depends(get_db)):
    """Refresh fermentables from seed file.

    Re-loads all non-custom fermentables from the seed JSON file.
    Custom fermentables (is_custom=True) are preserved.
    """
    result = await seed_fermentables(db, force=True)
    if not result["success"]:
        raise HTTPException(
            status_code=500,
            detail=result.get("error", "Refresh failed")
        )
    return result
