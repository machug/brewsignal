"""Yeast strain API endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import YeastStrain, YeastStrainCreate, YeastStrainResponse
from ..services.yeast_seeder import seed_yeast_strains, get_yeast_strain_count

router = APIRouter(prefix="/api/yeast-strains", tags=["yeast-strains"])


@router.get("", response_model=list[YeastStrainResponse])
async def list_yeast_strains(
    type: Optional[str] = Query(None, description="Filter by type (ale/lager/wine/wild/hybrid)"),
    producer: Optional[str] = Query(None, description="Filter by producer/lab name"),
    form: Optional[str] = Query(None, description="Filter by form (dry/liquid/slant)"),
    search: Optional[str] = Query(None, description="Search in name, producer, product_id"),
    is_custom: Optional[bool] = Query(None, description="Filter by custom strains only"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List all yeast strains with optional filters."""
    query = select(YeastStrain).order_by(YeastStrain.producer, YeastStrain.name)

    # Apply filters
    if type:
        query = query.where(YeastStrain.type == type)
    if producer:
        query = query.where(YeastStrain.producer.ilike(f"%{producer}%"))
    if form:
        query = query.where(YeastStrain.form == form)
    if is_custom is not None:
        query = query.where(YeastStrain.is_custom == is_custom)
    if search:
        search_pattern = f"%{search}%"
        query = query.where(
            or_(
                YeastStrain.name.ilike(search_pattern),
                YeastStrain.producer.ilike(search_pattern),
                YeastStrain.product_id.ilike(search_pattern),
            )
        )

    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/stats")
async def get_yeast_strain_stats(db: AsyncSession = Depends(get_db)):
    """Get statistics about yeast strains."""
    counts = await get_yeast_strain_count(db)
    return counts


@router.get("/producers")
async def list_yeast_producers(db: AsyncSession = Depends(get_db)):
    """Get list of unique producers/labs."""
    result = await db.execute(
        select(YeastStrain.producer)
        .where(YeastStrain.producer.isnot(None))
        .distinct()
        .order_by(YeastStrain.producer)
    )
    producers = [row[0] for row in result.all()]
    return {"producers": producers}


@router.get("/{strain_id}", response_model=YeastStrainResponse)
async def get_yeast_strain(strain_id: int, db: AsyncSession = Depends(get_db)):
    """Get a specific yeast strain by ID."""
    strain = await db.get(YeastStrain, strain_id)
    if not strain:
        raise HTTPException(status_code=404, detail="Yeast strain not found")
    return strain


@router.post("", response_model=YeastStrainResponse, status_code=201)
async def create_yeast_strain(
    strain: YeastStrainCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a custom yeast strain.

    Custom strains are marked as is_custom=True and source='custom'.
    They are preserved when refreshing the database from the seed file.
    """
    db_strain = YeastStrain(
        name=strain.name,
        producer=strain.producer,
        product_id=strain.product_id,
        type=strain.type,
        form=strain.form,
        attenuation_low=strain.attenuation_low,
        attenuation_high=strain.attenuation_high,
        temp_low=strain.temp_low,
        temp_high=strain.temp_high,
        alcohol_tolerance=strain.alcohol_tolerance,
        flocculation=strain.flocculation,
        description=strain.description,
        source="custom",
        is_custom=True,
    )
    db.add(db_strain)
    await db.commit()
    await db.refresh(db_strain)
    return db_strain


@router.delete("/{strain_id}")
async def delete_yeast_strain(strain_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a custom yeast strain.

    Only custom strains (is_custom=True) can be deleted.
    Built-in strains cannot be deleted but will be restored on refresh.
    """
    strain = await db.get(YeastStrain, strain_id)
    if not strain:
        raise HTTPException(status_code=404, detail="Yeast strain not found")

    if not strain.is_custom:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete built-in yeast strain. Use /refresh to restore defaults."
        )

    await db.delete(strain)
    await db.commit()
    return {"status": "deleted", "id": strain_id}


@router.post("/refresh")
async def refresh_yeast_strains(db: AsyncSession = Depends(get_db)):
    """Refresh yeast strains from seed file.

    Re-loads all non-custom strains from the seed JSON file.
    Custom strains (is_custom=True) are preserved.
    """
    result = await seed_yeast_strains(db, force=True)
    if not result["success"]:
        raise HTTPException(
            status_code=500,
            detail=result.get("error", "Refresh failed")
        )
    return result
