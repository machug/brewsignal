"""Ingredient reference library tools for the AI brewing assistant."""

from typing import Any, Optional

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import HopVariety, Fermentable


async def search_hop_varieties(
    db: AsyncSession,
    query: Optional[str] = None,
    purpose: Optional[str] = None,
    origin: Optional[str] = None,
    min_alpha: Optional[float] = None,
    max_alpha: Optional[float] = None,
    limit: int = 15
) -> dict[str, Any]:
    """Search the hop variety reference database."""
    stmt = select(HopVariety).order_by(HopVariety.name)

    # Text search on name, aroma profile, description
    if query:
        search_term = f"%{query}%"
        stmt = stmt.where(
            or_(
                HopVariety.name.ilike(search_term),
                HopVariety.aroma_profile.ilike(search_term),
                HopVariety.description.ilike(search_term),
                HopVariety.substitutes.ilike(search_term),
            )
        )

    # Exact/partial filters
    if purpose:
        stmt = stmt.where(HopVariety.purpose == purpose.lower())
    if origin:
        stmt = stmt.where(HopVariety.origin.ilike(f"%{origin}%"))

    # Alpha acid range filters
    if min_alpha is not None:
        stmt = stmt.where(HopVariety.alpha_acid_high >= min_alpha)
    if max_alpha is not None:
        stmt = stmt.where(HopVariety.alpha_acid_low <= max_alpha)

    stmt = stmt.limit(limit)

    result = await db.execute(stmt)
    hops = result.scalars().all()

    if not hops:
        return {
            "count": 0,
            "message": "No hop varieties found matching your criteria",
            "hop_varieties": []
        }

    return {
        "count": len(hops),
        "hop_varieties": [
            {
                "name": h.name,
                "origin": h.origin,
                "purpose": h.purpose,
                "alpha_acid": f"{h.alpha_acid_low or '?'}-{h.alpha_acid_high or '?'}%" if h.alpha_acid_low or h.alpha_acid_high else None,
                "beta_acid": f"{h.beta_acid_low or '?'}-{h.beta_acid_high or '?'}%" if h.beta_acid_low or h.beta_acid_high else None,
                "aroma_profile": h.aroma_profile,
                "substitutes": h.substitutes,
                "description": h.description[:200] + "..." if h.description and len(h.description) > 200 else h.description,
                "is_custom": h.is_custom,
            }
            for h in hops
        ]
    }


async def search_fermentables(
    db: AsyncSession,
    query: Optional[str] = None,
    type: Optional[str] = None,
    origin: Optional[str] = None,
    maltster: Optional[str] = None,
    max_color_srm: Optional[float] = None,
    min_color_srm: Optional[float] = None,
    min_diastatic_power: Optional[float] = None,
    limit: int = 15
) -> dict[str, Any]:
    """Search the fermentables reference database."""
    stmt = select(Fermentable).order_by(Fermentable.name)

    # Text search on name, flavor profile, description
    if query:
        search_term = f"%{query}%"
        stmt = stmt.where(
            or_(
                Fermentable.name.ilike(search_term),
                Fermentable.flavor_profile.ilike(search_term),
                Fermentable.description.ilike(search_term),
                Fermentable.substitutes.ilike(search_term),
            )
        )

    # Exact/partial filters
    if type:
        stmt = stmt.where(Fermentable.type == type.lower())
    if origin:
        stmt = stmt.where(Fermentable.origin.ilike(f"%{origin}%"))
    if maltster:
        stmt = stmt.where(Fermentable.maltster.ilike(f"%{maltster}%"))

    # Color range filters
    if max_color_srm is not None:
        stmt = stmt.where(Fermentable.color_srm <= max_color_srm)
    if min_color_srm is not None:
        stmt = stmt.where(Fermentable.color_srm >= min_color_srm)

    # Diastatic power filter (for base malts)
    if min_diastatic_power is not None:
        stmt = stmt.where(Fermentable.diastatic_power >= min_diastatic_power)

    stmt = stmt.limit(limit)

    result = await db.execute(stmt)
    fermentables = result.scalars().all()

    if not fermentables:
        return {
            "count": 0,
            "message": "No fermentables found matching your criteria",
            "fermentables": []
        }

    return {
        "count": len(fermentables),
        "fermentables": [
            {
                "name": f.name,
                "type": f.type,
                "origin": f.origin,
                "maltster": f.maltster,
                "color_srm": f.color_srm,
                "potential_sg": f.potential_sg,
                "max_in_batch_percent": f.max_in_batch_percent,
                "diastatic_power": f.diastatic_power,
                "flavor_profile": f.flavor_profile,
                "substitutes": f.substitutes,
                "description": f.description[:200] + "..." if f.description and len(f.description) > 200 else f.description,
                "is_custom": f.is_custom,
            }
            for f in fermentables
        ]
    }
