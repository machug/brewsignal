"""Hop variety database seeding service.

Seeds the hop_varieties table from the JSON file on startup.
Preserves custom user-added varieties on refresh.
"""

import json
import logging
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import HopVariety

logger = logging.getLogger(__name__)

# Seed file location (committed to repo)
SEED_FILE = Path(__file__).parent.parent / "seed" / "hop_varieties.json"


async def seed_hop_varieties(db: AsyncSession, force: bool = False) -> dict:
    """Seed hop varieties from JSON file.

    Args:
        db: Database session
        force: If True, refresh all non-custom varieties (delete and re-insert)

    Returns:
        Dictionary with seeding results:
        - success: bool
        - action: "skipped" | "seeded"
        - count: number of varieties inserted (if seeded)
        - error: error message (if failed)
    """
    if not SEED_FILE.exists():
        logger.warning(f"Hop seed file not found: {SEED_FILE}")
        return {"success": False, "error": f"Seed file not found: {SEED_FILE}"}

    # Check if we need to seed
    result = await db.execute(
        select(HopVariety).where(HopVariety.is_custom == False).limit(1)
    )
    existing = result.scalar_one_or_none()

    if existing and not force:
        logger.debug("Hop varieties already seeded, skipping")
        return {"success": True, "action": "skipped", "reason": "already_seeded"}

    # Load seed data
    try:
        with open(SEED_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse hop seed file: {e}")
        return {"success": False, "error": f"Invalid JSON in seed file: {e}"}

    varieties = data.get("varieties", [])
    if not varieties:
        logger.warning("No varieties found in seed file")
        return {"success": False, "error": "No varieties in seed file"}

    # If force refresh, delete existing non-custom varieties
    if force:
        await db.execute(
            text("DELETE FROM hop_varieties WHERE is_custom = 0")
        )
        await db.commit()
        logger.info("Deleted existing non-custom hop varieties for refresh")

    # Insert varieties
    inserted = 0
    for variety_data in varieties:
        variety = HopVariety(
            name=variety_data["name"],
            origin=variety_data.get("origin"),
            alpha_acid_low=variety_data.get("alpha_acid_low"),
            alpha_acid_high=variety_data.get("alpha_acid_high"),
            beta_acid_low=variety_data.get("beta_acid_low"),
            beta_acid_high=variety_data.get("beta_acid_high"),
            purpose=variety_data.get("purpose"),
            aroma_profile=variety_data.get("aroma_profile"),
            substitutes=variety_data.get("substitutes"),
            description=variety_data.get("description"),
            source=variety_data.get("source", "brewersassociation"),
            is_custom=False,
        )
        db.add(variety)
        inserted += 1

    await db.commit()
    logger.info(f"Seeded {inserted} hop varieties from {SEED_FILE}")

    return {
        "success": True,
        "action": "seeded",
        "count": inserted,
        "version": data.get("version"),
        "sources": data.get("sources", []),
    }


async def get_hop_variety_count(db: AsyncSession) -> dict:
    """Get counts of hop varieties by source.

    Returns:
        Dictionary with counts:
        - total: total number of varieties
        - custom: number of custom varieties
        - seeded: number of seeded varieties
    """
    # Total count
    total_result = await db.execute(select(HopVariety))
    total = len(total_result.scalars().all())

    # Custom count
    custom_result = await db.execute(
        select(HopVariety).where(HopVariety.is_custom == True)
    )
    custom = len(custom_result.scalars().all())

    return {
        "total": total,
        "custom": custom,
        "seeded": total - custom,
    }
