"""BJCP style database seeding service.

Seeds the styles table from the JSON file on startup.
"""

import json
import logging
import re
from pathlib import Path
from typing import Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Style

logger = logging.getLogger(__name__)

# Seed file location (committed to repo)
SEED_FILE = Path(__file__).parent.parent / "seed" / "bjcp_styles.json"


def _parse_style_number(number: str) -> tuple[str, Optional[str]]:
    """Parse style number like '7B' into category_number and style_letter.

    Examples:
        '7B' -> ('7', 'B')
        '21' -> ('21', None)
        '23A' -> ('23', 'A')
    """
    match = re.match(r'^(\d+)([A-Z])?$', number.upper())
    if match:
        return match.group(1), match.group(2)
    return number, None


def _determine_type(tags: str) -> Optional[str]:
    """Determine beer type (Ale/Lager) from style tags."""
    if not tags:
        return None
    tags_lower = tags.lower()
    if 'top-fermented' in tags_lower:
        return 'Ale'
    if 'bottom-fermented' in tags_lower:
        return 'Lager'
    if 'any-fermentation' in tags_lower:
        return 'Mixed'
    return None


def _safe_float(value: str) -> Optional[float]:
    """Convert string to float, returning None on failure."""
    if not value:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


async def seed_styles(db: AsyncSession, force: bool = False) -> dict:
    """Seed BJCP styles from JSON file.

    Args:
        db: Database session
        force: If True, delete existing BJCP 2021 styles and re-insert

    Returns:
        Dictionary with seeding results
    """
    if not SEED_FILE.exists():
        logger.warning(f"BJCP styles seed file not found: {SEED_FILE}")
        return {"success": False, "error": f"Seed file not found: {SEED_FILE}"}

    # Check if we already have BJCP 2021 styles
    result = await db.execute(
        select(Style).where(Style.guide == "BJCP 2021").limit(1)
    )
    existing = result.scalar_one_or_none()

    if existing and not force:
        logger.debug("BJCP 2021 styles already seeded, skipping")
        return {"success": True, "action": "skipped", "reason": "already_seeded"}

    # Load seed data
    try:
        with open(SEED_FILE, 'r', encoding='utf-8') as f:
            styles_data = json.load(f)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse styles seed file: {e}")
        return {"success": False, "error": f"Invalid JSON in seed file: {e}"}

    if not styles_data:
        logger.warning("No styles found in seed file")
        return {"success": False, "error": "No styles in seed file"}

    # If force refresh, delete existing BJCP 2021 styles
    if force:
        await db.execute(
            text("DELETE FROM styles WHERE guide = 'BJCP 2021'")
        )
        await db.commit()
        logger.info("Deleted existing BJCP 2021 styles for refresh")

    # Insert styles
    inserted = 0
    for style_data in styles_data:
        number = style_data.get("number", "")
        category_number, style_letter = _parse_style_number(number)

        # Create unique ID
        style_id = f"bjcp-2021-{number}".lower()

        # Build description from overall impression
        description = style_data.get("overallimpression", "")

        style = Style(
            id=style_id,
            guide="BJCP 2021",
            category_number=category_number,
            style_letter=style_letter,
            name=style_data.get("name", ""),
            category=style_data.get("category", ""),
            type=_determine_type(style_data.get("tags", "")),
            og_min=_safe_float(style_data.get("ogmin")),
            og_max=_safe_float(style_data.get("ogmax")),
            fg_min=_safe_float(style_data.get("fgmin")),
            fg_max=_safe_float(style_data.get("fgmax")),
            ibu_min=_safe_float(style_data.get("ibumin")),
            ibu_max=_safe_float(style_data.get("ibumax")),
            srm_min=_safe_float(style_data.get("srmmin")),
            srm_max=_safe_float(style_data.get("srmmax")),
            abv_min=_safe_float(style_data.get("abvmin")),
            abv_max=_safe_float(style_data.get("abvmax")),
            description=description,
        )
        db.add(style)
        inserted += 1

    await db.commit()
    logger.info(f"Seeded {inserted} BJCP 2021 styles from {SEED_FILE}")

    return {
        "success": True,
        "action": "seeded",
        "count": inserted,
    }


async def get_style_count(db: AsyncSession) -> dict:
    """Get counts of styles by guide.

    Returns:
        Dictionary with counts
    """
    # Total count
    total_result = await db.execute(select(Style))
    total = len(total_result.scalars().all())

    # BJCP 2021 count
    bjcp_result = await db.execute(
        select(Style).where(Style.guide == "BJCP 2021")
    )
    bjcp_2021 = len(bjcp_result.scalars().all())

    return {
        "total": total,
        "bjcp_2021": bjcp_2021,
        "other": total - bjcp_2021,
    }
