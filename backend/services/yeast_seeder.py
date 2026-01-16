"""Yeast strain database seeding service.

Seeds the yeast_strains table from the JSON file on startup.
Preserves custom user-added strains on refresh.
"""

import json
import logging
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import YeastStrain

logger = logging.getLogger(__name__)

# Seed file location (committed to repo)
SEED_FILE = Path(__file__).parent.parent / "seed" / "yeast_strains.json"


async def seed_yeast_strains(db: AsyncSession, force: bool = False) -> dict:
    """Seed yeast strains from JSON file.

    Args:
        db: Database session
        force: If True, refresh all non-custom strains (delete and re-insert)

    Returns:
        Dictionary with seeding results:
        - success: bool
        - action: "skipped" | "seeded"
        - count: number of strains inserted (if seeded)
        - error: error message (if failed)
    """
    if not SEED_FILE.exists():
        logger.warning(f"Yeast seed file not found: {SEED_FILE}")
        return {"success": False, "error": f"Seed file not found: {SEED_FILE}"}

    # Check if we need to seed
    result = await db.execute(
        select(YeastStrain).where(YeastStrain.is_custom == False).limit(1)
    )
    existing = result.scalar_one_or_none()

    if existing and not force:
        logger.debug("Yeast strains already seeded, skipping")
        return {"success": True, "action": "skipped", "reason": "already_seeded"}

    # Load seed data
    try:
        with open(SEED_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse yeast seed file: {e}")
        return {"success": False, "error": f"Invalid JSON in seed file: {e}"}

    strains = data.get("strains", [])
    if not strains:
        logger.warning("No strains found in seed file")
        return {"success": False, "error": "No strains in seed file"}

    # If force refresh, delete existing non-custom strains
    if force:
        await db.execute(
            text("DELETE FROM yeast_strains WHERE is_custom = 0")
        )
        await db.commit()
        logger.info("Deleted existing non-custom yeast strains for refresh")

    # Insert strains
    inserted = 0
    for strain_data in strains:
        strain = YeastStrain(
            name=strain_data["name"],
            producer=strain_data.get("producer"),
            product_id=strain_data.get("product_id"),
            type=strain_data.get("type"),
            form=strain_data.get("form"),
            attenuation_low=strain_data.get("attenuation_low"),
            attenuation_high=strain_data.get("attenuation_high"),
            temp_low=strain_data.get("temp_low"),
            temp_high=strain_data.get("temp_high"),
            alcohol_tolerance=strain_data.get("alcohol_tolerance"),
            flocculation=strain_data.get("flocculation"),
            description=strain_data.get("description"),
            source=strain_data.get("source", "custom"),
            is_custom=False,
        )
        db.add(strain)
        inserted += 1

    await db.commit()
    logger.info(f"Seeded {inserted} yeast strains from {SEED_FILE}")

    return {
        "success": True,
        "action": "seeded",
        "count": inserted,
        "version": data.get("version"),
        "sources": data.get("sources", []),
    }


async def get_yeast_strain_count(db: AsyncSession) -> dict:
    """Get counts of yeast strains by source.

    Returns:
        Dictionary with counts:
        - total: total number of strains
        - custom: number of custom strains
        - seeded: number of seeded strains
    """
    # Total count
    total_result = await db.execute(select(YeastStrain))
    total = len(total_result.scalars().all())

    # Custom count
    custom_result = await db.execute(
        select(YeastStrain).where(YeastStrain.is_custom == True)
    )
    custom = len(custom_result.scalars().all())

    return {
        "total": total,
        "custom": custom,
        "seeded": total - custom,
    }
