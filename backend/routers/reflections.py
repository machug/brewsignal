"""Batch reflections API endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from ..auth import AuthUser, require_auth
from ..database import get_db
from ..models import (
    BatchReflection,
    BatchReflectionUpdate,
    BatchReflectionResponse,
)
from .batches import get_user_batch

router = APIRouter(prefix="/api/batches", tags=["reflections"])


class ReflectionCreateBody(BaseModel):
    """Request body for creating a reflection (batch_id comes from URL)."""
    phase: str
    metrics: Optional[dict] = None
    what_went_well: Optional[str] = None
    what_went_wrong: Optional[str] = None
    lessons_learned: Optional[str] = None
    next_time_changes: Optional[str] = None

    @field_validator("phase")
    @classmethod
    def validate_phase(cls, v: str) -> str:
        valid = ["brew_day", "fermentation", "packaging", "conditioning"]
        if v not in valid:
            raise ValueError(f"phase must be one of: {', '.join(valid)}")
        return v


@router.post("/{batch_id}/reflections", response_model=BatchReflectionResponse, status_code=201)
async def create_reflection(
    batch_id: int,
    data: ReflectionCreateBody,
    user: AuthUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Create a new reflection for a batch phase."""
    # Verify batch exists and user owns it
    await get_user_batch(batch_id, user, db)

    # Check for existing reflection for this phase
    existing = await db.execute(
        select(BatchReflection).where(
            BatchReflection.batch_id == batch_id,
            BatchReflection.phase == data.phase
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail=f"Reflection for phase '{data.phase}' already exists. Use PUT to update."
        )

    reflection = BatchReflection(
        batch_id=batch_id,
        user_id=user.user_id,
        phase=data.phase,
        metrics=data.metrics,
        what_went_well=data.what_went_well,
        what_went_wrong=data.what_went_wrong,
        lessons_learned=data.lessons_learned,
        next_time_changes=data.next_time_changes,
    )
    db.add(reflection)
    await db.commit()
    await db.refresh(reflection)
    return reflection


@router.get("/{batch_id}/reflections", response_model=list[BatchReflectionResponse])
async def list_reflections(
    batch_id: int,
    user: AuthUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """List all reflections for a batch."""
    await get_user_batch(batch_id, user, db)

    result = await db.execute(
        select(BatchReflection)
        .where(BatchReflection.batch_id == batch_id)
        .order_by(BatchReflection.created_at)
    )
    return result.scalars().all()


@router.get("/{batch_id}/reflections/{phase}", response_model=BatchReflectionResponse)
async def get_reflection_by_phase(
    batch_id: int,
    phase: str,
    user: AuthUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific phase reflection for a batch."""
    await get_user_batch(batch_id, user, db)

    result = await db.execute(
        select(BatchReflection).where(
            BatchReflection.batch_id == batch_id,
            BatchReflection.phase == phase
        )
    )
    reflection = result.scalar_one_or_none()
    if not reflection:
        raise HTTPException(status_code=404, detail=f"No reflection found for phase '{phase}'")
    return reflection


@router.put("/{batch_id}/reflections/{reflection_id}", response_model=BatchReflectionResponse)
async def update_reflection(
    batch_id: int,
    reflection_id: int,
    data: BatchReflectionUpdate,
    user: AuthUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Update a reflection."""
    await get_user_batch(batch_id, user, db)

    result = await db.execute(
        select(BatchReflection).where(
            BatchReflection.id == reflection_id,
            BatchReflection.batch_id == batch_id
        )
    )
    reflection = result.scalar_one_or_none()
    if not reflection:
        raise HTTPException(status_code=404, detail="Reflection not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(reflection, field, value)

    await db.commit()
    await db.refresh(reflection)
    return reflection
