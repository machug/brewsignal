"""Fermentable database seeding service.

Seeds the fermentables table from the JSON file on startup.
Preserves custom user-added fermentables on refresh.
"""

import json
import logging
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Fermentable

logger = logging.getLogger(__name__)

# Seed file location (committed to repo)
SEED_FILE = Path(__file__).parent.parent / "seed" / "fermentables.json"


async def seed_fermentables(db: AsyncSession, force: bool = False) -> dict:
    """Seed fermentables from JSON file.

    Args:
        db: Database session
        force: If True, refresh all non-custom fermentables (delete and re-insert)

    Returns:
        Dictionary with seeding results:
        - success: bool
        - action: "skipped" | "seeded"
        - count: number of fermentables inserted (if seeded)
        - error: error message (if failed)
    """
    if not SEED_FILE.exists():
        logger.warning(f"Fermentables seed file not found: {SEED_FILE}")
        return {"success": False, "error": f"Seed file not found: {SEED_FILE}"}

    # Check if we need to seed
    result = await db.execute(
        select(Fermentable).where(Fermentable.is_custom == False).limit(1)
    )
    existing = result.scalar_one_or_none()

    if existing and not force:
        logger.debug("Fermentables already seeded, skipping")
        return {"success": True, "action": "skipped", "reason": "already_seeded"}

    # Load seed data
    try:
        with open(SEED_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse fermentables seed file: {e}")
        return {"success": False, "error": f"Invalid JSON in seed file: {e}"}

    # Support both "fermentables" and legacy "varieties" keys
    fermentables_data = data.get("fermentables") or data.get("varieties", [])
    if not fermentables_data:
        logger.warning("No fermentables found in seed file")
        return {"success": False, "error": "No fermentables in seed file"}

    # If force refresh, delete existing non-custom fermentables
    if force:
        await db.execute(
            text("DELETE FROM fermentables WHERE is_custom = 0")
        )
        await db.commit()
        logger.info("Deleted existing non-custom fermentables for refresh")

    # Insert fermentables
    inserted = 0
    for item in fermentables_data:
        fermentable = Fermentable(
            name=item["name"],
            type=item.get("type"),
            origin=item.get("origin"),
            maltster=item.get("maltster"),
            color_srm=item.get("color_srm"),
            potential_sg=item.get("potential_sg"),
            max_in_batch_percent=item.get("max_in_batch_percent"),
            diastatic_power=item.get("diastatic_power"),
            flavor_profile=item.get("flavor_profile"),
            substitutes=item.get("substitutes"),
            description=item.get("description"),
            source=item.get("source", "brewing_reference"),
            is_custom=False,
        )
        db.add(fermentable)
        inserted += 1

    await db.commit()
    logger.info(f"Seeded {inserted} fermentables from {SEED_FILE}")

    return {
        "success": True,
        "action": "seeded",
        "count": inserted,
        "version": data.get("version"),
        "sources": data.get("sources", []),
    }


async def get_fermentable_count(db: AsyncSession) -> dict:
    """Get counts of fermentables by source.

    Returns:
        Dictionary with counts:
        - total: total number of fermentables
        - custom: number of custom fermentables
        - seeded: number of seeded fermentables
    """
    # Total count
    total_result = await db.execute(select(Fermentable))
    total = len(total_result.scalars().all())

    # Custom count
    custom_result = await db.execute(
        select(Fermentable).where(Fermentable.is_custom == True)
    )
    custom = len(custom_result.scalars().all())

    return {
        "total": total,
        "custom": custom,
        "seeded": total - custom,
    }
