"""AG-UI Tools for the AI brewing assistant.

This module defines tools that the LLM can call to query the database
for yeast strains, beer styles, and other brewing information.
"""

import logging
from typing import Any, Optional

from sqlalchemy import select, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from datetime import datetime, timedelta, timezone
from backend.models import (
    YeastStrain, Style, HopInventory, YeastInventory,
    Batch, Recipe, Reading, Device, AmbientReading, RecipeCulture
)
from backend.state import latest_readings

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
    },
    {
        "type": "function",
        "function": {
            "name": "search_inventory_hops",
            "description": "Search the user's hop inventory. Use this when the user asks about what hops they have on hand, or when suggesting recipes based on available ingredients.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search term to match against hop variety name (e.g., 'Citra', 'Cascade', 'Mosaic')"
                    },
                    "min_amount_grams": {
                        "type": "number",
                        "description": "Minimum amount in grams (to filter out nearly empty stocks)"
                    },
                    "form": {
                        "type": "string",
                        "enum": ["pellet", "leaf", "plug"],
                        "description": "Filter by hop form"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results to return (default: 20)"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_inventory_yeast",
            "description": "Search the user's yeast inventory. Use this when the user asks about what yeast they have available, or when suggesting recipes based on available ingredients.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search term to match against yeast strain name or custom name"
                    },
                    "type": {
                        "type": "string",
                        "enum": ["ale", "lager", "wine", "wild", "hybrid"],
                        "description": "Filter by yeast type"
                    },
                    "form": {
                        "type": "string",
                        "enum": ["dry", "liquid", "slant", "harvested"],
                        "description": "Filter by yeast form"
                    },
                    "include_expired": {
                        "type": "boolean",
                        "description": "Include expired yeast in results (default: false)"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results to return (default: 20)"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_recipe_ingredients",
            "description": "Check if the user has specific hops and yeast in their inventory. Use this to verify ingredient availability before recommending a recipe.",
            "parameters": {
                "type": "object",
                "properties": {
                    "hop_varieties": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of hop variety names to check (e.g., ['Citra', 'Mosaic'])"
                    },
                    "yeast_query": {
                        "type": "string",
                        "description": "Yeast strain name or type to check for (e.g., 'US-05' or 'Belgian ale')"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_inventory_summary",
            "description": "Get a summary of the user's brewing inventory (hops, yeast). Use this for a quick overview of what's available.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    # =============================================================================
    # Fermentation Monitoring Tools
    # =============================================================================
    {
        "type": "function",
        "function": {
            "name": "list_fermentations",
            "description": "List active or completed fermentation batches with their current progress. Use this when the user asks about their fermentations, what's fermenting, or wants an overview of batches.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["fermenting", "conditioning", "completed", "planning", "all"],
                        "description": "Filter by batch status. 'all' includes all non-deleted batches."
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of batches to return (default: 10)"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_fermentation_status",
            "description": "Get comprehensive real-time status for a specific fermentation batch. Returns current readings, progress, temperature status relative to yeast tolerance, ML predictions, and any alerts. Use this when the user asks about a specific batch's status or progress.",
            "parameters": {
                "type": "object",
                "properties": {
                    "batch_id": {
                        "type": "integer",
                        "description": "The batch ID to get status for"
                    }
                },
                "required": ["batch_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_fermentation_history",
            "description": "Get historical readings for a fermentation batch with trend analysis. Use this when the user asks about fermentation trends, how it's been progressing, or wants historical data.",
            "parameters": {
                "type": "object",
                "properties": {
                    "batch_id": {
                        "type": "integer",
                        "description": "The batch ID to get history for"
                    },
                    "hours": {
                        "type": "integer",
                        "description": "Number of hours of history to retrieve (default: 24, max: 720)"
                    },
                    "include_anomalies_only": {
                        "type": "boolean",
                        "description": "If true, only return readings flagged as anomalies (default: false)"
                    }
                },
                "required": ["batch_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_ambient_conditions",
            "description": "Get current ambient temperature and humidity from environment sensors. Use this when discussing fermentation environment, temperature control, or room conditions.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "compare_batches",
            "description": "Find similar historical batches for comparison. Useful for comparing current fermentation to past batches with the same recipe, style, or yeast strain.",
            "parameters": {
                "type": "object",
                "properties": {
                    "batch_id": {
                        "type": "integer",
                        "description": "The reference batch ID to compare against"
                    },
                    "comparison_type": {
                        "type": "string",
                        "enum": ["recipe", "style", "yeast"],
                        "description": "Type of comparison: 'recipe' matches same recipe, 'style' matches same beer style, 'yeast' matches same yeast strain"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of similar batches to return (default: 5)"
                    }
                },
                "required": ["batch_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_yeast_fermentation_advice",
            "description": "Get yeast-specific fermentation advice and recommendations. Use this when the user asks about how to ferment with a specific yeast, optimal temperatures, or yeast characteristics.",
            "parameters": {
                "type": "object",
                "properties": {
                    "yeast_query": {
                        "type": "string",
                        "description": "Yeast name or product ID to get advice for (e.g., 'US-05', 'WLP001', 'Belgian ale')"
                    },
                    "batch_id": {
                        "type": "integer",
                        "description": "Optional batch ID to provide batch-specific recommendations"
                    }
                },
                "required": ["yeast_query"]
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
    elif tool_name == "search_inventory_hops":
        return await _search_inventory_hops(db, **arguments)
    elif tool_name == "search_inventory_yeast":
        return await _search_inventory_yeast(db, **arguments)
    elif tool_name == "check_recipe_ingredients":
        return await _check_recipe_ingredients(db, **arguments)
    elif tool_name == "get_inventory_summary":
        return await _get_inventory_summary(db)
    # Fermentation monitoring tools
    elif tool_name == "list_fermentations":
        return await _list_fermentations(db, **arguments)
    elif tool_name == "get_fermentation_status":
        return await _get_fermentation_status(db, **arguments)
    elif tool_name == "get_fermentation_history":
        return await _get_fermentation_history(db, **arguments)
    elif tool_name == "get_ambient_conditions":
        return await _get_ambient_conditions(db)
    elif tool_name == "compare_batches":
        return await _compare_batches(db, **arguments)
    elif tool_name == "get_yeast_fermentation_advice":
        return await _get_yeast_fermentation_advice(db, **arguments)
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


# =============================================================================
# Inventory Tools
# =============================================================================

async def _search_inventory_hops(
    db: AsyncSession,
    query: Optional[str] = None,
    min_amount_grams: Optional[float] = None,
    form: Optional[str] = None,
    limit: int = 20
) -> dict[str, Any]:
    """Search the user's hop inventory."""
    from sqlalchemy.orm import selectinload

    stmt = select(HopInventory).order_by(HopInventory.variety)

    if query:
        stmt = stmt.where(HopInventory.variety.ilike(f"%{query}%"))
    if min_amount_grams is not None:
        stmt = stmt.where(HopInventory.amount_grams >= min_amount_grams)
    if form:
        stmt = stmt.where(HopInventory.form == form)

    stmt = stmt.limit(limit)

    result = await db.execute(stmt)
    hops = result.scalars().all()

    if not hops:
        return {
            "count": 0,
            "message": "No hops found in inventory",
            "hops": []
        }

    return {
        "count": len(hops),
        "hops": [
            {
                "id": h.id,
                "variety": h.variety,
                "amount_grams": round(h.amount_grams, 1),
                "alpha_acid_percent": h.alpha_acid_percent,
                "form": h.form,
                "crop_year": h.crop_year,
                "storage_location": h.storage_location,
            }
            for h in hops
        ]
    }


async def _search_inventory_yeast(
    db: AsyncSession,
    query: Optional[str] = None,
    type: Optional[str] = None,
    form: Optional[str] = None,
    include_expired: bool = False,
    limit: int = 20
) -> dict[str, Any]:
    """Search the user's yeast inventory."""
    from sqlalchemy.orm import selectinload

    stmt = (
        select(YeastInventory)
        .options(selectinload(YeastInventory.yeast_strain))
        .order_by(YeastInventory.expiry_date.asc().nullsfirst())
    )

    if query:
        # Search in both yeast strain name and custom name
        stmt = stmt.outerjoin(YeastStrain).where(
            or_(
                YeastInventory.custom_name.ilike(f"%{query}%"),
                YeastStrain.name.ilike(f"%{query}%"),
                YeastStrain.product_id.ilike(f"%{query}%"),
            )
        )

    if type:
        stmt = stmt.outerjoin(YeastStrain).where(YeastStrain.type == type.lower())

    if form:
        stmt = stmt.where(YeastInventory.form == form)

    if not include_expired:
        now = datetime.now(timezone.utc)
        stmt = stmt.where(
            or_(
                YeastInventory.expiry_date.is_(None),
                YeastInventory.expiry_date > now,
            )
        )

    stmt = stmt.limit(limit)

    result = await db.execute(stmt)
    yeasts = result.scalars().all()

    if not yeasts:
        return {
            "count": 0,
            "message": "No yeast found in inventory",
            "yeasts": []
        }

    now = datetime.now(timezone.utc)

    return {
        "count": len(yeasts),
        "yeasts": [
            {
                "id": y.id,
                "name": y.yeast_strain.name if y.yeast_strain else y.custom_name,
                "producer": y.yeast_strain.producer if y.yeast_strain else None,
                "product_id": y.yeast_strain.product_id if y.yeast_strain else None,
                "type": y.yeast_strain.type if y.yeast_strain else None,
                "quantity": y.quantity,
                "form": y.form,
                "expiry_date": y.expiry_date.isoformat() if y.expiry_date else None,
                "days_until_expiry": (y.expiry_date - now).days if y.expiry_date else None,
                "generation": y.generation,
                "storage_location": y.storage_location,
            }
            for y in yeasts
        ]
    }


async def _check_recipe_ingredients(
    db: AsyncSession,
    hop_varieties: Optional[list[str]] = None,
    yeast_query: Optional[str] = None
) -> dict[str, Any]:
    """Check if user has specific hops and yeast in inventory."""
    result = {
        "hops": {"requested": [], "available": [], "missing": []},
        "yeast": {"requested": None, "available": [], "found": False}
    }

    # Check hops
    if hop_varieties:
        result["hops"]["requested"] = hop_varieties
        for variety in hop_varieties:
            stmt = select(HopInventory).where(
                HopInventory.variety.ilike(f"%{variety}%"),
                HopInventory.amount_grams > 0
            )
            hop_result = await db.execute(stmt)
            hops = hop_result.scalars().all()

            if hops:
                for h in hops:
                    result["hops"]["available"].append({
                        "variety": h.variety,
                        "amount_grams": round(h.amount_grams, 1),
                        "alpha_acid_percent": h.alpha_acid_percent,
                    })
            else:
                result["hops"]["missing"].append(variety)

    # Check yeast
    if yeast_query:
        result["yeast"]["requested"] = yeast_query
        now = datetime.now(timezone.utc)

        from sqlalchemy.orm import selectinload
        stmt = (
            select(YeastInventory)
            .options(selectinload(YeastInventory.yeast_strain))
            .outerjoin(YeastStrain)
            .where(
                YeastInventory.quantity > 0,
                or_(
                    YeastInventory.expiry_date.is_(None),
                    YeastInventory.expiry_date > now,
                ),
                or_(
                    YeastInventory.custom_name.ilike(f"%{yeast_query}%"),
                    YeastStrain.name.ilike(f"%{yeast_query}%"),
                    YeastStrain.product_id.ilike(f"%{yeast_query}%"),
                    YeastStrain.type.ilike(f"%{yeast_query}%"),
                )
            )
        )

        yeast_result = await db.execute(stmt)
        yeasts = yeast_result.scalars().all()

        if yeasts:
            result["yeast"]["found"] = True
            for y in yeasts:
                result["yeast"]["available"].append({
                    "name": y.yeast_strain.name if y.yeast_strain else y.custom_name,
                    "product_id": y.yeast_strain.product_id if y.yeast_strain else None,
                    "quantity": y.quantity,
                    "form": y.form,
                    "days_until_expiry": (y.expiry_date - now).days if y.expiry_date else None,
                })

    return result


async def _get_inventory_summary(db: AsyncSession) -> dict[str, Any]:
    """Get a summary of the user's brewing inventory."""
    now = datetime.now(timezone.utc)
    expiry_cutoff = now + timedelta(days=30)

    # Hop summary
    hop_result = await db.execute(
        select(
            func.count(HopInventory.id).label("total_items"),
            func.sum(HopInventory.amount_grams).label("total_grams"),
            func.count(func.distinct(HopInventory.variety)).label("unique_varieties"),
        )
    )
    hop_row = hop_result.one()

    # Yeast summary
    yeast_result = await db.execute(
        select(
            func.count(YeastInventory.id).label("total_items"),
            func.sum(YeastInventory.quantity).label("total_quantity"),
        ).where(YeastInventory.quantity > 0)
    )
    yeast_row = yeast_result.one()

    # Expiring soon
    expiring_result = await db.execute(
        select(func.count(YeastInventory.id)).where(
            YeastInventory.expiry_date.is_not(None),
            YeastInventory.expiry_date <= expiry_cutoff,
            YeastInventory.expiry_date > now,
            YeastInventory.quantity > 0,
        )
    )
    expiring_count = expiring_result.scalar() or 0

    return {
        "hops": {
            "total_items": hop_row.total_items or 0,
            "total_grams": round(hop_row.total_grams or 0, 1),
            "unique_varieties": hop_row.unique_varieties or 0,
        },
        "yeast": {
            "total_items": yeast_row.total_items or 0,
            "total_quantity": yeast_row.total_quantity or 0,
            "expiring_within_30_days": expiring_count,
        }
    }
