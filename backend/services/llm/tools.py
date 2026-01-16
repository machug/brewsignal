"""AG-UI Tools for the AI brewing assistant.

This module defines tools that the LLM can call to query the database
for yeast strains, beer styles, and other brewing information.
"""

import logging
from typing import Any, Optional

from sqlalchemy import select, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import YeastStrain, Style

logger = logging.getLogger(__name__)


# Tool definitions in OpenAI function calling format
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "search_yeast",
            "description": "Search the yeast strain database. Returns matching yeast strains with their fermentation characteristics. Use this when the user asks about yeast recommendations, yeast properties, or needs help choosing a yeast for their recipe.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search term to match against yeast name, producer, or product ID (e.g., 'US-05', 'Belgian', 'Safale', 'White Labs')"
                    },
                    "type": {
                        "type": "string",
                        "enum": ["ale", "lager", "wine", "wild", "hybrid"],
                        "description": "Filter by yeast type"
                    },
                    "form": {
                        "type": "string",
                        "enum": ["dry", "liquid", "slant"],
                        "description": "Filter by yeast form (dry is easier for beginners)"
                    },
                    "producer": {
                        "type": "string",
                        "description": "Filter by producer/lab name (e.g., 'Fermentis', 'White Labs', 'Wyeast', 'Lallemand')"
                    },
                    "min_attenuation": {
                        "type": "number",
                        "description": "Minimum attenuation percentage (e.g., 75 for drier beers)"
                    },
                    "max_attenuation": {
                        "type": "number",
                        "description": "Maximum attenuation percentage (e.g., 70 for sweeter beers)"
                    },
                    "temp_range": {
                        "type": "number",
                        "description": "Fermentation temperature in Celsius - returns yeasts that work at this temp"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results to return (default: 10)"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_styles",
            "description": "Search the BJCP beer style database. Returns matching styles with their vital statistics (OG, FG, IBU, SRM, ABV ranges). Use this when the user asks about beer style characteristics or guidelines.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search term to match against style name or category (e.g., 'IPA', 'Stout', 'Belgian', 'Lager')"
                    },
                    "type": {
                        "type": "string",
                        "enum": ["Ale", "Lager", "Mixed", "Wheat", "Wild"],
                        "description": "Filter by beer type"
                    },
                    "category_number": {
                        "type": "string",
                        "description": "BJCP category number (e.g., '18' for Pale American Ale)"
                    },
                    "og_range": {
                        "type": "object",
                        "properties": {
                            "min": {"type": "number"},
                            "max": {"type": "number"}
                        },
                        "description": "Filter by OG range"
                    },
                    "ibu_range": {
                        "type": "object",
                        "properties": {
                            "min": {"type": "number"},
                            "max": {"type": "number"}
                        },
                        "description": "Filter by IBU range"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results to return (default: 10)"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_yeast_by_id",
            "description": "Get detailed information about a specific yeast strain by its product ID. Use this when you need complete details about a specific yeast.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {
                        "type": "string",
                        "description": "The yeast product ID (e.g., 'US-05', 'WLP001', 'W-34/70')"
                    }
                },
                "required": ["product_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_style_by_name",
            "description": "Get detailed BJCP guidelines for a specific beer style. Use this when you need the exact specifications for a style.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "The beer style name (e.g., 'American IPA', 'German Pilsner', 'Belgian Tripel')"
                    }
                },
                "required": ["name"]
            }
        }
    }
]


async def execute_tool(
    db: AsyncSession,
    tool_name: str,
    arguments: dict[str, Any]
) -> dict[str, Any]:
    """Execute a tool and return the result.

    Args:
        db: Database session
        tool_name: Name of the tool to execute
        arguments: Tool arguments

    Returns:
        Tool result as a dictionary
    """
    logger.info(f"Executing tool: {tool_name} with args: {arguments}")

    if tool_name == "search_yeast":
        return await _search_yeast(db, **arguments)
    elif tool_name == "search_styles":
        return await _search_styles(db, **arguments)
    elif tool_name == "get_yeast_by_id":
        return await _get_yeast_by_id(db, **arguments)
    elif tool_name == "get_style_by_name":
        return await _get_style_by_name(db, **arguments)
    else:
        return {"error": f"Unknown tool: {tool_name}"}


async def _search_yeast(
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


async def _search_styles(
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


async def _get_yeast_by_id(
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


async def _get_style_by_name(
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
