"""Yeast and style search tools for the AI brewing assistant."""

from typing import Any, Optional

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import YeastStrain, Style


async def search_yeast(
    db: AsyncSession,
    query: Optional[str] = None,
    type: Optional[str] = None,
    form: Optional[str] = None,
    producer: Optional[str] = None,
    min_attenuation: Optional[float] = None,
    max_attenuation: Optional[float] = None,
    temp_range: Optional[float] = None,
    limit: int = 10
) -> dict[str, Any]:
    """Search yeast strains with various filters."""
    stmt = select(YeastStrain)

    # Text search on name, producer, product_id
    if query:
        search_term = f"%{query}%"
        stmt = stmt.where(
            or_(
                YeastStrain.name.ilike(search_term),
                YeastStrain.producer.ilike(search_term),
                YeastStrain.product_id.ilike(search_term),
                YeastStrain.description.ilike(search_term)
            )
        )

    # Exact filters
    if type:
        stmt = stmt.where(YeastStrain.type == type.lower())
    if form:
        stmt = stmt.where(YeastStrain.form == form.lower())
    if producer:
        stmt = stmt.where(YeastStrain.producer.ilike(f"%{producer}%"))

    # Attenuation range
    if min_attenuation:
        stmt = stmt.where(YeastStrain.attenuation_high >= min_attenuation)
    if max_attenuation:
        stmt = stmt.where(YeastStrain.attenuation_low <= max_attenuation)

    # Temperature compatibility
    if temp_range:
        stmt = stmt.where(
            YeastStrain.temp_low <= temp_range,
            YeastStrain.temp_high >= temp_range
        )

    stmt = stmt.limit(limit)

    result = await db.execute(stmt)
    yeasts = result.scalars().all()

    return {
        "count": len(yeasts),
        "yeasts": [
            {
                "name": y.name,
                "producer": y.producer,
                "product_id": y.product_id,
                "type": y.type,
                "form": y.form,
                "attenuation": f"{y.attenuation_low or '?'}-{y.attenuation_high or '?'}%",
                "temp_range": f"{y.temp_low or '?'}-{y.temp_high or '?'}°C",
                "flocculation": y.flocculation,
                "alcohol_tolerance": y.alcohol_tolerance,
                "description": y.description[:200] + "..." if y.description and len(y.description) > 200 else y.description
            }
            for y in yeasts
        ]
    }


async def search_styles(
    db: AsyncSession,
    query: Optional[str] = None,
    type: Optional[str] = None,
    category_number: Optional[str] = None,
    og_range: Optional[dict] = None,
    ibu_range: Optional[dict] = None,
    limit: int = 10
) -> dict[str, Any]:
    """Search beer styles with various filters."""
    stmt = select(Style)

    # Text search on name, category
    if query:
        search_term = f"%{query}%"
        stmt = stmt.where(
            or_(
                Style.name.ilike(search_term),
                Style.category.ilike(search_term),
                Style.description.ilike(search_term)
            )
        )

    # Exact filters
    if type:
        stmt = stmt.where(Style.type == type)
    if category_number:
        stmt = stmt.where(Style.category_number == category_number)

    # OG range
    if og_range:
        if og_range.get("min"):
            stmt = stmt.where(Style.og_max >= og_range["min"])
        if og_range.get("max"):
            stmt = stmt.where(Style.og_min <= og_range["max"])

    # IBU range
    if ibu_range:
        if ibu_range.get("min"):
            stmt = stmt.where(Style.ibu_max >= ibu_range["min"])
        if ibu_range.get("max"):
            stmt = stmt.where(Style.ibu_min <= ibu_range["max"])

    stmt = stmt.limit(limit)

    result = await db.execute(stmt)
    styles = result.scalars().all()

    return {
        "count": len(styles),
        "styles": [
            {
                "name": s.name,
                "category": s.category,
                "category_number": s.category_number,
                "style_letter": s.style_letter,
                "type": s.type,
                "og": f"{s.og_min or '?'}-{s.og_max or '?'}",
                "fg": f"{s.fg_min or '?'}-{s.fg_max or '?'}",
                "ibu": f"{s.ibu_min or '?'}-{s.ibu_max or '?'}",
                "srm": f"{s.srm_min or '?'}-{s.srm_max or '?'}",
                "abv": f"{s.abv_min or '?'}-{s.abv_max or '?'}%",
                "description": s.description[:200] + "..." if s.description and len(s.description) > 200 else s.description
            }
            for s in styles
        ]
    }


async def get_yeast_by_id(
    db: AsyncSession,
    product_id: str
) -> dict[str, Any]:
    """Get detailed yeast info by product ID."""
    stmt = select(YeastStrain).where(
        YeastStrain.product_id.ilike(product_id)
    )

    result = await db.execute(stmt)
    yeast = result.scalar_one_or_none()

    if not yeast:
        # Try broader search
        stmt = select(YeastStrain).where(
            or_(
                YeastStrain.product_id.ilike(f"%{product_id}%"),
                YeastStrain.name.ilike(f"%{product_id}%")
            )
        ).limit(1)
        result = await db.execute(stmt)
        yeast = result.scalar_one_or_none()

    if not yeast:
        return {"error": f"Yeast not found: {product_id}"}

    return {
        "found": True,
        "yeast": {
            "name": yeast.name,
            "producer": yeast.producer,
            "product_id": yeast.product_id,
            "type": yeast.type,
            "form": yeast.form,
            "attenuation_low": yeast.attenuation_low,
            "attenuation_high": yeast.attenuation_high,
            "temp_low_c": yeast.temp_low,
            "temp_high_c": yeast.temp_high,
            "flocculation": yeast.flocculation,
            "alcohol_tolerance": yeast.alcohol_tolerance,
            "description": yeast.description
        }
    }


async def get_style_by_name(
    db: AsyncSession,
    name: str
) -> dict[str, Any]:
    """Get detailed style info by name."""
    # Try exact match first
    stmt = select(Style).where(Style.name.ilike(name))
    result = await db.execute(stmt)
    style = result.scalar_one_or_none()

    if not style:
        # Try partial match
        stmt = select(Style).where(Style.name.ilike(f"%{name}%")).limit(1)
        result = await db.execute(stmt)
        style = result.scalar_one_or_none()

    if not style:
        return {"error": f"Style not found: {name}"}

    return {
        "found": True,
        "style": {
            "name": style.name,
            "guide": style.guide,
            "category": style.category,
            "category_number": style.category_number,
            "style_letter": style.style_letter,
            "type": style.type,
            "og_min": style.og_min,
            "og_max": style.og_max,
            "fg_min": style.fg_min,
            "fg_max": style.fg_max,
            "ibu_min": style.ibu_min,
            "ibu_max": style.ibu_max,
            "srm_min": style.srm_min,
            "srm_max": style.srm_max,
            "abv_min": style.abv_min,
            "abv_max": style.abv_max,
            "description": style.description
        }
    }
