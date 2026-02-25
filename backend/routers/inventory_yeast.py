"""Yeast inventory API endpoints."""

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..auth import AuthUser, require_auth
from ..config import get_settings
from ..database import get_db
from ..models import (
    Batch,
    YeastInventory,
    YeastInventoryCreate,
    YeastInventoryHarvest,
    YeastInventoryResponse,
    YeastInventoryUpdate,
    YeastInventoryUse,
    YeastStrain,
)

router = APIRouter(prefix="/api/inventory/yeast", tags=["inventory-yeast"])


def user_owns_yeast(user: AuthUser):
    """Create a SQLAlchemy condition for yeast inventory ownership.

    In LOCAL deployment mode, includes:
    - Yeast explicitly owned by the user
    - Yeast owned by the dummy "local" user (pre-auth data)
    - Unclaimed yeast (user_id IS NULL) for backward compatibility

    In CLOUD deployment mode, strictly filters by user_id.
    """
    settings = get_settings()
    if settings.is_local:
        # LOCAL mode: single-user Pi, no ownership filtering needed
        return True
    return YeastInventory.user_id == user.user_id


@router.get("", response_model=list[YeastInventoryResponse])
async def list_yeast_inventory(
    query_str: Optional[str] = Query(None, alias="query", description="Search by strain name or custom name"),
    form: Optional[str] = Query(None, description="Filter by form (dry, liquid, slant, harvested)"),
    include_expired: bool = Query(False, description="Include expired yeast"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(require_auth),
):
    """List yeast inventory with optional filters."""
    query = (
        select(YeastInventory)
        .options(selectinload(YeastInventory.yeast_strain))
        .where(user_owns_yeast(user))
        .order_by(YeastInventory.expiry_date.asc().nullsfirst())
    )

    if query_str:
        # Search in both yeast strain name and custom name
        query = query.outerjoin(YeastStrain).where(
            or_(
                YeastInventory.custom_name.ilike(f"%{query_str}%"),
                YeastStrain.name.ilike(f"%{query_str}%"),
                YeastStrain.product_id.ilike(f"%{query_str}%"),
            )
        )
    if form:
        query = query.where(YeastInventory.form == form)
    if not include_expired:
        now = datetime.now(timezone.utc)
        query = query.where(
            or_(
                YeastInventory.expiry_date.is_(None),
                YeastInventory.expiry_date > now,
            )
        )

    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/expiring-soon", response_model=list[YeastInventoryResponse])
async def list_expiring_yeast(
    days: int = Query(30, ge=1, le=365, description="Days until expiration"),
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(require_auth),
):
    """Get yeast expiring within N days."""
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(days=days)

    query = (
        select(YeastInventory)
        .options(selectinload(YeastInventory.yeast_strain))
        .where(
            user_owns_yeast(user),
            YeastInventory.expiry_date.is_not(None),
            YeastInventory.expiry_date <= cutoff,
            YeastInventory.expiry_date > now,  # Not already expired
            YeastInventory.quantity > 0,  # Has some left
        )
        .order_by(YeastInventory.expiry_date.asc())
    )

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/summary")
async def get_yeast_summary(
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(require_auth),
):
    """Get summary statistics for yeast inventory."""
    now = datetime.now(timezone.utc)

    # Total counts
    result = await db.execute(
        select(
            func.count(YeastInventory.id).label("total_items"),
            func.sum(YeastInventory.quantity).label("total_quantity"),
        ).where(user_owns_yeast(user), YeastInventory.quantity > 0)
    )
    row = result.one()

    # Expiring soon (within 30 days)
    cutoff = now + timedelta(days=30)
    expiring_result = await db.execute(
        select(func.count(YeastInventory.id)).where(
            user_owns_yeast(user),
            YeastInventory.expiry_date.is_not(None),
            YeastInventory.expiry_date <= cutoff,
            YeastInventory.expiry_date > now,
            YeastInventory.quantity > 0,
        )
    )
    expiring_count = expiring_result.scalar() or 0

    # Already expired
    expired_result = await db.execute(
        select(func.count(YeastInventory.id)).where(
            user_owns_yeast(user),
            YeastInventory.expiry_date.is_not(None),
            YeastInventory.expiry_date <= now,
            YeastInventory.quantity > 0,
        )
    )
    expired_count = expired_result.scalar() or 0

    return {
        "total_items": row.total_items or 0,
        "total_quantity": row.total_quantity or 0,
        "expiring_soon": expiring_count,
        "expired": expired_count,
    }


@router.get("/{yeast_id}", response_model=YeastInventoryResponse)
async def get_yeast_inventory(
    yeast_id: int,
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(require_auth),
):
    """Get a specific yeast inventory item by ID."""
    query = (
        select(YeastInventory)
        .options(selectinload(YeastInventory.yeast_strain))
        .where(YeastInventory.id == yeast_id, user_owns_yeast(user))
    )
    result = await db.execute(query)
    yeast = result.scalar_one_or_none()

    if not yeast:
        raise HTTPException(status_code=404, detail="Yeast inventory item not found")
    return yeast


@router.post("", response_model=YeastInventoryResponse, status_code=201)
async def create_yeast_inventory(
    yeast: YeastInventoryCreate,
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(require_auth),
):
    """Create a new yeast inventory item."""
    # Validate that either yeast_strain_id or custom_name is provided
    if not yeast.yeast_strain_id and not yeast.custom_name:
        raise HTTPException(
            status_code=400,
            detail="Either yeast_strain_id or custom_name must be provided"
        )

    # If yeast_strain_id provided, verify it exists
    if yeast.yeast_strain_id:
        strain_result = await db.execute(
            select(YeastStrain).where(YeastStrain.id == yeast.yeast_strain_id)
        )
        if not strain_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Yeast strain not found")

    db_yeast = YeastInventory(
        yeast_strain_id=yeast.yeast_strain_id,
        custom_name=yeast.custom_name,
        quantity=yeast.quantity,
        form=yeast.form,
        manufacture_date=yeast.manufacture_date,
        expiry_date=yeast.expiry_date,
        generation=yeast.generation,
        source_batch_id=yeast.source_batch_id,
        storage_location=yeast.storage_location,
        supplier=yeast.supplier,
        lot_number=yeast.lot_number,
        notes=yeast.notes,
        user_id=user.user_id,
    )
    db.add(db_yeast)
    await db.commit()

    # Re-fetch with relationships
    query = (
        select(YeastInventory)
        .options(selectinload(YeastInventory.yeast_strain))
        .where(YeastInventory.id == db_yeast.id)
    )
    result = await db.execute(query)
    return result.scalar_one()


@router.put("/{yeast_id}", response_model=YeastInventoryResponse)
async def update_yeast_inventory(
    yeast_id: int,
    yeast: YeastInventoryUpdate,
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(require_auth),
):
    """Update a yeast inventory item."""
    query = (
        select(YeastInventory)
        .options(selectinload(YeastInventory.yeast_strain))
        .where(YeastInventory.id == yeast_id, user_owns_yeast(user))
    )
    result = await db.execute(query)
    db_yeast = result.scalar_one_or_none()

    if not db_yeast:
        raise HTTPException(status_code=404, detail="Yeast inventory item not found")

    # Update fields if provided
    update_data = yeast.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_yeast, key, value)

    await db.commit()
    await db.refresh(db_yeast)
    return db_yeast


