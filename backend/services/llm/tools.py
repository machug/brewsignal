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
    YeastStrain, Style, HopInventory, YeastInventory, Equipment,
    Batch, Recipe, Reading, Device, AmbientReading, RecipeCulture,
    HopVariety, Fermentable
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
    {
        "type": "function",
        "function": {
            "name": "get_equipment",
            "description": "Get the user's brewing equipment. Use this to find batch sizes (fermenter capacity), brewing systems, and equipment details. Essential for determining appropriate recipe scaling.",
            "parameters": {
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": ["fermenter", "kettle", "all_in_one", "mash_tun", "pump", "chiller", "mill", "bottling", "kegging", "other"],
                        "description": "Filter by equipment type"
                    },
                    "active_only": {
                        "type": "boolean",
                        "description": "Only return active equipment (default: true)"
                    }
                },
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
    },
    {
        "type": "function",
        "function": {
            "name": "save_recipe",
            "description": "Save a BeerJSON recipe to the user's recipe library. Use this when you've helped the user create or design a recipe and they want to save it. The recipe data should be in BeerJSON format with name, ingredients (fermentables, hops, cultures), and vitals (OG, FG, IBU, etc.).",
            "parameters": {
                "type": "object",
                "properties": {
                    "recipe": {
                        "type": "object",
                        "description": "BeerJSON recipe object containing name, type, batch_size, original_gravity, final_gravity, ingredients (with fermentable_additions, hop_additions, culture_additions), and other recipe data"
                    },
                    "name_override": {
                        "type": "string",
                        "description": "Optional name to use instead of the name in the recipe object"
                    }
                },
                "required": ["recipe"]
            }
        }
    },
    # =============================================================================
    # Ingredient Reference Library Tools
    # =============================================================================
    {
        "type": "function",
        "function": {
            "name": "search_hop_varieties",
            "description": "Search the hop variety reference database. Returns hop varieties with their alpha/beta acids, aroma profiles, and substitutes. Use this when the user asks about hop characteristics, recommendations, or needs help choosing hops for a recipe.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search term to match against hop name, aroma profile, or description (e.g., 'Citra', 'citrus', 'pine', 'floral')"
                    },
                    "purpose": {
                        "type": "string",
                        "enum": ["bittering", "aroma", "dual"],
                        "description": "Filter by hop purpose"
                    },
                    "origin": {
                        "type": "string",
                        "description": "Filter by origin country/region (e.g., 'USA', 'Germany', 'New Zealand')"
                    },
                    "min_alpha": {
                        "type": "number",
                        "description": "Minimum alpha acid percentage (for high-alpha bittering hops)"
                    },
                    "max_alpha": {
                        "type": "number",
                        "description": "Maximum alpha acid percentage (for low-alpha aroma hops)"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results to return (default: 15)"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_fermentables",
            "description": "Search the fermentables reference database (grains, sugars, extracts, adjuncts). Returns fermentables with their color, extract potential, diastatic power, and flavor profiles. Use this when the user asks about grain characteristics, malt recommendations, or needs help building a grain bill.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search term to match against name, flavor profile, or description (e.g., 'Pilsner', 'caramel', 'Munich', 'biscuit')"
                    },
                    "type": {
                        "type": "string",
                        "enum": ["base", "specialty", "adjunct", "sugar", "extract", "fruit", "other"],
                        "description": "Filter by fermentable type"
                    },
                    "origin": {
                        "type": "string",
                        "description": "Filter by origin country/region (e.g., 'Germany', 'Belgium', 'USA')"
                    },
                    "maltster": {
                        "type": "string",
                        "description": "Filter by maltster/manufacturer (e.g., 'Weyermann', 'Briess', 'Castle')"
                    },
                    "max_color_srm": {
                        "type": "number",
                        "description": "Maximum color in SRM (for lighter malts)"
                    },
                    "min_color_srm": {
                        "type": "number",
                        "description": "Minimum color in SRM (for darker specialty malts)"
                    },
                    "min_diastatic_power": {
                        "type": "number",
                        "description": "Minimum diastatic power in Lintner (for base malts with enzymatic conversion)"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results to return (default: 15)"
                    }
                },
                "required": []
            }
        }
    },
    # =============================================================================
    # System / Utility Tools
    # =============================================================================
    {
        "type": "function",
        "function": {
            "name": "get_current_datetime",
            "description": "Get the current date and time. Use this when you need to know today's date, current time, or when calculating future dates (e.g., when fermentation will complete). Always call this tool when making date/time-based predictions.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
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
    elif tool_name == "get_equipment":
        return await _get_equipment(db, **arguments)
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
    elif tool_name == "save_recipe":
        return await _save_recipe(db, **arguments)
    # Ingredient reference library tools
    elif tool_name == "search_hop_varieties":
        return await _search_hop_varieties(db, **arguments)
    elif tool_name == "search_fermentables":
        return await _search_fermentables(db, **arguments)
    # System / utility tools
    elif tool_name == "get_current_datetime":
        return _get_current_datetime()
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
                "days_until_expiry": (y.expiry_date.replace(tzinfo=timezone.utc) - now).days if y.expiry_date else None,
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
                    "days_until_expiry": (y.expiry_date.replace(tzinfo=timezone.utc) - now).days if y.expiry_date else None,
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


async def _get_equipment(
    db: AsyncSession,
    type: Optional[str] = None,
    active_only: bool = True
) -> dict[str, Any]:
    """Get user's brewing equipment."""
    stmt = select(Equipment).order_by(Equipment.type, Equipment.name)

    if type:
        stmt = stmt.where(Equipment.type == type)

    if active_only:
        stmt = stmt.where(Equipment.is_active == True)

    result = await db.execute(stmt)
    equipment_list = result.scalars().all()

    if not equipment_list:
        return {
            "count": 0,
            "message": "No equipment found. Add your brewing equipment in the Inventory page.",
            "equipment": [],
            "brewing_defaults": None
        }

    # Find primary fermenter or all-in-one for default batch size
    primary_fermenter = None
    for eq in equipment_list:
        if eq.type in ("fermenter", "all_in_one") and eq.capacity_liters:
            if primary_fermenter is None or eq.type == "all_in_one":
                primary_fermenter = eq

    brewing_defaults = None
    if primary_fermenter:
        # Default batch size is typically 80-90% of fermenter capacity for headspace
        default_batch_size = round(primary_fermenter.capacity_liters * 0.85, 1)
        brewing_defaults = {
            "batch_size_liters": default_batch_size,
            "fermenter_capacity_liters": primary_fermenter.capacity_liters,
            "primary_fermenter": primary_fermenter.name,
            "efficiency_percent": 72  # Default efficiency - could be made configurable
        }

    return {
        "count": len(equipment_list),
        "equipment": [
            {
                "id": eq.id,
                "name": eq.name,
                "type": eq.type,
                "brand": eq.brand,
                "model": eq.model,
                "capacity_liters": eq.capacity_liters,
                "capacity_kg": eq.capacity_kg,
                "is_active": eq.is_active,
                "notes": eq.notes,
            }
            for eq in equipment_list
        ],
        "brewing_defaults": brewing_defaults
    }


# =============================================================================
# Ingredient Reference Library Tools
# =============================================================================

async def _search_hop_varieties(
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


async def _search_fermentables(
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


# =============================================================================
# Fermentation Monitoring Tools
# =============================================================================

async def _list_fermentations(
    db: AsyncSession,
    status: Optional[str] = None,
    limit: int = 10
) -> dict[str, Any]:
    """List fermentation batches with current progress."""
    from sqlalchemy.orm import selectinload

    # Build query with eager loading
    stmt = (
        select(Batch)
        .options(
            selectinload(Batch.recipe).selectinload(Recipe.style),
            selectinload(Batch.recipe).selectinload(Recipe.cultures),
            selectinload(Batch.device),
            selectinload(Batch.yeast_strain),
        )
        .where(Batch.deleted_at.is_(None))  # Exclude deleted
    )

    # Filter by status
    if status and status != "all":
        stmt = stmt.where(Batch.status == status)

    # Order by most recently active
    stmt = stmt.order_by(Batch.updated_at.desc()).limit(limit)

    result = await db.execute(stmt)
    batches = result.scalars().all()

    if not batches:
        return {
            "count": 0,
            "message": "No fermentation batches found",
            "batches": []
        }

    now = datetime.now(timezone.utc)
    batch_list = []

    for batch in batches:
        # Get live reading if available
        live_reading = latest_readings.get(batch.device_id) if batch.device_id else None

        # Calculate days fermenting
        days_fermenting = None
        if batch.start_time:
            start = batch.start_time.replace(tzinfo=timezone.utc) if batch.start_time.tzinfo is None else batch.start_time
            delta = now - start
            days_fermenting = round(delta.total_seconds() / 86400, 1)

        # Calculate progress
        progress_percent = None
        current_sg = live_reading.get("sg") if live_reading else None
        if batch.measured_og and current_sg:
            target_fg = batch.recipe.fg if batch.recipe and batch.recipe.fg else 1.010
            if batch.measured_og > target_fg:
                progress = (batch.measured_og - current_sg) / (batch.measured_og - target_fg) * 100
                progress_percent = min(100.0, max(0.0, round(progress, 1)))

        # Get yeast info
        yeast_name = None
        temp_min = None
        temp_max = None
        if batch.yeast_strain:
            yeast_name = batch.yeast_strain.name
            temp_min = batch.yeast_strain.temp_low
            temp_max = batch.yeast_strain.temp_high
        elif batch.recipe and batch.recipe.cultures:
            culture = batch.recipe.cultures[0]
            yeast_name = culture.name
            temp_min = culture.temp_min_c
            temp_max = culture.temp_max_c

        # Temperature status
        current_temp = live_reading.get("temp") if live_reading else None
        temp_status = "unknown"
        if current_temp is not None and temp_min is not None and temp_max is not None:
            if current_temp < temp_min:
                temp_status = "too_cold"
            elif current_temp > temp_max:
                temp_status = "too_warm"
            else:
                temp_status = "in_range"

        batch_list.append({
            "batch_id": batch.id,
            "name": batch.name or (batch.recipe.name if batch.recipe else f"Batch #{batch.id}"),
            "recipe_name": batch.recipe.name if batch.recipe else None,
            "style": batch.recipe.style.name if batch.recipe and batch.recipe.style else None,
            "status": batch.status,
            "device_id": batch.device_id,
            "days_fermenting": days_fermenting,
            "current_sg": current_sg,
            "current_temp_c": current_temp,
            "measured_og": batch.measured_og,
            "target_fg": batch.recipe.fg if batch.recipe else None,
            "progress_percent": progress_percent,
            "yeast_name": yeast_name,
            "temp_status": temp_status,
        })

    return {
        "count": len(batch_list),
        "batches": batch_list
    }


async def _get_fermentation_status(
    db: AsyncSession,
    batch_id: int
) -> dict[str, Any]:
    """Get comprehensive status for a specific fermentation batch."""
    from sqlalchemy.orm import selectinload

    # Query batch with all relationships
    stmt = (
        select(Batch)
        .options(
            selectinload(Batch.recipe).selectinload(Recipe.style),
            selectinload(Batch.recipe).selectinload(Recipe.cultures),
            selectinload(Batch.device),
            selectinload(Batch.yeast_strain),
        )
        .where(Batch.id == batch_id)
    )

    result = await db.execute(stmt)
    batch = result.scalar_one_or_none()

    if not batch:
        return {"error": f"Batch not found: {batch_id}"}

    now = datetime.now(timezone.utc)

    # Get live reading
    live_reading = latest_readings.get(batch.device_id) if batch.device_id else None
    current_sg = live_reading.get("sg") if live_reading else None
    current_temp = live_reading.get("temp") if live_reading else None
    reading_confidence = live_reading.get("confidence") if live_reading else None
    reading_time = live_reading.get("timestamp") if live_reading else None

    # Build batch info
    batch_info = {
        "id": batch.id,
        "name": batch.name or (batch.recipe.name if batch.recipe else f"Batch #{batch.id}"),
        "status": batch.status,
        "brew_date": batch.brew_date.isoformat() if batch.brew_date else None,
        "start_time": batch.start_time.isoformat() if batch.start_time else None,
        "measured_og": batch.measured_og,
        "measured_fg": batch.measured_fg,
        "notes": batch.notes,
    }

    # Build recipe info
    recipe_info = None
    if batch.recipe:
        recipe_info = {
            "name": batch.recipe.name,
            "style": batch.recipe.style.name if batch.recipe.style else None,
            "target_og": batch.recipe.og,
            "target_fg": batch.recipe.fg,
            "target_abv": batch.recipe.abv,
            "primary_temp_c": batch.recipe.primary_temp_c,
        }

    # Build device info
    device_info = None
    if batch.device:
        device_info = {
            "id": batch.device.id,
            "type": batch.device.device_type,
            "name": batch.device.display_name or batch.device.name,
            "battery_voltage": batch.device.battery_voltage,
        }

    # Current reading
    current_reading = None
    if live_reading:
        current_reading = {
            "sg": current_sg,
            "temp_c": current_temp,
            "confidence": reading_confidence,
            "timestamp": reading_time,
            "sg_rate": live_reading.get("sg_rate"),
            "temp_rate": live_reading.get("temp_rate"),
        }

    # Progress calculations
    progress_info = {"available": False}
    if batch.measured_og and current_sg:
        target_fg = batch.recipe.fg if batch.recipe and batch.recipe.fg else 1.010
        if batch.measured_og > target_fg:
            progress = (batch.measured_og - current_sg) / (batch.measured_og - target_fg) * 100
            progress_percent = min(100.0, max(0.0, round(progress, 1)))
            current_attenuation = (batch.measured_og - current_sg) / (batch.measured_og - 1.0) * 100

            progress_info = {
                "available": True,
                "percent_complete": progress_percent,
                "current_attenuation": round(current_attenuation, 1),
                "gravity_drop": round(batch.measured_og - current_sg, 4),
                "remaining_gravity": round(current_sg - target_fg, 4) if current_sg > target_fg else 0,
            }

    # Days fermenting
    if batch.start_time:
        start = batch.start_time.replace(tzinfo=timezone.utc) if batch.start_time.tzinfo is None else batch.start_time
        delta = now - start
        progress_info["days_fermenting"] = round(delta.total_seconds() / 86400, 1)

    # Temperature analysis
    temp_info = {"available": False}
    yeast_temp_min = None
    yeast_temp_max = None
    yeast_name = None

    if batch.yeast_strain:
        yeast_name = batch.yeast_strain.name
        yeast_temp_min = batch.yeast_strain.temp_low
        yeast_temp_max = batch.yeast_strain.temp_high
    elif batch.recipe and batch.recipe.cultures:
        culture = batch.recipe.cultures[0]
        yeast_name = culture.name
        yeast_temp_min = culture.temp_min_c
        yeast_temp_max = culture.temp_max_c

    if current_temp is not None:
        temp_info = {
            "available": True,
            "current_c": current_temp,
            "yeast_name": yeast_name,
            "yeast_min_c": yeast_temp_min,
            "yeast_max_c": yeast_temp_max,
            "target_c": batch.temp_target,
        }

        if yeast_temp_min is not None and yeast_temp_max is not None:
            if current_temp < yeast_temp_min:
                temp_info["status"] = "too_cold"
                temp_info["deviation_c"] = round(yeast_temp_min - current_temp, 1)
                temp_info["message"] = f"Temperature is {temp_info['deviation_c']}°C below yeast minimum"
            elif current_temp > yeast_temp_max:
                temp_info["status"] = "too_warm"
                temp_info["deviation_c"] = round(current_temp - yeast_temp_max, 1)
                temp_info["message"] = f"Temperature is {temp_info['deviation_c']}°C above yeast maximum"
            else:
                temp_info["status"] = "in_range"
                temp_info["message"] = "Temperature is within yeast tolerance"
        else:
            temp_info["status"] = "unknown"
            temp_info["message"] = "Yeast temperature range not specified"

    # ML predictions
    predictions = {"available": False}
    if batch.device_id:
        try:
            from backend.main import get_ml_manager
            ml_mgr = get_ml_manager()
            if ml_mgr:
                expected_fg = batch.recipe.fg if batch.recipe and batch.recipe.fg else None
                state = ml_mgr.get_device_state(batch.device_id, expected_fg=expected_fg)
                if state and state.get("predictions"):
                    pred = state["predictions"]
                    predictions = {
                        "available": True,
                        "predicted_fg": pred.get("predicted_fg"),
                        "hours_to_completion": pred.get("hours_to_completion"),
                        "confidence": pred.get("confidence"),
                    }
        except Exception as e:
            logger.warning(f"Failed to get ML predictions: {e}")

    # Build alerts
    alerts = []
    if temp_info.get("status") == "too_cold":
        alerts.append({
            "type": "temperature",
            "severity": "warning",
            "message": temp_info["message"]
        })
    elif temp_info.get("status") == "too_warm":
        alerts.append({
            "type": "temperature",
            "severity": "warning",
            "message": temp_info["message"]
        })

    if live_reading and live_reading.get("is_anomaly"):
        alerts.append({
            "type": "anomaly",
            "severity": "info",
            "message": f"Anomaly detected: {live_reading.get('anomaly_reasons', 'unknown reason')}"
        })

    # Stalled fermentation check
    if progress_info.get("available") and current_reading:
        sg_rate = current_reading.get("sg_rate")
        if sg_rate is not None and abs(sg_rate) < 0.0001 and progress_info.get("percent_complete", 0) < 90:
            alerts.append({
                "type": "stalled",
                "severity": "warning",
                "message": "Fermentation appears stalled - gravity not changing"
            })

    return {
        "found": True,
        "batch": batch_info,
        "recipe": recipe_info,
        "device": device_info,
        "current_reading": current_reading,
        "progress": progress_info,
        "temperature": temp_info,
        "predictions": predictions,
        "alerts": alerts,
    }


async def _get_fermentation_history(
    db: AsyncSession,
    batch_id: int,
    hours: int = 24,
    include_anomalies_only: bool = False
) -> dict[str, Any]:
    """Get historical readings for a batch with trend analysis."""
    from sqlalchemy.orm import selectinload

    # Validate hours
    hours = min(720, max(1, hours))  # 1 hour to 30 days

    # First verify batch exists
    batch_stmt = (
        select(Batch)
        .options(selectinload(Batch.recipe))
        .where(Batch.id == batch_id)
    )
    batch_result = await db.execute(batch_stmt)
    batch = batch_result.scalar_one_or_none()

    if not batch:
        return {"error": f"Batch not found: {batch_id}"}

    # Query readings
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    stmt = (
        select(Reading)
        .where(
            Reading.batch_id == batch_id,
            Reading.timestamp >= cutoff
        )
        .order_by(Reading.timestamp.asc())
    )

    if include_anomalies_only:
        stmt = stmt.where(Reading.is_anomaly == True)

    result = await db.execute(stmt)
    readings = result.scalars().all()

    if not readings:
        return {
            "batch_id": batch_id,
            "batch_name": batch.name or (batch.recipe.name if batch.recipe else f"Batch #{batch.id}"),
            "hours_requested": hours,
            "count": 0,
            "message": "No readings found in the specified time period",
            "readings": []
        }

    # Calculate summary statistics
    sg_values = [r.sg_calibrated or r.sg_raw for r in readings if (r.sg_calibrated or r.sg_raw)]
    temp_values = [r.temp_calibrated or r.temp_raw for r in readings if (r.temp_calibrated or r.temp_raw)]

    summary = {}
    if sg_values:
        summary["sg"] = {
            "min": round(min(sg_values), 4),
            "max": round(max(sg_values), 4),
            "start": round(sg_values[0], 4),
            "end": round(sg_values[-1], 4),
            "change": round(sg_values[-1] - sg_values[0], 4),
        }

    if temp_values:
        summary["temp_c"] = {
            "min": round(min(temp_values), 1),
            "max": round(max(temp_values), 1),
            "avg": round(sum(temp_values) / len(temp_values), 1),
        }

    # Calculate trend (simple linear regression approximation)
    trend_analysis = {}
    if len(sg_values) >= 2:
        # Points per hour rate
        time_span_hours = (readings[-1].timestamp - readings[0].timestamp).total_seconds() / 3600
        if time_span_hours > 0:
            sg_rate_per_hour = (sg_values[-1] - sg_values[0]) / time_span_hours
            trend_analysis["sg_rate_per_hour"] = round(sg_rate_per_hour, 6)

            if sg_rate_per_hour < -0.001:
                trend_analysis["sg_trend"] = "actively_fermenting"
            elif sg_rate_per_hour < -0.0001:
                trend_analysis["sg_trend"] = "slowly_fermenting"
            else:
                trend_analysis["sg_trend"] = "stable"

    if len(temp_values) >= 2:
        time_span_hours = (readings[-1].timestamp - readings[0].timestamp).total_seconds() / 3600
        if time_span_hours > 0:
            temp_rate = (temp_values[-1] - temp_values[0]) / time_span_hours
            trend_analysis["temp_rate_per_hour"] = round(temp_rate, 3)

            if temp_rate > 0.5:
                trend_analysis["temp_trend"] = "rising"
            elif temp_rate < -0.5:
                trend_analysis["temp_trend"] = "falling"
            else:
                trend_analysis["temp_trend"] = "stable"

    # Sample readings (downsample if too many)
    max_readings = 50
    sample_readings = []
    if len(readings) <= max_readings:
        sample_readings = readings
    else:
        # Evenly sample
        step = len(readings) / max_readings
        indices = [int(i * step) for i in range(max_readings)]
        sample_readings = [readings[i] for i in indices]

    readings_list = [
        {
            "timestamp": r.timestamp.isoformat(),
            "sg": r.sg_calibrated or r.sg_raw,
            "temp_c": r.temp_calibrated or r.temp_raw,
            "confidence": r.confidence,
            "is_anomaly": r.is_anomaly,
            "anomaly_reasons": r.anomaly_reasons,
        }
        for r in sample_readings
    ]

    return {
        "batch_id": batch_id,
        "batch_name": batch.name or (batch.recipe.name if batch.recipe else f"Batch #{batch.id}"),
        "hours_requested": hours,
        "time_range": {
            "start": readings[0].timestamp.isoformat(),
            "end": readings[-1].timestamp.isoformat(),
        },
        "count": len(readings),
        "summary": summary,
        "trend_analysis": trend_analysis,
        "readings": readings_list,
    }


async def _get_ambient_conditions(db: AsyncSession) -> dict[str, Any]:
    """Get current ambient temperature and humidity."""
    # Get most recent ambient reading
    stmt = (
        select(AmbientReading)
        .order_by(AmbientReading.timestamp.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    ambient = result.scalar_one_or_none()

    now = datetime.now(timezone.utc)

    response = {
        "available": False,
        "message": "No ambient sensor data available"
    }

    if ambient:
        age_minutes = (now - ambient.timestamp).total_seconds() / 60
        response = {
            "available": True,
            "temperature_c": ambient.temperature,
            "humidity_percent": ambient.humidity,
            "timestamp": ambient.timestamp.isoformat(),
            "age_minutes": round(age_minutes, 1),
            "entity_id": ambient.entity_id,
        }

        if age_minutes > 30:
            response["warning"] = "Data may be stale (over 30 minutes old)"

    # Get active fermentations to compare
    batch_stmt = (
        select(Batch)
        .where(
            Batch.deleted_at.is_(None),
            Batch.status.in_(["fermenting", "conditioning"])
        )
    )
    batch_result = await db.execute(batch_stmt)
    active_batches = batch_result.scalars().all()

    if active_batches and response.get("available"):
        comparisons = []
        for batch in active_batches:
            if batch.device_id:
                live = latest_readings.get(batch.device_id)
                if live and live.get("temp") is not None:
                    delta = round(live["temp"] - response["temperature_c"], 1)
                    comparisons.append({
                        "batch_id": batch.id,
                        "batch_name": batch.name or f"Batch #{batch.id}",
                        "fermentation_temp_c": live["temp"],
                        "delta_from_ambient_c": delta,
                    })
        if comparisons:
            response["fermentation_comparisons"] = comparisons

    return response


async def _compare_batches(
    db: AsyncSession,
    batch_id: int,
    comparison_type: Optional[str] = "recipe",
    limit: int = 5
) -> dict[str, Any]:
    """Find similar historical batches for comparison."""
    from sqlalchemy.orm import selectinload

    # Get reference batch
    ref_stmt = (
        select(Batch)
        .options(
            selectinload(Batch.recipe).selectinload(Recipe.style),
            selectinload(Batch.recipe).selectinload(Recipe.cultures),
            selectinload(Batch.yeast_strain),
        )
        .where(Batch.id == batch_id)
    )
    ref_result = await db.execute(ref_stmt)
    ref_batch = ref_result.scalar_one_or_none()

    if not ref_batch:
        return {"error": f"Batch not found: {batch_id}"}

    # Build filter based on comparison type
    similar_stmt = (
        select(Batch)
        .options(
            selectinload(Batch.recipe).selectinload(Recipe.style),
            selectinload(Batch.yeast_strain),
        )
        .where(
            Batch.id != batch_id,
            Batch.deleted_at.is_(None),
            Batch.status.in_(["completed", "conditioning"])  # Only compare to finished batches
        )
    )

    comparison_type = comparison_type or "recipe"

    if comparison_type == "recipe" and ref_batch.recipe_id:
        similar_stmt = similar_stmt.where(Batch.recipe_id == ref_batch.recipe_id)
    elif comparison_type == "style" and ref_batch.recipe and ref_batch.recipe.style_id:
        # Join through recipe to style
        similar_stmt = similar_stmt.join(Recipe).where(Recipe.style_id == ref_batch.recipe.style_id)
    elif comparison_type == "yeast":
        # Match by yeast strain or recipe culture
        if ref_batch.yeast_strain_id:
            similar_stmt = similar_stmt.where(Batch.yeast_strain_id == ref_batch.yeast_strain_id)
        elif ref_batch.recipe and ref_batch.recipe.cultures:
            yeast_name = ref_batch.recipe.cultures[0].name
            # This is trickier - need to match by culture name
            similar_stmt = (
                similar_stmt
                .join(Recipe)
                .join(RecipeCulture)
                .where(RecipeCulture.name.ilike(f"%{yeast_name}%"))
            )

    similar_stmt = similar_stmt.order_by(Batch.end_time.desc().nullsfirst()).limit(limit)

    similar_result = await db.execute(similar_stmt)
    similar_batches = similar_result.scalars().all()

    # Build reference batch info
    ref_info = {
        "batch_id": ref_batch.id,
        "name": ref_batch.name or (ref_batch.recipe.name if ref_batch.recipe else f"Batch #{ref_batch.id}"),
        "recipe_name": ref_batch.recipe.name if ref_batch.recipe else None,
        "style": ref_batch.recipe.style.name if ref_batch.recipe and ref_batch.recipe.style else None,
        "status": ref_batch.status,
        "measured_og": ref_batch.measured_og,
        "measured_fg": ref_batch.measured_fg,
        "measured_abv": ref_batch.measured_abv,
        "measured_attenuation": ref_batch.measured_attenuation,
    }

    # Build similar batches list
    similar_list = []
    for batch in similar_batches:
        fermentation_days = None
        if batch.start_time and batch.end_time:
            fermentation_days = round((batch.end_time - batch.start_time).total_seconds() / 86400, 1)

        similar_list.append({
            "batch_id": batch.id,
            "name": batch.name or (batch.recipe.name if batch.recipe else f"Batch #{batch.id}"),
            "recipe_name": batch.recipe.name if batch.recipe else None,
            "style": batch.recipe.style.name if batch.recipe and batch.recipe.style else None,
            "brew_date": batch.brew_date.isoformat() if batch.brew_date else None,
            "measured_og": batch.measured_og,
            "measured_fg": batch.measured_fg,
            "measured_abv": batch.measured_abv,
            "measured_attenuation": batch.measured_attenuation,
            "fermentation_days": fermentation_days,
        })

    # Generate comparison insights
    insights = []
    if similar_list:
        # Compare OG/FG
        if ref_batch.measured_og:
            avg_og = sum(b["measured_og"] for b in similar_list if b["measured_og"]) / len([b for b in similar_list if b["measured_og"]]) if any(b["measured_og"] for b in similar_list) else None
            if avg_og:
                diff = round(ref_batch.measured_og - avg_og, 3)
                if abs(diff) > 0.005:
                    insights.append(f"OG is {abs(diff):.3f} {'higher' if diff > 0 else 'lower'} than average of similar batches")

        # Compare attenuation
        if ref_batch.measured_attenuation:
            attens = [b["measured_attenuation"] for b in similar_list if b["measured_attenuation"]]
            if attens:
                avg_atten = sum(attens) / len(attens)
                diff = ref_batch.measured_attenuation - avg_atten
                if abs(diff) > 5:
                    insights.append(f"Attenuation is {abs(diff):.1f}% {'higher' if diff > 0 else 'lower'} than average")

    return {
        "reference_batch": ref_info,
        "comparison_type": comparison_type,
        "similar_batches_count": len(similar_list),
        "similar_batches": similar_list,
        "insights": insights,
    }


async def _get_yeast_fermentation_advice(
    db: AsyncSession,
    yeast_query: str,
    batch_id: Optional[int] = None
) -> dict[str, Any]:
    """Get yeast-specific fermentation advice."""
    from sqlalchemy.orm import selectinload

    # Search for the yeast strain
    yeast_stmt = select(YeastStrain).where(
        or_(
            YeastStrain.product_id.ilike(f"%{yeast_query}%"),
            YeastStrain.name.ilike(f"%{yeast_query}%"),
        )
    ).limit(1)

    result = await db.execute(yeast_stmt)
    yeast = result.scalar_one_or_none()

    if not yeast:
        return {
            "found": False,
            "error": f"Yeast strain not found: {yeast_query}",
            "suggestion": "Try searching with a product ID (e.g., 'US-05', 'WLP001') or partial name"
        }

    # Build yeast profile
    yeast_profile = {
        "name": yeast.name,
        "producer": yeast.producer,
        "product_id": yeast.product_id,
        "type": yeast.type,
        "form": yeast.form,
        "temp_range_c": {
            "min": yeast.temp_low,
            "max": yeast.temp_high,
            "optimal": round((yeast.temp_low + yeast.temp_high) / 2, 1) if yeast.temp_low and yeast.temp_high else None,
        },
        "attenuation_range_percent": {
            "min": yeast.attenuation_low,
            "max": yeast.attenuation_high,
        },
        "flocculation": yeast.flocculation,
        "alcohol_tolerance": yeast.alcohol_tolerance,
        "description": yeast.description,
    }

    # Generate fermentation advice based on yeast characteristics
    advice = []

    # Temperature advice
    if yeast.temp_low and yeast.temp_high:
        optimal = round((yeast.temp_low + yeast.temp_high) / 2, 1)
        advice.append({
            "category": "temperature",
            "recommendation": f"Ferment at {yeast.temp_low}-{yeast.temp_high}°C. Optimal: {optimal}°C.",
            "details": "Lower temperatures generally produce cleaner flavors, higher temperatures produce more esters and phenols."
        })

        if yeast.type == "lager":
            advice.append({
                "category": "temperature",
                "recommendation": "Consider a diacetyl rest at 18-20°C for 2-3 days near the end of fermentation.",
                "details": "This helps the yeast clean up diacetyl (buttery flavor) before cold conditioning."
            })

    # Attenuation advice
    if yeast.attenuation_low and yeast.attenuation_high:
        if yeast.attenuation_high > 80:
            advice.append({
                "category": "attenuation",
                "recommendation": "This is a highly attenuative strain - expect a dry finish.",
                "details": f"Expected attenuation: {yeast.attenuation_low}-{yeast.attenuation_high}%"
            })
        elif yeast.attenuation_low < 70:
            advice.append({
                "category": "attenuation",
                "recommendation": "This is a low-attenuating strain - expect residual sweetness.",
                "details": f"Expected attenuation: {yeast.attenuation_low}-{yeast.attenuation_high}%"
            })

    # Flocculation advice
    if yeast.flocculation:
        if yeast.flocculation.lower() in ["high", "very high"]:
            advice.append({
                "category": "flocculation",
                "recommendation": "High flocculation - beer should clear quickly.",
                "details": "May need to rouse yeast if fermentation stalls. Consider a warmer finish to ensure complete attenuation."
            })
        elif yeast.flocculation.lower() in ["low", "very low"]:
            advice.append({
                "category": "flocculation",
                "recommendation": "Low flocculation - beer may take longer to clear.",
                "details": "Cold crashing or fining agents may help achieve clarity if desired."
            })

    # Pitch rate advice based on form
    if yeast.form == "dry":
        advice.append({
            "category": "pitching",
            "recommendation": "Rehydrate dry yeast in warm water (25-30°C) for 15-30 minutes before pitching.",
            "details": "Some brewers pitch directly, but rehydration can improve cell viability."
        })
    elif yeast.form == "liquid":
        advice.append({
            "category": "pitching",
            "recommendation": "Consider making a starter for liquid yeast, especially for high-gravity beers.",
            "details": "A 1-2L starter is typically sufficient for most ales under 1.060 OG."
        })

    # Batch-specific recommendations
    batch_specific = None
    if batch_id:
        batch_stmt = (
            select(Batch)
            .options(
                selectinload(Batch.recipe),
                selectinload(Batch.device),
            )
            .where(Batch.id == batch_id)
        )
        batch_result = await db.execute(batch_stmt)
        batch = batch_result.scalar_one_or_none()

        if batch:
            batch_specific = {
                "batch_id": batch.id,
                "batch_name": batch.name or (batch.recipe.name if batch.recipe else f"Batch #{batch.id}"),
            }

            # Check current temperature
            if batch.device_id:
                live = latest_readings.get(batch.device_id)
                if live and live.get("temp") is not None:
                    current_temp = live["temp"]
                    batch_specific["current_temp_c"] = current_temp

                    if yeast.temp_low and current_temp < yeast.temp_low:
                        batch_specific["temp_warning"] = f"Temperature ({current_temp}°C) is below yeast minimum ({yeast.temp_low}°C). Consider raising temperature."
                    elif yeast.temp_high and current_temp > yeast.temp_high:
                        batch_specific["temp_warning"] = f"Temperature ({current_temp}°C) is above yeast maximum ({yeast.temp_high}°C). Consider cooling."
                    else:
                        batch_specific["temp_status"] = "Temperature is within yeast tolerance range."

            # OG-specific advice
            if batch.measured_og:
                batch_specific["measured_og"] = batch.measured_og
                if batch.measured_og > 1.070:
                    batch_specific["high_gravity_note"] = "High gravity wort - ensure adequate yeast pitch rate and consider incremental feeding."

    return {
        "found": True,
        "yeast": yeast_profile,
        "advice": advice,
        "batch_specific": batch_specific,
    }


def _normalize_recipe_to_beerjson(recipe: dict[str, Any]) -> dict[str, Any]:
    """Normalize LLM-generated recipe data to BeerJSON format.

    The LLM may send recipes in various simplified formats. This function
    converts them to the strict BeerJSON format expected by RecipeSerializer.
    """
    normalized = {"name": recipe.get("name", "Untitled Recipe")}

    # Copy simple string/text fields
    for field in ["type", "author", "notes"]:
        if field in recipe:
            normalized[field] = recipe[field]

    # Normalize batch_size to unit object
    batch_size = recipe.get("batch_size") or recipe.get("batch_size_liters")
    if batch_size is not None:
        if isinstance(batch_size, dict):
            normalized["batch_size"] = batch_size
        else:
            normalized["batch_size"] = {"value": float(batch_size), "unit": "l"}

    # Normalize boil to unit object
    boil_time = recipe.get("boil_time") or recipe.get("boil_time_minutes")
    if boil_time is not None:
        boil_val = boil_time.get("value") if isinstance(boil_time, dict) else boil_time
        normalized["boil"] = {"boil_time": {"value": float(boil_val), "unit": "min"}}

    # Normalize efficiency
    efficiency = recipe.get("efficiency") or recipe.get("efficiency_percent")
    if efficiency is not None:
        if isinstance(efficiency, dict):
            # Could be {"brewhouse": 72} or {"brewhouse": {"value": 0.72}}
            brewhouse = efficiency.get("brewhouse", efficiency.get("value", efficiency))
            if isinstance(brewhouse, dict):
                eff_val = brewhouse.get("value", 0.72)
            else:
                eff_val = float(brewhouse)
        else:
            eff_val = float(efficiency)
        # Convert percentage to decimal if > 1
        if eff_val > 1:
            eff_val = eff_val / 100
        normalized["efficiency"] = {"brewhouse": {"value": eff_val, "unit": "%"}}

    # Normalize gravity values
    og = recipe.get("original_gravity") or recipe.get("og")
    if og is not None:
        if isinstance(og, dict):
            normalized["original_gravity"] = og
        else:
            normalized["original_gravity"] = {"value": float(og), "unit": "sg"}

    fg = recipe.get("final_gravity") or recipe.get("fg")
    if fg is not None:
        if isinstance(fg, dict):
            normalized["final_gravity"] = fg
        else:
            normalized["final_gravity"] = {"value": float(fg), "unit": "sg"}

    # Normalize ABV
    abv = recipe.get("alcohol_by_volume") or recipe.get("abv")
    if abv is not None:
        if isinstance(abv, dict):
            normalized["alcohol_by_volume"] = abv
        else:
            abv_val = float(abv)
            # Convert percentage to decimal if > 1
            if abv_val > 1:
                abv_val = abv_val / 100
            normalized["alcohol_by_volume"] = {"value": abv_val, "unit": "%"}

    # Normalize IBU
    ibu = recipe.get("ibu") or recipe.get("ibu_estimate")
    if ibu is not None:
        if isinstance(ibu, dict):
            normalized["ibu_estimate"] = ibu
        else:
            normalized["ibu_estimate"] = {"value": float(ibu), "unit": "IBUs"}

    # Normalize color
    color = recipe.get("color") or recipe.get("color_srm") or recipe.get("color_estimate")
    if color is not None:
        if isinstance(color, dict):
            normalized["color_estimate"] = color
        else:
            normalized["color_estimate"] = {"value": float(color), "unit": "SRM"}

    # Normalize ingredients
    ingredients = recipe.get("ingredients", {})
    normalized_ingredients = {}

    # Fermentables - can be "fermentable_additions" or "fermentables"
    fermentables = ingredients.get("fermentable_additions") or ingredients.get("fermentables") or recipe.get("fermentables", [])
    if fermentables:
        normalized_ferms = []
        for f in fermentables:
            norm_f = {"name": f.get("name", "Unknown Grain")}
            if "type" in f:
                norm_f["type"] = f["type"]

            # Amount
            amount = f.get("amount") or f.get("amount_kg")
            if amount is not None:
                if isinstance(amount, dict):
                    norm_f["amount"] = amount
                else:
                    norm_f["amount"] = {"value": float(amount), "unit": "kg"}

            # Color - use provided value or lookup default by grain name
            color = f.get("color") or f.get("color_lovibond") or f.get("color_srm")
            if color is not None:
                if isinstance(color, dict):
                    norm_f["color"] = color
                else:
                    norm_f["color"] = {"value": float(color), "unit": "Lovibond"}
            else:
                # Default colors (SRM) for common grains when not specified
                default_colors = {
                    # Base malts
                    "pale ale malt": 3, "pale malt": 2, "pilsner malt": 1.5, "pilsner": 1.5,
                    "maris otter": 3, "golden promise": 2.5, "vienna malt": 3.5, "vienna": 3.5,
                    "munich malt": 9, "munich": 9, "munich light": 6, "munich dark": 12,
                    # Wheat & other base grains
                    "wheat malt": 2, "wheat": 2, "white wheat": 2, "red wheat": 3,
                    "rye malt": 3, "rye": 3, "oat malt": 2,
                    # Adjuncts
                    "flaked oats": 1, "oats": 1, "flaked wheat": 1.5, "flaked barley": 2,
                    "flaked maize": 0.5, "corn": 0.5, "flaked rice": 0.5, "rice": 0.5,
                    # Crystal/Caramel malts
                    "carapils": 2, "carafoam": 2, "dextrin malt": 2,
                    "crystal 10": 10, "crystal 20": 20, "crystal 30": 30, "crystal 40": 40,
                    "crystal 60": 60, "crystal 80": 80, "crystal 120": 120,
                    "caramel 10": 10, "caramel 20": 20, "caramel 40": 40, "caramel 60": 60,
                    "caramel 80": 80, "caramel 120": 120, "caramunich": 50,
                    "caravienne": 20, "carahell": 10, "carared": 20,
                    # Roasted malts
                    "chocolate malt": 400, "chocolate": 400, "pale chocolate": 200,
                    "black malt": 500, "black patent": 550, "roasted barley": 500,
                    "carafa i": 350, "carafa ii": 450, "carafa iii": 550,
                    "midnight wheat": 550, "blackprinz": 500,
                    # Specialty malts
                    "biscuit malt": 25, "biscuit": 25, "victory malt": 28, "victory": 28,
                    "amber malt": 30, "brown malt": 65, "aromatic malt": 20, "aromatic": 20,
                    "melanoidin malt": 30, "melanoidin": 30, "honey malt": 25, "honey": 25,
                    "special b": 140, "special roast": 50,
                    # Sugars
                    "table sugar": 0, "cane sugar": 0, "corn sugar": 0, "dextrose": 0,
                    "brown sugar": 15, "belgian candi sugar": 1, "dark candi sugar": 80,
                    "honey": 2, "maple syrup": 35, "molasses": 80,
                }
                grain_name = f.get("name", "").lower().strip()
                if grain_name in default_colors:
                    norm_f["color"] = {"value": float(default_colors[grain_name]), "unit": "SRM"}

            # Yield
            yield_val = f.get("yield") or f.get("yield_percent")
            if yield_val is not None:
                if isinstance(yield_val, dict) and "fine_grind" in yield_val:
                    fg_val = yield_val["fine_grind"]
                    if isinstance(fg_val, dict):
                        norm_f["yield"] = {"fine_grind": fg_val}
                    else:
                        y = float(fg_val)
                        if y > 1:
                            y = y / 100
                        norm_f["yield"] = {"fine_grind": {"value": y, "unit": "%"}}
                elif isinstance(yield_val, (int, float)):
                    y = float(yield_val)
                    if y > 1:
                        y = y / 100
                    norm_f["yield"] = {"fine_grind": {"value": y, "unit": "%"}}

            normalized_ferms.append(norm_f)
        normalized_ingredients["fermentable_additions"] = normalized_ferms

    # Hops - can be "hop_additions" or "hops"
    hops = ingredients.get("hop_additions") or ingredients.get("hops") or recipe.get("hops", [])
    if hops:
        normalized_hops = []
        for h in hops:
            norm_h = {"name": h.get("name", "Unknown Hop")}
            if "form" in h:
                norm_h["form"] = h["form"]
            if "origin" in h:
                norm_h["origin"] = h["origin"]

            # Amount
            amount = h.get("amount") or h.get("amount_g") or h.get("amount_grams")
            if amount is not None:
                if isinstance(amount, dict):
                    norm_h["amount"] = amount
                else:
                    norm_h["amount"] = {"value": float(amount), "unit": "g"}

            # Alpha acid
            alpha = h.get("alpha_acid") or h.get("alpha_acid_percent") or h.get("alpha")
            if alpha is not None:
                if isinstance(alpha, dict):
                    norm_h["alpha_acid"] = alpha
                else:
                    a = float(alpha)
                    if a > 1:
                        a = a / 100
                    norm_h["alpha_acid"] = {"value": a, "unit": "%"}

            # Timing
            timing = h.get("timing")
            if timing:
                # Normalize timing.time → timing.duration for consistency
                if "time" in timing and "duration" not in timing:
                    timing = {**timing, "duration": timing.pop("time")}
                norm_h["timing"] = timing
            else:
                # Build timing from flat fields
                use = h.get("use", "boil")
                time_val = h.get("time") or h.get("time_min") or h.get("time_minutes")
                if time_val is not None:
                    if isinstance(time_val, dict):
                        norm_h["timing"] = {"use": use, "duration": time_val}
                    else:
                        norm_h["timing"] = {"use": use, "duration": {"value": float(time_val), "unit": "min"}}

            normalized_hops.append(norm_h)
        normalized_ingredients["hop_additions"] = normalized_hops

    # Cultures (yeast) - can be "culture_additions" or "cultures" or "yeast"
    cultures = ingredients.get("culture_additions") or ingredients.get("cultures") or recipe.get("cultures", [])
    yeast = recipe.get("yeast")
    if not cultures and yeast:
        # Convert single yeast object to culture_additions array
        cultures = [yeast] if isinstance(yeast, dict) else []

    if cultures:
        normalized_cultures = []
        for c in cultures:
            norm_c = {"name": c.get("name", "Unknown Yeast")}
            if "type" in c:
                norm_c["type"] = c["type"]
            if "form" in c:
                norm_c["form"] = c["form"]

            # Producer/lab
            producer = c.get("producer") or c.get("laboratory") or c.get("lab")
            if producer:
                norm_c["producer"] = producer

            if "product_id" in c:
                norm_c["product_id"] = c["product_id"]

            # Temperature range
            temp_range = c.get("temperature_range")
            if temp_range:
                norm_c["temperature_range"] = temp_range
            else:
                # Build from flat fields
                temp_min = c.get("temp_min") or c.get("temp_min_c")
                temp_max = c.get("temp_max") or c.get("temp_max_c")
                if temp_min is not None or temp_max is not None:
                    tr = {}
                    if temp_min is not None:
                        if isinstance(temp_min, dict):
                            tr["minimum"] = temp_min
                        else:
                            tr["minimum"] = {"value": float(temp_min), "unit": "C"}
                    if temp_max is not None:
                        if isinstance(temp_max, dict):
                            tr["maximum"] = temp_max
                        else:
                            tr["maximum"] = {"value": float(temp_max), "unit": "C"}
                    norm_c["temperature_range"] = tr

            # Attenuation
            atten = c.get("attenuation") or c.get("attenuation_range")
            if atten is not None:
                if isinstance(atten, dict) and ("minimum" in atten or "maximum" in atten or "value" in atten):
                    norm_c["attenuation"] = atten
                else:
                    a = float(atten) if not isinstance(atten, dict) else float(atten.get("value", 75))
                    if a > 1:
                        a = a / 100
                    norm_c["attenuation"] = {"minimum": {"value": a, "unit": "%"}}

            normalized_cultures.append(norm_c)
        normalized_ingredients["culture_additions"] = normalized_cultures

    if normalized_ingredients:
        normalized["ingredients"] = normalized_ingredients

    # Mash steps
    mash = recipe.get("mash")
    if mash and "mash_steps" in mash:
        normalized_mash = {"mash_steps": []}
        for step in mash["mash_steps"]:
            norm_step = {"name": step.get("name", step.get("type", "Mash Step"))}
            if "type" in step:
                norm_step["type"] = step["type"]

            # Temperature
            temp = step.get("step_temperature") or step.get("temperature") or step.get("temp")
            if temp is not None:
                if isinstance(temp, dict):
                    norm_step["step_temperature"] = temp
                else:
                    norm_step["step_temperature"] = {"value": float(temp), "unit": "C"}

            # Time
            time_val = step.get("step_time") or step.get("time") or step.get("time_minutes")
            if time_val is not None:
                if isinstance(time_val, dict):
                    norm_step["step_time"] = time_val
                else:
                    norm_step["step_time"] = {"value": float(time_val), "unit": "min"}

            normalized_mash["mash_steps"].append(norm_step)
        normalized["mash"] = normalized_mash
    elif recipe.get("mash_temp") or recipe.get("mash_time"):
        # Simple mash from flat fields
        mash_temp = recipe.get("mash_temp")
        mash_time = recipe.get("mash_time") or 60
        normalized["mash"] = {
            "mash_steps": [{
                "name": "Saccharification",
                "type": "infusion",
                "step_temperature": {"value": float(mash_temp), "unit": "C"} if mash_temp else {"value": 65, "unit": "C"},
                "step_time": {"value": float(mash_time), "unit": "min"}
            }]
        }

    return normalized


async def _save_recipe(
    db: AsyncSession,
    recipe: dict[str, Any],
    name_override: Optional[str] = None
) -> dict[str, Any]:
    """Save a BeerJSON recipe to the database."""
    from backend.services.serializers.recipe_serializer import RecipeSerializer

    if not recipe:
        return {"error": "Recipe data is required"}

    # Check if recipe has required name field
    if not recipe.get("name") and not name_override:
        return {"error": "Recipe must have a name (either in recipe.name or via name_override)"}

    # Apply name override if provided
    if name_override:
        recipe["name"] = name_override

    try:
        # Normalize the recipe to BeerJSON format
        normalized = _normalize_recipe_to_beerjson(recipe)
        logger.info(f"Normalized recipe: {normalized.get('name')}")

        # Use the RecipeSerializer to convert BeerJSON to SQLAlchemy model
        serializer = RecipeSerializer()
        db_recipe = await serializer.serialize(normalized, db)

        # Add to database
        db.add(db_recipe)
        await db.commit()

        # Re-fetch with eager loading to avoid lazy-load errors
        from sqlalchemy.orm import selectinload
        stmt = select(Recipe).options(
            selectinload(Recipe.fermentables),
            selectinload(Recipe.hops),
            selectinload(Recipe.cultures),
        ).where(Recipe.id == db_recipe.id)
        result = await db.execute(stmt)
        saved_recipe = result.scalar_one()

        # Build response with recipe summary
        return {
            "success": True,
            "recipe_id": saved_recipe.id,
            "name": saved_recipe.name,
            "type": saved_recipe.type,
            "batch_size_liters": saved_recipe.batch_size_liters,
            "og": saved_recipe.og,
            "fg": saved_recipe.fg,
            "abv": saved_recipe.abv,
            "ibu": saved_recipe.ibu,
            "color_srm": saved_recipe.color_srm,
            "fermentables_count": len(saved_recipe.fermentables),
            "hops_count": len(saved_recipe.hops),
            "cultures_count": len(saved_recipe.cultures),
            "message": f"Recipe '{saved_recipe.name}' saved successfully with ID {saved_recipe.id}",
        }

    except KeyError as e:
        await db.rollback()
        return {
            "error": f"Missing required field in recipe: {e}",
            "hint": "Ensure recipe has at minimum: name, and optionally ingredients.fermentable_additions, ingredients.hop_additions, ingredients.culture_additions"
        }
    except Exception as e:
        await db.rollback()
        logger.exception(f"Failed to save recipe: {e}")
        return {
            "error": f"Failed to save recipe: {str(e)}"
        }


# =============================================================================
# System / Utility Tools
# =============================================================================


def _get_current_datetime() -> dict[str, Any]:
    """Get the current date and time in the system timezone.

    Returns a dictionary with various date/time representations
    useful for making time-based calculations and predictions.
    """
    import zoneinfo

    # Get current time in UTC
    now_utc = datetime.now(timezone.utc)

    # Try to get local timezone, fallback to UTC
    try:
        # Try common Australian timezone (where the system is)
        local_tz = zoneinfo.ZoneInfo("Australia/Sydney")
        now_local = now_utc.astimezone(local_tz)
    except Exception:
        # Fallback to UTC if timezone not available
        now_local = now_utc
        local_tz = timezone.utc

    # Calculate day of week
    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    day_of_week = day_names[now_local.weekday()]

    return {
        "current_datetime": now_local.isoformat(),
        "date": now_local.strftime("%Y-%m-%d"),
        "time": now_local.strftime("%H:%M:%S"),
        "day_of_week": day_of_week,
        "timezone": str(local_tz),
        "timestamp_utc": now_utc.isoformat(),
        "unix_timestamp": int(now_utc.timestamp()),
        "human_readable": now_local.strftime("%A, %B %d, %Y at %I:%M %p"),
    }
