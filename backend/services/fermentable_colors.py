"""Enrich recipe fermentable colors from the seeded Fermentable reference table.

The LLM recipe-stat calc derives SRM from each normalized fermentable's `color`
and defaults a missing color to pale (~3). When the model omits a dark grain's
color, the roasted contribution vanishes and a stout reads as ~3 SRM
(tilt_ui-81n). The Fermentable reference table knows real colors
(Roasted Barley = 500 SRM), so we fill missing colors from it before the SRM
calc and before serialization writes the recipe_fermentables rows.
"""
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Fermentable


async def resolve_fermentable_color_srm(
    db: AsyncSession, name: Optional[str]
) -> Optional[float]:
    """Look up a grain's color (SRM) in the reference table by name.

    Exact (case-insensitive) match first, then a substring match preferring the
    shortest reference name (so "Roast" lands on "Roasted Barley", not a longer
    specialty variant). Returns None when unknown or the row has no color.
    """
    if not name or not isinstance(name, str):
        return None
    n = name.strip()
    if not n:
        return None

    result = await db.execute(
        select(Fermentable)
        .where(func.lower(Fermentable.name) == n.lower())
        .limit(1)
    )
    ref = result.scalar_one_or_none()
    if ref is None:
        result = await db.execute(
            select(Fermentable)
            .where(Fermentable.name.ilike(f"%{n}%"))
            .order_by(func.length(Fermentable.name))
            .limit(1)
        )
        ref = result.scalar_one_or_none()

    return ref.color_srm if ref is not None and ref.color_srm is not None else None


def _has_color(ferm: dict[str, Any]) -> bool:
    # A color the model/import explicitly provided counts; a value the
    # normalizer guessed from its hard-coded map (_color_guessed) does NOT, so
    # the seeded reference table stays authoritative and can replace it.
    if ferm.get("_color_guessed"):
        return False
    color = ferm.get("color")
    if color is None:
        return False
    if isinstance(color, dict):
        return color.get("value") is not None
    return True


async def enrich_fermentable_colors(
    db: AsyncSession, normalized: dict[str, Any]
) -> int:
    """Fill missing `color` on normalized fermentable_additions from the
    reference table. The reference is authoritative over normalizer guesses
    (`_color_guessed`); explicit model/import colors are preserved. Mutates
    `normalized` in place. Returns the number filled from the reference.
    """
    ingredients = normalized.get("ingredients") or {}
    fermentables = ingredients.get("fermentable_additions") or []

    enriched = 0
    for ferm in fermentables:
        if not isinstance(ferm, dict):
            continue
        if not _has_color(ferm):
            srm = await resolve_fermentable_color_srm(db, ferm.get("name"))
            if srm is not None:
                ferm["color"] = {"value": float(srm), "unit": "SRM"}
                enriched += 1
        # Drop the transient guess marker so it never reaches the serializer.
        ferm.pop("_color_guessed", None)
    return enriched
