"""Tasting note tools for the AI brewing assistant."""

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.models import Batch, TastingNote, Recipe


async def start_tasting_session(
    db: AsyncSession,
    batch_id: int,
    user_id: Optional[str] = None,
) -> dict[str, Any]:
    """Start a guided tasting session for a batch.

    Returns batch context including recipe, style, and previous tastings.

    Args:
        db: Database session
        batch_id: ID of the batch to start tasting session for
        user_id: User ID for multi-tenant isolation

    Returns:
        Dict with batch context for guided tasting or error message
    """
    result = await db.execute(
        select(Batch)
        .options(
            selectinload(Batch.recipe).selectinload(Recipe.style),
            selectinload(Batch.tasting_notes)
        )
        .where(Batch.id == batch_id)
    )
    batch = result.scalar_one_or_none()
    if not batch:
        return {"success": False, "error": f"Batch {batch_id} not found"}

    days_since_packaging = None
    if batch.packaged_at:
        days_since_packaging = (datetime.now(timezone.utc) - batch.packaged_at).days

    style_info = None
    if batch.recipe and batch.recipe.style:
        style = batch.recipe.style
        style_info = {
            "name": style.name,
            "category": style.category,
            "type": style.type,
            "description": style.description,
            "comments": style.comments,
            # Vital statistics for style compliance
            "og_range": [style.og_min, style.og_max] if style.og_min else None,
            "fg_range": [style.fg_min, style.fg_max] if style.fg_min else None,
            "ibu_range": [style.ibu_min, style.ibu_max] if style.ibu_min else None,
            "abv_range": [style.abv_min, style.abv_max] if style.abv_min else None,
            "srm_range": [style.srm_min, style.srm_max] if style.srm_min else None,
        }

    previous_tastings = []
    for note in (batch.tasting_notes or []):
        previous_tastings.append({
            "tasted_at": note.tasted_at.isoformat() if note.tasted_at else None,
            "total_score": note.total_score,
            "days_since_packaging": note.days_since_packaging,
        })

    return {
        "success": True,
        "batch": {
            "id": batch.id,
            "name": batch.name,
            "recipe_name": batch.recipe.name if batch.recipe else None,
            "status": batch.status,
            "measured_og": batch.measured_og,
            "measured_fg": batch.measured_fg,
            "measured_abv": batch.measured_abv,
            "packaged_at": batch.packaged_at.isoformat() if batch.packaged_at else None,
            "days_since_packaging": days_since_packaging,
        },
        "style_guidelines": style_info,
        "previous_tastings": previous_tastings,
        "tasting_count": len(previous_tastings),
    }


