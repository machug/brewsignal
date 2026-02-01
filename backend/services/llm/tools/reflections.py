"""Batch reflection tools for the AI brewing assistant."""

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Batch, BatchReflection


async def create_batch_reflection(
    db: AsyncSession,
    batch_id: int,
    phase: str,
    metrics: Optional[dict] = None,
    what_went_well: Optional[str] = None,
    what_went_wrong: Optional[str] = None,
    lessons_learned: Optional[str] = None,
    next_time_changes: Optional[str] = None,
    user_id: Optional[str] = None,
) -> dict[str, Any]:
    """Create a reflection for a batch phase.

    Args:
        db: Database session
        batch_id: ID of the batch to create reflection for
        phase: Phase of the batch (brew_day, fermentation, packaging, conditioning)
        metrics: Optional dict of phase-specific metrics
        what_went_well: Things that went well during this phase
        what_went_wrong: Things that went wrong during this phase
        lessons_learned: Lessons learned from this phase
        next_time_changes: Changes to make next time
        user_id: User ID for multi-tenant isolation

    Returns:
        Dict with success status and created reflection or error message
    """
    # Verify batch exists
    batch_result = await db.execute(select(Batch).where(Batch.id == batch_id))
    batch = batch_result.scalar_one_or_none()
    if not batch:
        return {"success": False, "error": f"Batch {batch_id} not found"}

    # Check for existing reflection for this phase
    existing = await db.execute(
        select(BatchReflection).where(
            BatchReflection.batch_id == batch_id,
            BatchReflection.phase == phase
        )
    )
    if existing.scalar_one_or_none():
        return {"success": False, "error": f"Reflection for phase '{phase}' already exists"}

    reflection = BatchReflection(
        batch_id=batch_id,
        user_id=user_id,
        phase=phase,
        metrics=metrics,
        what_went_well=what_went_well,
        what_went_wrong=what_went_wrong,
        lessons_learned=lessons_learned,
        next_time_changes=next_time_changes,
    )
    db.add(reflection)
    await db.commit()
    await db.refresh(reflection)

    return {
        "success": True,
        "reflection": {
            "id": reflection.id,
            "batch_id": reflection.batch_id,
            "phase": reflection.phase,
            "metrics": reflection.metrics,
            "what_went_well": reflection.what_went_well,
            "what_went_wrong": reflection.what_went_wrong,
            "lessons_learned": reflection.lessons_learned,
            "next_time_changes": reflection.next_time_changes,
            "ai_summary": reflection.ai_summary,
            "created_at": reflection.created_at.isoformat() if reflection.created_at else None,
        }
    }


async def get_batch_reflections(
    db: AsyncSession,
    batch_id: int,
    phase: Optional[str] = None,
    user_id: Optional[str] = None,
) -> dict[str, Any]:
    """Get reflections for a batch, optionally filtered by phase.

    Args:
        db: Database session
        batch_id: ID of the batch to get reflections for
        phase: Optional phase to filter by
        user_id: User ID for multi-tenant isolation

    Returns:
        Dict with count and list of reflections
    """
    query = select(BatchReflection).where(BatchReflection.batch_id == batch_id)
    if phase:
        query = query.where(BatchReflection.phase == phase)
    query = query.order_by(BatchReflection.created_at)

    result = await db.execute(query)
    reflections = result.scalars().all()

    return {
        "count": len(reflections),
        "reflections": [
            {
                "id": r.id,
                "batch_id": r.batch_id,
                "phase": r.phase,
                "metrics": r.metrics,
                "what_went_well": r.what_went_well,
                "what_went_wrong": r.what_went_wrong,
                "lessons_learned": r.lessons_learned,
                "next_time_changes": r.next_time_changes,
                "ai_summary": r.ai_summary,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in reflections
        ]
    }


async def update_batch_reflection(
    db: AsyncSession,
    reflection_id: int,
    metrics: Optional[dict] = None,
    what_went_well: Optional[str] = None,
    what_went_wrong: Optional[str] = None,
    lessons_learned: Optional[str] = None,
    next_time_changes: Optional[str] = None,
    user_id: Optional[str] = None,
) -> dict[str, Any]:
    """Update an existing batch reflection.

    Args:
        db: Database session
        reflection_id: ID of the reflection to update
        metrics: Optional dict of phase-specific metrics
        what_went_well: Things that went well during this phase
        what_went_wrong: Things that went wrong during this phase
        lessons_learned: Lessons learned from this phase
        next_time_changes: Changes to make next time
        user_id: User ID for multi-tenant isolation

    Returns:
        Dict with success status and updated reflection or error message
    """
    result = await db.execute(
        select(BatchReflection).where(BatchReflection.id == reflection_id)
    )
    reflection = result.scalar_one_or_none()
    if not reflection:
        return {"success": False, "error": f"Reflection {reflection_id} not found"}

    # Only update fields that are provided (not None)
    if metrics is not None:
        reflection.metrics = metrics
    if what_went_well is not None:
        reflection.what_went_well = what_went_well
    if what_went_wrong is not None:
        reflection.what_went_wrong = what_went_wrong
    if lessons_learned is not None:
        reflection.lessons_learned = lessons_learned
    if next_time_changes is not None:
        reflection.next_time_changes = next_time_changes

    await db.commit()
    await db.refresh(reflection)

    return {
        "success": True,
        "reflection": {
            "id": reflection.id,
            "batch_id": reflection.batch_id,
            "phase": reflection.phase,
            "metrics": reflection.metrics,
            "what_went_well": reflection.what_went_well,
            "what_went_wrong": reflection.what_went_wrong,
            "lessons_learned": reflection.lessons_learned,
            "next_time_changes": reflection.next_time_changes,
            "ai_summary": reflection.ai_summary,
            "updated_at": reflection.updated_at.isoformat() if reflection.updated_at else None,
        }
    }
