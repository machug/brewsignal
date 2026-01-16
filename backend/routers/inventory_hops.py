"""Hop inventory API endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import (
    HopInventory,
    HopInventoryAdjust,
    HopInventoryCreate,
    HopInventoryResponse,
    HopInventoryUpdate,
)

router = APIRouter(prefix="/api/inventory/hops", tags=["inventory-hops"])


@router.get("", response_model=list[HopInventoryResponse])
async def list_hop_inventory(
    variety: Optional[str] = Query(None, description="Filter by variety name (partial match)"),
    form: Optional[str] = Query(None, description="Filter by form (pellet, leaf, plug)"),
    min_amount_grams: Optional[float] = Query(None, description="Minimum amount in grams"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List hop inventory with optional filters."""
    query = select(HopInventory).order_by(HopInventory.variety)

    if variety:
        query = query.where(HopInventory.variety.ilike(f"%{variety}%"))
    if form:
        query = query.where(HopInventory.form == form)
    if min_amount_grams is not None:
        query = query.where(HopInventory.amount_grams >= min_amount_grams)

    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/varieties", response_model=list[str])
async def list_hop_varieties(db: AsyncSession = Depends(get_db)):
    """Get unique hop varieties in inventory."""
    query = select(HopInventory.variety).distinct().order_by(HopInventory.variety)
    result = await db.execute(query)
    return [row[0] for row in result.all()]


@router.get("/summary")
async def get_hop_summary(db: AsyncSession = Depends(get_db)):
    """Get summary statistics for hop inventory."""
    # Total count and weight
    result = await db.execute(
        select(
            func.count(HopInventory.id).label("total_items"),
            func.sum(HopInventory.amount_grams).label("total_grams"),
            func.count(func.distinct(HopInventory.variety)).label("unique_varieties"),
        )
    )
    row = result.one()
    return {
        "total_items": row.total_items or 0,
        "total_grams": round(row.total_grams or 0, 1),
        "unique_varieties": row.unique_varieties or 0,
    }


@router.get("/{hop_id}", response_model=HopInventoryResponse)
async def get_hop_inventory(hop_id: int, db: AsyncSession = Depends(get_db)):
    """Get a specific hop inventory item by ID."""
    result = await db.execute(select(HopInventory).where(HopInventory.id == hop_id))
    hop = result.scalar_one_or_none()

    if not hop:
        raise HTTPException(status_code=404, detail="Hop inventory item not found")
    return hop


@router.post("", response_model=HopInventoryResponse, status_code=201)
async def create_hop_inventory(
    hop: HopInventoryCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new hop inventory item."""
    db_hop = HopInventory(
        variety=hop.variety,
        amount_grams=hop.amount_grams,
        alpha_acid_percent=hop.alpha_acid_percent,
        crop_year=hop.crop_year,
        form=hop.form,
        storage_location=hop.storage_location,
        purchase_date=hop.purchase_date,
        supplier=hop.supplier,
        lot_number=hop.lot_number,
        notes=hop.notes,
    )
    db.add(db_hop)
    await db.commit()
    await db.refresh(db_hop)
    return db_hop


@router.put("/{hop_id}", response_model=HopInventoryResponse)
async def update_hop_inventory(
    hop_id: int,
    hop: HopInventoryUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update a hop inventory item."""
    result = await db.execute(select(HopInventory).where(HopInventory.id == hop_id))
    db_hop = result.scalar_one_or_none()

    if not db_hop:
        raise HTTPException(status_code=404, detail="Hop inventory item not found")

    # Update fields if provided
    update_data = hop.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_hop, key, value)

    await db.commit()
    await db.refresh(db_hop)
    return db_hop


@router.patch("/{hop_id}/adjust", response_model=HopInventoryResponse)
async def adjust_hop_amount(
    hop_id: int,
    adjustment: HopInventoryAdjust,
    db: AsyncSession = Depends(get_db),
):
    """Quick adjust hop amount (add or subtract grams)."""
    result = await db.execute(select(HopInventory).where(HopInventory.id == hop_id))
    db_hop = result.scalar_one_or_none()

    if not db_hop:
        raise HTTPException(status_code=404, detail="Hop inventory item not found")

    new_amount = db_hop.amount_grams + adjustment.delta_grams
    if new_amount < 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot subtract {abs(adjustment.delta_grams)}g - only {db_hop.amount_grams}g available"
        )

    db_hop.amount_grams = new_amount
    await db.commit()
    await db.refresh(db_hop)
    return db_hop


@router.delete("/{hop_id}", status_code=204)
async def delete_hop_inventory(hop_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a hop inventory item."""
    result = await db.execute(select(HopInventory).where(HopInventory.id == hop_id))
    db_hop = result.scalar_one_or_none()

    if not db_hop:
        raise HTTPException(status_code=404, detail="Hop inventory item not found")

    await db.delete(db_hop)
    await db.commit()
