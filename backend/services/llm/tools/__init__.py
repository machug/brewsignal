"""AG-UI Tools for the AI brewing assistant.

This package defines tools that the LLM can call to query the database
for yeast strains, beer styles, and other brewing information.
"""

import logging
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

# Import all tool implementations from submodules
from .yeast_style import (
    search_yeast,
    search_styles,
    get_yeast_by_id,
    get_style_by_name,
)
from .inventory import (
    search_inventory_hops,
    search_inventory_yeast,
    check_recipe_ingredients,
    get_inventory_summary,
    get_equipment,
)
from .ingredients import (
    search_hop_varieties,
    search_fermentables,
)
from .fermentation import (
    list_fermentations,
    get_fermentation_status,
    get_fermentation_history,
    get_ambient_conditions,
    compare_batches,
    get_yeast_fermentation_advice,
)
from .recipe import (
    normalize_recipe_to_beerjson,
    calculate_recipe_stats,
    save_recipe,
    review_recipe_style,
)
from .utility import (
    get_current_datetime,
    strip_html_tags,
    fetch_url,
    rename_chat,
    list_recent_threads,
    get_thread_context,
    search_threads,
)

logger = logging.getLogger(__name__)

__all__ = ['TOOL_DEFINITIONS', 'execute_tool']

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
            "description": "Save a recipe to the user's recipe library. Include ALL ingredients as structured arrays: fermentables (with amounts in kg), hops (with amounts in grams and boil times), and cultures/yeast. The server automatically calculates OG, FG, ABV, IBU, and color from the ingredients - you don't need to calculate these.",
            "parameters": {
                "type": "object",
                "properties": {
                    "recipe": {
                        "type": "object",
                        "description": "Recipe object with structured ingredient arrays. Stats (OG/FG/ABV/IBU/SRM) are auto-calculated from ingredients.",
                        "properties": {
                            "name": {"type": "string", "description": "Recipe name"},
                            "type": {"type": "string", "enum": ["all-grain", "extract", "partial-mash"]},
                            "batch_size_liters": {"type": "number", "description": "Batch size in liters"},
                            "notes": {"type": "string", "description": "Recipe notes, brewing tips, etc."},
                            "fermentables": {
                                "type": "array",
                                "description": "REQUIRED: Array of grains/malts/sugars",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "name": {"type": "string", "description": "Grain name (e.g. 'Pale Malt', 'Crystal 40L')"},
                                        "amount_kg": {"type": "number", "description": "Amount in kg (e.g. 4.1)"},
                                        "color_srm": {"type": "number", "description": "Color in SRM/Lovibond"}
                                    },
                                    "required": ["name", "amount_kg"]
                                }
                            },
                            "hops": {
                                "type": "array",
                                "description": "REQUIRED: Array of hop additions",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "name": {"type": "string", "description": "Hop name (e.g. 'Centennial', 'Cascade')"},
                                        "amount_g": {"type": "number", "description": "Amount in grams"},
                                        "time_minutes": {"type": "number", "description": "Boil time in minutes (0 for flameout, -1 for dry hop)"},
                                        "use": {"type": "string", "enum": ["boil", "dry_hop", "whirlpool"], "description": "When hop is added"},
                                        "alpha_acid": {"type": "number", "description": "Alpha acid percentage"}
                                    },
                                    "required": ["name", "amount_g", "time_minutes"]
                                }
                            },
                            "cultures": {
                                "type": "array",
                                "description": "REQUIRED: Array of yeast - ALWAYS include the yeast for the recipe",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "name": {"type": "string", "description": "Yeast name (e.g. 'US-05', 'Safale S-04')"},
                                        "producer": {"type": "string", "description": "Yeast lab (e.g. 'Fermentis', 'White Labs')"},
                                        "product_id": {"type": "string", "description": "Product code (e.g. 'WLP001')"},
                                        "attenuation": {"type": "number", "description": "Expected attenuation % (e.g. 77)"}
                                    },
                                    "required": ["name"]
                                }
                            },
                            "mash_temp": {"type": "number", "description": "Mash temperature in Celsius"},
                            "mash_time": {"type": "number", "description": "Mash time in minutes"}
                        },
                        "required": ["name", "fermentables", "hops", "cultures"]
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
    {
        "type": "function",
        "function": {
            "name": "review_recipe_style",
            "description": "Review a recipe against BJCP style guidelines. Returns detailed compliance analysis showing which stats are in/out of range, suggestions for fixes, and optionally applies automatic corrections. Use this when checking if a recipe fits its target style or when the user wants style compliance verification.",
            "parameters": {
                "type": "object",
                "properties": {
                    "recipe_id": {
                        "type": "integer",
                        "description": "ID of the recipe to review"
                    },
                    "style_id": {
                        "type": "string",
                        "description": "Optional BJCP style ID to review against (e.g., 'bjcp-2021-18b'). If not provided, uses the recipe's assigned style."
                    },
                    "auto_fix": {
                        "type": "boolean",
                        "description": "If true, automatically adjust recipe to fit within style guidelines where possible (adjusts grain bill, hops, etc.)",
                        "default": False
                    }
                },
                "required": ["recipe_id"]
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
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_url",
            "description": "Fetch content from a URL. Use this to retrieve brewing articles, recipes, or reference material from the web. Returns the text content of the page.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL to fetch (e.g., 'https://www.brewersfriend.com/recipe/123')"
                    }
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "rename_chat",
            "description": "Rename the current chat thread to better reflect its content. Use this when the conversation has shifted to a new topic and the original title is no longer relevant. Choose a concise, descriptive title (max 60 chars).",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "New title for the chat (e.g., 'Raspberry Sour Recipe Development')"
                    }
                },
                "required": ["title"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_threads",
            "description": "Search previous chat conversations for a specific topic or keyword. Use SIMPLE, SINGLE-WORD queries for best results (e.g., 'stout', 'IPA', 'temperature'). Use this to recall information from past conversations when the user references something discussed before.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "A SINGLE keyword or short phrase to search for (e.g., 'stout', 'pilsner', 'yeast', 'fermentation'). Simpler queries work better."
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of threads to return (default: 5)"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_recent_threads",
            "description": "List recent conversations to see what has been discussed before. Use this FIRST when asked about previous conversations, to browse conversation history, or when you want to proactively recall relevant past discussions. Returns thread titles, dates, and previews.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Number of recent conversations to return (default: 10, max: 20)"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_thread_context",
            "description": "Get the full conversation from a previous chat thread. Use this after finding a relevant thread (via list_recent_threads or search_threads) to recall the complete discussion, decisions made, recipes created, or issues resolved.",
            "parameters": {
                "type": "object",
                "properties": {
                    "thread_id": {
                        "type": "string",
                        "description": "The thread ID to retrieve (from list_recent_threads or search_threads results)"
                    },
                    "max_messages": {
                        "type": "integer",
                        "description": "Maximum messages to retrieve (default: 20, max: 50)"
                    }
                },
                "required": ["thread_id"]
            }
        }
    }
]


