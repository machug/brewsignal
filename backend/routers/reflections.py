"""Batch reflections API endpoints."""

import asyncio
import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from typing import Optional

from ..auth import AuthUser, require_auth
from ..database import get_db
from ..models import (
    Batch,
    BatchReflection,
    BatchReflectionUpdate,
    BatchReflectionResponse,
    Recipe,
)
from .batches import get_user_batch

logger = logging.getLogger(__name__)
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


async def _store_reflection_memory(
    db: AsyncSession,
    reflection: BatchReflection,
    batch: Batch,
    user_id: str,
) -> None:
    """Store reflection as a memory in mem0 (non-blocking, graceful failure)."""
    try:
        from backend.services.memory import add_memory
        from backend.routers.assistant import get_llm_config

        # Only store if there's meaningful content
        if not (reflection.lessons_learned or reflection.what_went_well or reflection.what_went_wrong):
            return

        llm_config = await get_llm_config(db)
        if not llm_config.is_configured():
            logger.debug("LLM not configured, skipping memory storage for reflection")
            return

        recipe_name = batch.recipe.name if batch.recipe else "unknown recipe"
        messages = [
            {
                "role": "user",
                "content": f"I just completed the {reflection.phase} phase for batch '{batch.name}' ({recipe_name})."
            },
            {"role": "assistant", "content": "How did it go?"},
            {
                "role": "user",
                "content": f"""What went well: {reflection.what_went_well or 'N/A'}
What went wrong: {reflection.what_went_wrong or 'N/A'}
Lessons learned: {reflection.lessons_learned or 'N/A'}
Next time: {reflection.next_time_changes or 'N/A'}"""
            }
        ]
        await add_memory(
            messages=messages,
            user_id=user_id,
            llm_config=llm_config,
            metadata={
                "type": "reflection",
                "batch_id": batch.id,
                "batch_name": batch.name,
                "phase": reflection.phase,
            }
        )
        logger.info(f"Stored reflection memory for batch {batch.id} phase {reflection.phase}")
    except Exception as e:
        # Non-blocking: log and continue, don't fail the request
        logger.warning(f"Failed to store reflection memory: {e}")


@router.post("/{batch_id}/reflections", response_model=BatchReflectionResponse, status_code=201)
async def create_reflection(
    batch_id: int,
    data: ReflectionCreateBody,
    user: AuthUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Create a new reflection for a batch phase."""
    # Verify batch exists and user owns it, with recipe eagerly loaded for memory
    result = await db.execute(
        select(Batch)
        .options(selectinload(Batch.recipe))
        .where(Batch.id == batch_id)
    )
    batch = result.scalar_one_or_none()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

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

    # Store memory in background (non-blocking)
    asyncio.create_task(_store_reflection_memory(db, reflection, batch, user.user_id))

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
    # Fetch batch with recipe eagerly loaded for memory
    batch_result = await db.execute(
        select(Batch)
        .options(selectinload(Batch.recipe))
        .where(Batch.id == batch_id)
    )
    batch = batch_result.scalar_one_or_none()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

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

    # Store updated memory in background (non-blocking)
    asyncio.create_task(_store_reflection_memory(db, reflection, batch, user.user_id))

    return reflection
