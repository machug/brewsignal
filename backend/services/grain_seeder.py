"""Grain variety database seeding service.

Seeds the grain_varieties table from the JSON file on startup.
Preserves custom user-added varieties on refresh.
"""

import json
import logging
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import GrainVariety

logger = logging.getLogger(__name__)

# Seed file location (committed to repo)
SEED_FILE = Path(__file__).parent.parent / "seed" / "grain_varieties.json"


async def seed_grain_varieties(db: AsyncSession, force: bool = False) -> dict:
    """Seed grain varieties from JSON file.

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
        logger.warning(f"Grain seed file not found: {SEED_FILE}")
        return {"success": False, "error": f"Seed file not found: {SEED_FILE}"}

    # Check if we need to seed
    result = await db.execute(
        select(GrainVariety).where(GrainVariety.is_custom == False).limit(1)
    )
    existing = result.scalar_one_or_none()

    if existing and not force:
        logger.debug("Grain varieties already seeded, skipping")
        return {"success": True, "action": "skipped", "reason": "already_seeded"}

    # Load seed data
    try:
        with open(SEED_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse grain seed file: {e}")
        return {"success": False, "error": f"Invalid JSON in seed file: {e}"}

    varieties = data.get("varieties", [])
    if not varieties:
        logger.warning("No varieties found in seed file")
        return {"success": False, "error": "No varieties in seed file"}

    # If force refresh, delete existing non-custom varieties
    if force:
        await db.execute(
            text("DELETE FROM grain_varieties WHERE is_custom = 0")
        )
        await db.commit()
        logger.info("Deleted existing non-custom grain varieties for refresh")

    # Insert varieties
    inserted = 0
    for variety_data in varieties:
        variety = GrainVariety(
            name=variety_data["name"],
            type=variety_data.get("type"),
            origin=variety_data.get("origin"),
            maltster=variety_data.get("maltster"),
            color_srm=variety_data.get("color_srm"),
            potential_sg=variety_data.get("potential_sg"),
            max_in_batch_percent=variety_data.get("max_in_batch_percent"),
            diastatic_power=variety_data.get("diastatic_power"),
            flavor_profile=variety_data.get("flavor_profile"),
            substitutes=variety_data.get("substitutes"),
            description=variety_data.get("description"),
            source=variety_data.get("source", "brewing_reference"),
            is_custom=False,
        )
        db.add(variety)
        inserted += 1

    await db.commit()
    logger.info(f"Seeded {inserted} grain varieties from {SEED_FILE}")

    return {
        "success": True,
        "action": "seeded",
        "count": inserted,
        "version": data.get("version"),
        "sources": data.get("sources", []),
    }


async def get_grain_variety_count(db: AsyncSession) -> dict:
    """Get counts of grain varieties by source.

    Returns:
        Dictionary with counts:
        - total: total number of varieties
        - custom: number of custom varieties
        - seeded: number of seeded varieties
    """
    # Total count
    total_result = await db.execute(select(GrainVariety))
    total = len(total_result.scalars().all())

    # Custom count
    custom_result = await db.execute(
        select(GrainVariety).where(GrainVariety.is_custom == True)
    )
    custom = len(custom_result.scalars().all())

    return {
        "total": total,
        "custom": custom,
        "seeded": total - custom,
    }