@router.patch("/{yeast_id}/use", response_model=YeastInventoryResponse)
async def use_yeast(
    yeast_id: int,
    usage: YeastInventoryUse,
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(require_auth),
):
    """Use yeast (decrement quantity)."""
    query = (
        select(YeastInventory)
        .options(selectinload(YeastInventory.yeast_strain))
        .where(YeastInventory.id == yeast_id, user_owns_yeast(user))
    )
    result = await db.execute(query)
    db_yeast = result.scalar_one_or_none()

    if not db_yeast:
        raise HTTPException(status_code=404, detail="Yeast inventory item not found")

    if db_yeast.quantity < usage.quantity:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot use {usage.quantity} - only {db_yeast.quantity} available"
        )

    db_yeast.quantity -= usage.quantity
    await db.commit()
    await db.refresh(db_yeast)
    return db_yeast


@router.post("/harvest", response_model=YeastInventoryResponse, status_code=201)
async def harvest_yeast(
    harvest: YeastInventoryHarvest,
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(require_auth),
):
    """Create new yeast inventory from harvested batch."""
    # Get the batch to find its yeast strain
    batch_result = await db.execute(
        select(Batch)
        .options(selectinload(Batch.yeast_strain), selectinload(Batch.recipe))
        .where(Batch.id == harvest.source_batch_id)
    )
    batch = batch_result.scalar_one_or_none()

    if not batch:
        raise HTTPException(status_code=404, detail="Source batch not found")

    # Determine yeast strain from batch
    yeast_strain_id = batch.yeast_strain_id
    custom_name = None

    if not yeast_strain_id and batch.recipe:
        # Try to get yeast info from recipe
        custom_name = batch.recipe.yeast_name

    # Find if there's existing harvested yeast from this batch to determine generation
    existing_result = await db.execute(
        select(func.max(YeastInventory.generation))
        .where(YeastInventory.source_batch_id == harvest.source_batch_id)
    )
    max_gen = existing_result.scalar()
    generation = (max_gen or 0) + 1

    db_yeast = YeastInventory(
        yeast_strain_id=yeast_strain_id,
        custom_name=custom_name or f"Harvested from Batch #{batch.id}",
        quantity=harvest.quantity,
        form="harvested",
        generation=generation,
        source_batch_id=harvest.source_batch_id,
        notes=harvest.notes,
        user_id=user.user_id,
    )
    db.add(db_yeast)
    await db.commit()

    # Re-fetch with relationships
    query = (
        select(YeastInventory)
        .options(selectinload(YeastInventory.yeast_strain))
        .where(YeastInventory.id == db_yeast.id)
    )
    result = await db.execute(query)
    return result.scalar_one()


@router.delete("/{yeast_id}", status_code=204)
async def delete_yeast_inventory(
    yeast_id: int,
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(require_auth),
):
    """Delete a yeast inventory item."""
    result = await db.execute(
        select(YeastInventory).where(YeastInventory.id == yeast_id, user_owns_yeast(user))
    )
    db_yeast = result.scalar_one_or_none()

    if not db_yeast:
        raise HTTPException(status_code=404, detail="Yeast inventory item not found")

    await db.delete(db_yeast)
    await db.commit()