async def save_tasting_note(
    db: AsyncSession,
    batch_id: int,
    appearance_score: int,
    aroma_score: int,
    flavor_score: int,
    mouthfeel_score: int,
    overall_score: int,
    appearance_notes: Optional[str] = None,
    aroma_notes: Optional[str] = None,
    flavor_notes: Optional[str] = None,
    mouthfeel_notes: Optional[str] = None,
    overall_notes: Optional[str] = None,
    days_since_packaging: Optional[int] = None,
    serving_temp_c: Optional[float] = None,
    glassware: Optional[str] = None,
    to_style: Optional[bool] = None,
    style_deviation_notes: Optional[str] = None,
    ai_suggestions: Optional[str] = None,
    interview_transcript: Optional[dict] = None,
    user_id: Optional[str] = None,
) -> dict[str, Any]:
    """Save a complete tasting note for a batch.

    Args:
        db: Database session
        batch_id: ID of the batch to add tasting note for
        appearance_score: Appearance score (1-5)
        aroma_score: Aroma score (1-5)
        flavor_score: Flavor score (1-5)
        mouthfeel_score: Mouthfeel score (1-5)
        overall_score: Overall impression score (1-5)
        appearance_notes: Notes about appearance
        aroma_notes: Notes about aroma
        flavor_notes: Notes about flavor
        mouthfeel_notes: Notes about mouthfeel
        overall_notes: Overall impression notes
        days_since_packaging: Days since beer was packaged
        serving_temp_c: Serving temperature in Celsius
        glassware: Type of glass used
        to_style: Whether beer is to style
        style_deviation_notes: Notes about style deviations
        ai_suggestions: AI-generated suggestions for improvement
        interview_transcript: Transcript of AI-guided tasting interview
        user_id: User ID for multi-tenant isolation

    Returns:
        Dict with success status and created tasting note or error message
    """
    batch_result = await db.execute(select(Batch).where(Batch.id == batch_id))
    batch = batch_result.scalar_one_or_none()
    if not batch:
        return {"success": False, "error": f"Batch {batch_id} not found"}

    total_score = appearance_score + aroma_score + flavor_score + mouthfeel_score + overall_score

    if days_since_packaging is None and batch.packaged_at:
        days_since_packaging = (datetime.now(timezone.utc) - batch.packaged_at).days

    note = TastingNote(
        batch_id=batch_id,
        user_id=user_id,
        tasted_at=datetime.now(timezone.utc),
        days_since_packaging=days_since_packaging,
        serving_temp_c=serving_temp_c,
        glassware=glassware,
        appearance_score=appearance_score,
        appearance_notes=appearance_notes,
        aroma_score=aroma_score,
        aroma_notes=aroma_notes,
        flavor_score=flavor_score,
        flavor_notes=flavor_notes,
        mouthfeel_score=mouthfeel_score,
        mouthfeel_notes=mouthfeel_notes,
        overall_score=overall_score,
        overall_notes=overall_notes,
        total_score=total_score,
        to_style=to_style,
        style_deviation_notes=style_deviation_notes,
        ai_suggestions=ai_suggestions,
        interview_transcript=interview_transcript,
    )
    db.add(note)
    await db.commit()
    await db.refresh(note)

    return {
        "success": True,
        "tasting_note": {
            "id": note.id,
            "batch_id": note.batch_id,
            "tasted_at": note.tasted_at.isoformat(),
            "days_since_packaging": note.days_since_packaging,
            "total_score": note.total_score,
            "appearance_score": note.appearance_score,
            "aroma_score": note.aroma_score,
            "flavor_score": note.flavor_score,
            "mouthfeel_score": note.mouthfeel_score,
            "overall_score": note.overall_score,
            "to_style": note.to_style,
        }
    }


async def get_batch_tasting_notes(
    db: AsyncSession,
    batch_id: int,
    user_id: Optional[str] = None,
) -> dict[str, Any]:
    """Get all tasting notes for a batch.

    Args:
        db: Database session
        batch_id: ID of the batch to get tasting notes for
        user_id: User ID for multi-tenant isolation

    Returns:
        Dict with count and list of tasting notes
    """
    result = await db.execute(
        select(TastingNote)
        .where(TastingNote.batch_id == batch_id)
        .order_by(TastingNote.tasted_at)
    )
    notes = result.scalars().all()

    return {
        "count": len(notes),
        "tasting_notes": [
            {
                "id": n.id,
                "tasted_at": n.tasted_at.isoformat() if n.tasted_at else None,
                "days_since_packaging": n.days_since_packaging,
                "total_score": n.total_score,
                "appearance_score": n.appearance_score,
                "appearance_notes": n.appearance_notes,
                "aroma_score": n.aroma_score,
                "aroma_notes": n.aroma_notes,
                "flavor_score": n.flavor_score,
                "flavor_notes": n.flavor_notes,
                "mouthfeel_score": n.mouthfeel_score,
                "mouthfeel_notes": n.mouthfeel_notes,
                "overall_score": n.overall_score,
                "overall_notes": n.overall_notes,
                "to_style": n.to_style,
                "style_deviation_notes": n.style_deviation_notes,
                "ai_suggestions": n.ai_suggestions,
            }
            for n in notes
        ]
    }