async def execute_tool(
    db: AsyncSession,
    tool_name: str,
    arguments: dict[str, Any],
    thread_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> dict[str, Any]:
    """Execute a tool and return the result.

    Args:
        db: Database session
        tool_name: Name of the tool to execute
        arguments: Tool arguments
        thread_id: Current chat thread ID (for tools that need it)
        user_id: Current user ID for multi-tenant isolation

    Returns:
        Tool result as a dictionary
    """
    logger.info(f"Executing tool: {tool_name} with args: {arguments}")

    # Yeast and style tools
    if tool_name == "search_yeast":
        return await search_yeast(db, **arguments)
    elif tool_name == "search_styles":
        return await search_styles(db, **arguments)
    elif tool_name == "get_yeast_by_id":
        return await get_yeast_by_id(db, **arguments)
    elif tool_name == "get_style_by_name":
        return await get_style_by_name(db, **arguments)
    # Inventory tools (Note: inventory tables don't have user_id yet - future work)
    elif tool_name == "search_inventory_hops":
        return await search_inventory_hops(db, **arguments)
    elif tool_name == "search_inventory_yeast":
        return await search_inventory_yeast(db, **arguments)
    elif tool_name == "check_recipe_ingredients":
        return await check_recipe_ingredients(db, **arguments)
    elif tool_name == "get_inventory_summary":
        return await get_inventory_summary(db)
    elif tool_name == "get_equipment":
        return await get_equipment(db, **arguments)
    # Fermentation monitoring tools - pass user_id for multi-tenant isolation
    elif tool_name == "list_fermentations":
        return await list_fermentations(db, user_id=user_id, **arguments)
    elif tool_name == "get_fermentation_status":
        return await get_fermentation_status(db, user_id=user_id, **arguments)
    elif tool_name == "get_fermentation_history":
        return await get_fermentation_history(db, user_id=user_id, **arguments)
    elif tool_name == "get_ambient_conditions":
        return await get_ambient_conditions(db)
    elif tool_name == "compare_batches":
        return await compare_batches(db, user_id=user_id, **arguments)
    elif tool_name == "get_yeast_fermentation_advice":
        return await get_yeast_fermentation_advice(db, user_id=user_id, **arguments)
    # Recipe tools - pass user_id for multi-tenant isolation
    elif tool_name == "save_recipe":
        return await save_recipe(db, user_id=user_id, **arguments)
    elif tool_name == "review_recipe_style":
        return await review_recipe_style(db, user_id=user_id, **arguments)
    # Ingredient reference library tools
    elif tool_name == "search_hop_varieties":
        return await search_hop_varieties(db, **arguments)
    elif tool_name == "search_fermentables":
        return await search_fermentables(db, **arguments)
    # System / utility tools
    elif tool_name == "get_current_datetime":
        return get_current_datetime()
    elif tool_name == "fetch_url":
        return await fetch_url(**arguments)
    elif tool_name == "rename_chat":
        return await rename_chat(db, thread_id, **arguments)
    elif tool_name == "search_threads":
        return await search_threads(db, current_thread_id=thread_id, user_id=user_id, **arguments)
    elif tool_name == "list_recent_threads":
        return await list_recent_threads(db, current_thread_id=thread_id, user_id=user_id, **arguments)
    elif tool_name == "get_thread_context":
        return await get_thread_context(db, user_id=user_id, **arguments)
    else:
        return {"error": f"Unknown tool: {tool_name}"}
