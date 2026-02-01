"""Equipment inventory API endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import AuthUser, require_auth
from ..config import get_settings
from ..database import get_db
from ..models import (
    Equipment,
    EquipmentCreate,
    EquipmentResponse,
    EquipmentUpdate,
)

router = APIRouter(prefix="/api/inventory/equipment", tags=["inventory-equipment"])


def user_owns_equipment(user: AuthUser):
    """Create a SQLAlchemy condition for equipment ownership.

    In LOCAL deployment mode, includes:
    - Equipment explicitly owned by the user
    - Equipment owned by the dummy "local" user (pre-auth data)
    - Unclaimed equipment (user_id IS NULL) for backward compatibility

    In CLOUD deployment mode, strictly filters by user_id.
    """
    settings = get_settings()
    if settings.is_local:
        return or_(
            Equipment.user_id == user.user_id,
            Equipment.user_id == "local",
            Equipment.user_id.is_(None),
        )
    return Equipment.user_id == user.user_id


@router.get("", response_model=list[EquipmentResponse])
async def list_equipment(
    type: Optional[str] = Query(None, description="Filter by equipment type"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(require_auth),
):
    """List equipment with optional filters."""
    query = select(Equipment).where(user_owns_equipment(user)).order_by(Equipment.name)

    if type:
        query = query.where(Equipment.type == type)
    if is_active is not None:
        query = query.where(Equipment.is_active == is_active)

    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/types", response_model=list[str])
async def list_equipment_types(
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(require_auth),
):
    """Get unique equipment types in inventory."""
    query = select(Equipment.type).where(user_owns_equipment(user)).distinct().order_by(Equipment.type)
    result = await db.execute(query)
    return [row[0] for row in result.all()]


@router.get("/{equipment_id}", response_model=EquipmentResponse)
async def get_equipment(
    equipment_id: int,
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(require_auth),
):
    """Get a specific equipment item by ID."""
    result = await db.execute(
        select(Equipment).where(Equipment.id == equipment_id, user_owns_equipment(user))
    )
    equipment = result.scalar_one_or_none()

    if not equipment:
        raise HTTPException(status_code=404, detail="Equipment not found")
    return equipment


@router.post("", response_model=EquipmentResponse, status_code=201)
async def create_equipment(
    equipment: EquipmentCreate,
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(require_auth),
):
    """Create a new equipment item."""
    db_equipment = Equipment(
        name=equipment.name,
        type=equipment.type,
        brand=equipment.brand,
        model=equipment.model,
        capacity_liters=equipment.capacity_liters,
        capacity_kg=equipment.capacity_kg,
        is_active=equipment.is_active,
        notes=equipment.notes,
        user_id=user.user_id,
    )
    db.add(db_equipment)
    await db.commit()
    await db.refresh(db_equipment)
    return db_equipment


@router.put("/{equipment_id}", response_model=EquipmentResponse)
async def update_equipment(
    equipment_id: int,
    equipment: EquipmentUpdate,
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(require_auth),
):
    """Update an equipment item."""
    result = await db.execute(
        select(Equipment).where(Equipment.id == equipment_id, user_owns_equipment(user))
    )
    db_equipment = result.scalar_one_or_none()

    if not db_equipment:
        raise HTTPException(status_code=404, detail="Equipment not found")

    # Update fields if provided
    update_data = equipment.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_equipment, key, value)

    await db.commit()
    await db.refresh(db_equipment)
    return db_equipment


@router.delete("/{equipment_id}", status_code=204)
async def delete_equipment(
    equipment_id: int,
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(require_auth),
):
    """Delete an equipment item."""
    result = await db.execute(
        select(Equipment).where(Equipment.id == equipment_id, user_owns_equipment(user))
    )
    db_equipment = result.scalar_one_or_none()

    if not db_equipment:
        raise HTTPException(status_code=404, detail="Equipment not found")

    await db.delete(db_equipment)
    await db.commit()
