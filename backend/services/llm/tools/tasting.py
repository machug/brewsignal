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
        "bjcp_scoring": {
            "aroma": {"max": 12, "subcategories": {"malt": 3, "hops": 3, "fermentation": 3, "other": 3}},
            "appearance": {"max": 3, "subcategories": {"color": 1, "clarity": 1, "head": 1}},
            "flavor": {"max": 20, "subcategories": {"malt": 5, "hops": 5, "bitterness": 3, "fermentation": 3, "balance": 2, "finish": 2}},
            "mouthfeel": {"max": 5, "subcategories": {"body": 2, "carbonation": 2, "warmth": 1}},
            "overall": {"max": 10},
            "total_max": 50,
        },
    }


async def save_tasting_note(
    db: AsyncSession,
    batch_id: int,
    # Legacy v1 scores (optional for v2 BJCP scoring)
    appearance_score: Optional[int] = None,
    aroma_score: Optional[int] = None,
    flavor_score: Optional[int] = None,
    mouthfeel_score: Optional[int] = None,
    overall_score: Optional[int] = None,
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
    # BJCP v2 scoring
    scoring_version: int = 1,
    # Aroma subcategories (0-3 each, max 12)
    aroma_malt: Optional[int] = None,
    aroma_hops: Optional[int] = None,
    aroma_fermentation: Optional[int] = None,
    aroma_other: Optional[int] = None,
    # Appearance subcategories (0-1 each, max 3)
    appearance_color: Optional[int] = None,
    appearance_clarity: Optional[int] = None,
    appearance_head: Optional[int] = None,
    # Flavor subcategories (varying, max 20)
    flavor_malt: Optional[int] = None,
    flavor_hops: Optional[int] = None,
    flavor_bitterness: Optional[int] = None,
    flavor_fermentation: Optional[int] = None,
    flavor_balance: Optional[int] = None,
    flavor_finish: Optional[int] = None,
    # Mouthfeel subcategories (varying, max 5)
    mouthfeel_body: Optional[int] = None,
    mouthfeel_carbonation: Optional[int] = None,
    mouthfeel_warmth: Optional[int] = None,
) -> dict[str, Any]:
    """Save a complete tasting note for a batch.

    Supports two scoring versions:
    - v1 (legacy): 5 category scores (1-5 each), max 25 points
    - v2 (BJCP): 16 subcategory scores + overall, max 50 points

    Args:
        db: Database session
        batch_id: ID of the batch to add tasting note for
        appearance_score: Legacy appearance score (1-5)
        aroma_score: Legacy aroma score (1-5)
        flavor_score: Legacy flavor score (1-5)
        mouthfeel_score: Legacy mouthfeel score (1-5)
        overall_score: Overall impression score (1-5 for v1, 0-10 for v2)
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
        scoring_version: 1 for legacy (default), 2 for BJCP subcategory scoring
        aroma_malt: BJCP aroma malt score (0-3)
        aroma_hops: BJCP aroma hops score (0-3)
        aroma_fermentation: BJCP aroma fermentation score (0-3)
        aroma_other: BJCP aroma other score (0-3)
        appearance_color: BJCP appearance color score (0-1)
        appearance_clarity: BJCP appearance clarity score (0-1)
        appearance_head: BJCP appearance head score (0-1)
        flavor_malt: BJCP flavor malt score (0-5)
        flavor_hops: BJCP flavor hops score (0-5)
        flavor_bitterness: BJCP flavor bitterness score (0-3)
        flavor_fermentation: BJCP flavor fermentation score (0-3)
        flavor_balance: BJCP flavor balance score (0-2)
        flavor_finish: BJCP flavor finish score (0-2)
        mouthfeel_body: BJCP mouthfeel body score (0-2)
        mouthfeel_carbonation: BJCP mouthfeel carbonation score (0-2)
        mouthfeel_warmth: BJCP mouthfeel warmth score (0-1)

    Returns:
        Dict with success status and created tasting note or error message
    """
    batch_result = await db.execute(select(Batch).where(Batch.id == batch_id))
    batch = batch_result.scalar_one_or_none()
    if not batch:
        return {"success": False, "error": f"Batch {batch_id} not found"}

    if scoring_version == 2:
        total_score = sum(filter(None, [
            aroma_malt, aroma_hops, aroma_fermentation, aroma_other,
            appearance_color, appearance_clarity, appearance_head,
            flavor_malt, flavor_hops, flavor_bitterness, flavor_fermentation,
            flavor_balance, flavor_finish,
            mouthfeel_body, mouthfeel_carbonation, mouthfeel_warmth,
            overall_score,
        ]))
    else:
        total_score = (appearance_score or 0) + (aroma_score or 0) + (flavor_score or 0) + (mouthfeel_score or 0) + (overall_score or 0)

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
        scoring_version=scoring_version,
        aroma_malt=aroma_malt,
        aroma_hops=aroma_hops,
        aroma_fermentation=aroma_fermentation,
        aroma_other=aroma_other,
        appearance_color=appearance_color,
        appearance_clarity=appearance_clarity,
        appearance_head=appearance_head,
        flavor_malt=flavor_malt,
        flavor_hops=flavor_hops,
        flavor_bitterness=flavor_bitterness,
        flavor_fermentation=flavor_fermentation,
        flavor_balance=flavor_balance,
        flavor_finish=flavor_finish,
        mouthfeel_body=mouthfeel_body,
        mouthfeel_carbonation=mouthfeel_carbonation,
        mouthfeel_warmth=mouthfeel_warmth,
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
            "scoring_version": note.scoring_version,
            "appearance_score": note.appearance_score,
            "aroma_score": note.aroma_score,
            "flavor_score": note.flavor_score,
            "mouthfeel_score": note.mouthfeel_score,
            "overall_score": note.overall_score,
            "to_style": note.to_style,
            # BJCP v2 subcategory scores
            "aroma_malt": note.aroma_malt,
            "aroma_hops": note.aroma_hops,
            "aroma_fermentation": note.aroma_fermentation,
            "aroma_other": note.aroma_other,
            "appearance_color": note.appearance_color,
            "appearance_clarity": note.appearance_clarity,
            "appearance_head": note.appearance_head,
            "flavor_malt": note.flavor_malt,
            "flavor_hops": note.flavor_hops,
            "flavor_bitterness": note.flavor_bitterness,
            "flavor_fermentation": note.flavor_fermentation,
            "flavor_balance": note.flavor_balance,
            "flavor_finish": note.flavor_finish,
            "mouthfeel_body": note.mouthfeel_body,
            "mouthfeel_carbonation": note.mouthfeel_carbonation,
            "mouthfeel_warmth": note.mouthfeel_warmth,
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
                "scoring_version": n.scoring_version,
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
                # BJCP v2 subcategory scores
                "aroma_malt": n.aroma_malt,
                "aroma_hops": n.aroma_hops,
                "aroma_fermentation": n.aroma_fermentation,
                "aroma_other": n.aroma_other,
                "appearance_color": n.appearance_color,
                "appearance_clarity": n.appearance_clarity,
                "appearance_head": n.appearance_head,
                "flavor_malt": n.flavor_malt,
                "flavor_hops": n.flavor_hops,
                "flavor_bitterness": n.flavor_bitterness,
                "flavor_fermentation": n.flavor_fermentation,
                "flavor_balance": n.flavor_balance,
                "flavor_finish": n.flavor_finish,
                "mouthfeel_body": n.mouthfeel_body,
                "mouthfeel_carbonation": n.mouthfeel_carbonation,
                "mouthfeel_warmth": n.mouthfeel_warmth,
            }
            for n in notes
        ]
    }
