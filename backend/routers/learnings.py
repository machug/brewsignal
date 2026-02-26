"""API endpoints for browsing and managing brewing learnings."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.auth import AuthUser, require_auth
from backend.models import (
    BrewingLearning, BrewingLearningResponse, BrewingLearningUpdate,
    LEARNING_CATEGORIES,
)

router = APIRouter(prefix="/api/learnings", tags=["learnings"])


@router.get("", response_model=list[BrewingLearningResponse])
async def list_learnings(
    category: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(require_auth),
):
    """List all brewing learnings, optionally filtered by category."""
    query = select(BrewingLearning).where(BrewingLearning.user_id == user.id)
    if category:
        if category not in LEARNING_CATEGORIES:
            raise HTTPException(400, f"Invalid category. Must be one of: {', '.join(LEARNING_CATEGORIES)}")
        query = query.where(BrewingLearning.category == category)
    query = query.order_by(BrewingLearning.created_at.desc())

    result = await db.execute(query)
    return result.scalars().all()


@router.put("/{learning_id}", response_model=BrewingLearningResponse)
async def update_learning(
    learning_id: int,
    update: BrewingLearningUpdate,
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(require_auth),
):
    """Update a brewing learning."""
    result = await db.execute(
        select(BrewingLearning).where(
            BrewingLearning.id == learning_id,
            BrewingLearning.user_id == user.id,
        )
    )
    learning = result.scalar_one_or_none()
    if not learning:
        raise HTTPException(404, "Learning not found")

    update_data = update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(learning, field, value)

    await db.commit()
    await db.refresh(learning)
    return learning


@router.delete("/{learning_id}", status_code=204)
async def delete_learning(
    learning_id: int,
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(require_auth),
):
    """Delete a brewing learning."""
    result = await db.execute(
        select(BrewingLearning).where(
            BrewingLearning.id == learning_id,
            BrewingLearning.user_id == user.id,
        )
    )
    learning = result.scalar_one_or_none()
    if not learning:
        raise HTTPException(404, "Learning not found")

    # Best-effort Mem0 cleanup
    if learning.mem0_memory_id:
        try:
            from backend.services.memory import delete_memory
            await delete_memory(learning.mem0_memory_id)
        except Exception:
            pass

    await db.delete(learning)
    await db.commit()
