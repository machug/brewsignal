"""Recipe management tools for the AI brewing assistant."""

import logging
import math
from pathlib import Path
from typing import Any, Optional

import prompty
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.config import get_settings
from backend.models import Recipe, Style
from backend.services.llm.service import LLMService

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

logger = logging.getLogger(__name__)


async def get_recipe(
    db: AsyncSession,
    recipe_id: int,
    user_id: Optional[str] = None,
) -> dict[str, Any]:
    """Get a recipe by ID with full ingredient details."""
    stmt = select(Recipe).options(
        selectinload(Recipe.style),
        selectinload(Recipe.fermentables),
        selectinload(Recipe.hops),
        selectinload(Recipe.cultures),
    ).where(Recipe.id == recipe_id)

    if user_id:
        settings = get_settings()
        if not settings.is_local:
            stmt = stmt.where(Recipe.user_id == user_id)

    result = await db.execute(stmt)
    recipe = result.scalar_one_or_none()

    if not recipe:
        return {"error": f"Recipe with ID {recipe_id} not found"}

    # Build ingredient lists
    fermentables = [
        {
            "name": f.name,
            "amount_kg": f.amount_kg,
            "color_srm": f.color_srm,
            "type": f.type,
        }
        for f in recipe.fermentables
    ]
    hops = [
        {
            "name": h.name,
            "amount_g": h.amount_grams,
            "time_minutes": h.time_min,
            "use": h.use,
            "alpha_acid": h.alpha_acid_percent,
        }
        for h in recipe.hops
    ]
    cultures = [
        {
            "name": c.name,
            "producer": c.producer,
            "product_id": c.product_id,
            "attenuation": c.attenuation,
        }
        for c in recipe.cultures
    ]

    return {
        "id": recipe.id,
        "name": recipe.name,
        "style": recipe.style.name if recipe.style else None,
        "type": recipe.type,
        "batch_size_liters": recipe.batch_size_liters,
        "boil_time_minutes": recipe.boil_time_minutes,
        "efficiency_percent": recipe.efficiency_percent,
        "og": recipe.og,
        "fg": recipe.fg,
        "abv": recipe.abv,
        "ibu": recipe.ibu,
        "color_srm": recipe.color_srm,
        "notes": recipe.notes,
        "fermentables": fermentables,
        "hops": hops,
        "cultures": cultures,
    }


async def list_recipes(
    db: AsyncSession,
    search: Optional[str] = None,
    limit: int = 20,
    user_id: Optional[str] = None,
) -> dict[str, Any]:
    """List recipes from the user's library, optionally filtered by search term."""
    stmt = select(Recipe).options(
        selectinload(Recipe.style),
    )

    settings = get_settings()
    if not settings.is_local and user_id:
        stmt = stmt.where(Recipe.user_id == user_id)

    if search:
        term = f"%{search}%"
        stmt = stmt.where(
            or_(
                Recipe.name.ilike(term),
                Recipe.notes.ilike(term),
            )
        )

    stmt = stmt.order_by(Recipe.created_at.desc()).limit(limit)

    result = await db.execute(stmt)
    recipes = result.scalars().all()

    return {
        "count": len(recipes),
        "recipes": [
            {
                "id": r.id,
                "name": r.name,
                "style": r.style.name if r.style else None,
                "type": r.type,
                "og": r.og,
                "fg": r.fg,
                "abv": r.abv,
                "ibu": r.ibu,
                "color_srm": r.color_srm,
                "batch_size_liters": r.batch_size_liters,
            }
            for r in recipes
        ],
    }


def _user_owns_recipe_condition(user_id: Optional[str]):
    """Create a SQLAlchemy condition for recipe ownership.

    In LOCAL mode: includes user's recipes + "local" user + unclaimed (NULL)
    In CLOUD mode: strict user_id filtering
    """
    settings = get_settings()
    if settings.is_local:
        # LOCAL mode: single-user Pi, no ownership filtering needed
        return True
    return Recipe.user_id == user_id


def normalize_recipe_to_beerjson(recipe: dict[str, Any]) -> dict[str, Any]:
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

    # Handle flat yeast fields (from prompty format: yeast_name, yeast_lab, yeast_attenuation, etc.)
    if not cultures:
        yeast_name = recipe.get("yeast_name")
        if yeast_name:
            flat_yeast = {"name": yeast_name}
            if recipe.get("yeast_lab"):
                flat_yeast["producer"] = recipe.get("yeast_lab")
            if recipe.get("yeast_product_id"):
                flat_yeast["product_id"] = recipe.get("yeast_product_id")
            if recipe.get("yeast_attenuation"):
                flat_yeast["attenuation"] = recipe.get("yeast_attenuation")
            if recipe.get("yeast_temp_min") or recipe.get("yeast_temp_max"):
                flat_yeast["temperature_range"] = {}
                if recipe.get("yeast_temp_min"):
                    flat_yeast["temperature_range"]["minimum"] = {"value": recipe.get("yeast_temp_min"), "unit": "C"}
                if recipe.get("yeast_temp_max"):
                    flat_yeast["temperature_range"]["maximum"] = {"value": recipe.get("yeast_temp_max"), "unit": "C"}
            cultures = [flat_yeast]
            logger.info(f"Converted flat yeast fields to culture: {flat_yeast}")

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


def calculate_recipe_stats(normalized: dict[str, Any]) -> dict[str, Any]:
    """Calculate OG, FG, ABV, IBU, and color from recipe ingredients.

    This ensures consistent, accurate calculations rather than relying on LLM math.
    """
    # Extract batch size in liters
    batch_size = normalized.get("batch_size", {})
    if isinstance(batch_size, dict):
        batch_liters = batch_size.get("value", 20)
    else:
        batch_liters = float(batch_size) if batch_size else 20

    # Default efficiency (72% brewhouse)
    efficiency = normalized.get("efficiency", {})
    if isinstance(efficiency, dict):
        brewhouse = efficiency.get("brewhouse", {})
        if isinstance(brewhouse, dict):
            eff_val = brewhouse.get("value", 0.72)
        else:
            eff_val = float(brewhouse) if brewhouse else 0.72
    else:
        eff_val = 0.72
    # Ensure efficiency is a decimal
    if eff_val > 1:
        eff_val = eff_val / 100

    ingredients = normalized.get("ingredients", {})

    # -------------------------------------------------------------------------
    # Calculate OG from fermentables
    # -------------------------------------------------------------------------
    fermentables = ingredients.get("fermentable_additions", [])
    total_gravity_points = 0
    total_mcu = 0  # Malt Color Units for SRM calculation

    # Default extract potentials (points per kg per liter, roughly)
    # These are simplified - real values depend on specific grain
    default_potentials = {
        # Base malts - high potential (~36-38 PPG = ~300-315 points/kg/L at 100% eff)
        "pale": 37, "pilsner": 37, "maris otter": 38, "golden promise": 37,
        "2-row": 37, "pale ale": 37, "vienna": 35, "munich": 34,
        # Wheat/adjuncts
        "wheat": 36, "rye": 29, "oat": 33, "flaked": 32, "rice": 32, "corn": 36,
        # Crystal/caramel (lower potential, mostly unfermentable)
        "crystal": 33, "caramel": 33, "cara": 33,
        # Roasted (very low potential)
        "chocolate": 28, "black": 25, "roast": 25,
        # Sugars (high potential, 100% fermentable)
        "sugar": 46, "dextrose": 46, "honey": 35, "candi": 38,
    }

    for ferm in fermentables:
        name = ferm.get("name", "").lower()
        amount = ferm.get("amount", {})
        if isinstance(amount, dict):
            amount_kg = amount.get("value", 0)
        else:
            amount_kg = float(amount) if amount else 0

        # Determine potential based on grain type
        potential = 36  # Default for unknown grains
        for key, val in default_potentials.items():
            if key in name:
                potential = val
                break

        # Gravity points contribution using PPG (points per pound per gallon)
        # Convert to metric: gravity points = (lbs * PPG * efficiency) / gallons
        # Where: 1 kg = 2.205 lbs, 1 gallon = 3.785 liters
        grain_lbs = amount_kg * 2.205
        batch_gal = batch_liters / 3.785
        points = (grain_lbs * potential * eff_val) / batch_gal
        total_gravity_points += points

        # Color contribution (MCU)
        color = ferm.get("color", {})
        if isinstance(color, dict):
            color_lov = color.get("value", 3)  # Default to pale malt color
        else:
            color_lov = float(color) if color else 3

        # MCU = (grain_lbs * color_lovibond) / batch_gallons
        grain_lbs = amount_kg * 2.205
        batch_gal = batch_liters * 0.264172
        if batch_gal > 0:
            total_mcu += (grain_lbs * color_lov) / batch_gal

    # Calculate OG
    calculated_og = 1.0 + (total_gravity_points / 1000)

    # Calculate SRM using Morey equation: SRM = 1.4922 * MCU^0.6859
    if total_mcu > 0:
        calculated_srm = 1.4922 * (total_mcu ** 0.6859)
    else:
        calculated_srm = 3  # Default pale color

    # -------------------------------------------------------------------------
    # Calculate IBU from hops (Tinseth formula)
    # -------------------------------------------------------------------------
    hops = ingredients.get("hop_additions", [])
    total_ibu = 0

    for hop in hops:
        if hop.get("is_extract"):
            # Abstrax-style extracts have no alpha acids and contribute zero
            # IBU regardless of timing/amount. Skip before alpha math to
            # avoid None/0 hazards (tilt_ui-0l5; mirrors brewing._calculate_ibu).
            continue
        amount = hop.get("amount", {})
        if isinstance(amount, dict):
            amount_g = amount.get("value", 0)
        else:
            amount_g = float(amount) if amount else 0

        alpha = hop.get("alpha_acid", {})
        if isinstance(alpha, dict):
            alpha_pct = alpha.get("value", 0.05)
            if alpha_pct > 1:
                alpha_pct = alpha_pct / 100
        else:
            alpha_pct = float(alpha) if alpha else 0.05
            if alpha_pct > 1:
                alpha_pct = alpha_pct / 100

        # Get boil time from timing
        timing = hop.get("timing", {})
        use = timing.get("use", "boil")
        duration = timing.get("duration", {})
        if isinstance(duration, dict):
            boil_min = duration.get("value", 0)
        else:
            boil_min = float(duration) if duration else 0

        # Only calculate IBU for boil additions
        if use in ["boil", "add_to_boil", "first_wort", "mash", "add_to_mash"]:
            # Tinseth utilization formula
            # Bigness factor = 1.65 * 0.000125^(OG - 1)
            bigness = 1.65 * (0.000125 ** (calculated_og - 1))
            # Boil time factor = (1 - e^(-0.04 * time)) / 4.15
            if boil_min > 0:
                boil_factor = (1 - math.exp(-0.04 * boil_min)) / 4.15
            else:
                boil_factor = 0
            utilization = bigness * boil_factor

            # IBU = (grams * alpha * utilization * 1000) / liters
            ibu_contribution = (amount_g * alpha_pct * utilization * 1000) / batch_liters
            total_ibu += ibu_contribution
        elif use in ["whirlpool", "add_to_whirlpool"]:
            # Hop-stand utilization: linear ramp from 5% (true flameout) to a
            # 20% cap reached around 30 minutes. Mirrors services/brewing.py
            # (tilt_ui-23u). Keep this in sync when updating the model.
            stand_min = max(0.0, boil_min)
            utilization = min(0.05 + 0.005 * stand_min, 0.20)
            ibu_contribution = (amount_g * alpha_pct * utilization * 1000) / batch_liters
            total_ibu += ibu_contribution
        # Dry hops don't contribute significant IBUs

    # -------------------------------------------------------------------------
    # Calculate FG and ABV from yeast attenuation
    # -------------------------------------------------------------------------
    cultures = ingredients.get("culture_additions", [])
    attenuation = 0.75  # Default 75% if no yeast specified

    for culture in cultures:
        atten = culture.get("attenuation", {})
        if isinstance(atten, dict):
            # Could be {"minimum": {"value": 0.73}} or {"value": 0.75}
            if "minimum" in atten:
                min_atten = atten["minimum"]
                if isinstance(min_atten, dict):
                    attenuation = min_atten.get("value", 0.75)
                else:
                    attenuation = float(min_atten)
            elif "value" in atten:
                attenuation = atten.get("value", 0.75)
            else:
                attenuation = 0.75
        else:
            attenuation = float(atten) if atten else 0.75

        # Ensure attenuation is decimal
        if attenuation > 1:
            attenuation = attenuation / 100
        break  # Use first yeast's attenuation

    # FG = OG - (OG - 1) * attenuation
    calculated_fg = calculated_og - (calculated_og - 1) * attenuation

    # ABV = (OG - FG) * 131.25
    calculated_abv = (calculated_og - calculated_fg) * 131.25

    return {
        "og": round(calculated_og, 3),
        "fg": round(calculated_fg, 3),
        "abv": round(calculated_abv, 1),
        "ibu": round(total_ibu, 0),
        "color_srm": round(calculated_srm, 1),
    }


# BJCP name → styles.id lookup lives in services/style_resolver. Re-export
# here so existing callers (save_recipe, update_recipe) keep working.
from ...style_resolver import resolve_style_id as _resolve_style_id  # noqa: F401


_CONFIRMATION_GUIDANCE = (
    "Do not persist this recipe yet. Required workflow: "
    "(1) run review_recipe on the candidate (save it to a draft first "
    "if it has no id yet, or summarize it back to the user for review); "
    "(2) explicitly ask the user to confirm — e.g. 'Save this recipe?' or "
    "'Apply these changes to recipe N?'; "
    "(3) only after the user says yes, call this tool again with "
    "user_confirmed=true."
)


def _confirmation_required_response(action: str) -> dict[str, Any]:
    return {
        "requires_confirmation": True,
        "action": action,
        "guidance": _CONFIRMATION_GUIDANCE,
    }


async def save_recipe(
    db: AsyncSession,
    recipe: dict[str, Any],
    name_override: Optional[str] = None,
    user_confirmed: Optional[bool] = None,
    user_id: Optional[str] = None,
) -> dict[str, Any]:
    """Save a BeerJSON recipe to the database."""
    from backend.services.serializers.recipe_serializer import RecipeSerializer

    if not recipe:
        return {"error": "Recipe data is required"}

    if user_confirmed is not True:
        return _confirmation_required_response("save")

    # Check if recipe has required name field
    if not recipe.get("name") and not name_override:
        return {"error": "Recipe must have a name (either in recipe.name or via name_override)"}

    # Apply name override if provided
    if name_override:
        recipe["name"] = name_override

    try:
        # Normalize the recipe to BeerJSON format
        normalized = normalize_recipe_to_beerjson(recipe)
        logger.info(f"Normalized recipe: {normalized.get('name')}")

        # Calculate OG, FG, ABV, IBU, and color from ingredients
        # This ensures accurate values regardless of what the LLM provided
        calculated = calculate_recipe_stats(normalized)
        logger.info(f"Calculated stats: OG={calculated['og']}, FG={calculated['fg']}, "
                    f"ABV={calculated['abv']}%, IBU={calculated['ibu']}, SRM={calculated['color_srm']}")

        # Override normalized values with calculated values
        normalized["original_gravity"] = {"value": calculated["og"], "unit": "sg"}
        normalized["final_gravity"] = {"value": calculated["fg"], "unit": "sg"}
        normalized["alcohol_by_volume"] = {"value": calculated["abv"] / 100, "unit": "%"}
        normalized["ibu_estimate"] = {"value": calculated["ibu"], "unit": "IBUs"}
        normalized["color_estimate"] = {"value": calculated["color_srm"], "unit": "SRM"}

        # Use the RecipeSerializer to convert BeerJSON to SQLAlchemy model
        serializer = RecipeSerializer()
        db_recipe = await serializer.serialize(normalized, db)

        # Resolve free-text "style" (e.g. "American IPA") to a BJCP Style row.
        style_id = await _resolve_style_id(db, recipe.get("style"))
        if style_id:
            db_recipe.style_id = style_id

        # Set user_id for multi-tenant isolation
        if user_id:
            db_recipe.user_id = user_id

        # Add to database
        db.add(db_recipe)
        await db.commit()

        # Re-fetch with eager loading to avoid lazy-load errors
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


async def update_recipe(
    db: AsyncSession,
    recipe_id: int,
    recipe: dict[str, Any],
    user_confirmed: Optional[bool] = None,
    user_id: Optional[str] = None,
) -> dict[str, Any]:
    """Update an existing recipe (full replacement of fields + children).

    Loads the recipe by id, validates ownership, normalizes the supplied
    payload, recomputes OG/FG/ABV/IBU/SRM, replaces all child rows
    (fermentables/hops/cultures/mash/fermentation steps) and commits.

    Args:
        recipe_id: ID of the existing recipe to update.
        recipe: Same shape as save_recipe's recipe arg. Missing top-level
            children are treated as "remove all" (full-replacement semantics);
            callers wanting partial edits should fetch via get_recipe, merge,
            then pass the merged shape.
    """
    from backend.services.serializers.recipe_serializer import RecipeSerializer

    if not recipe:
        return {"error": "Recipe data is required"}

    if user_confirmed is not True:
        return _confirmation_required_response("update")

    stmt = select(Recipe).options(
        selectinload(Recipe.fermentables),
        selectinload(Recipe.hops),
        selectinload(Recipe.cultures),
        selectinload(Recipe.miscs),
        selectinload(Recipe.mash_steps),
        selectinload(Recipe.fermentation_steps),
        selectinload(Recipe.water_profiles),
        selectinload(Recipe.water_adjustments),
    ).where(Recipe.id == recipe_id)

    settings = get_settings()
    if not settings.is_local and user_id:
        stmt = stmt.where(Recipe.user_id == user_id)

    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()

    if not existing:
        return {"error": f"Recipe with ID {recipe_id} not found"}

    try:
        # Preserve existing name if patch omits it.
        if not recipe.get("name"):
            recipe["name"] = existing.name

        normalized = normalize_recipe_to_beerjson(recipe)
        calculated = calculate_recipe_stats(normalized)

        normalized["original_gravity"] = {"value": calculated["og"], "unit": "sg"}
        normalized["final_gravity"] = {"value": calculated["fg"], "unit": "sg"}
        normalized["alcohol_by_volume"] = {"value": calculated["abv"] / 100, "unit": "%"}
        normalized["ibu_estimate"] = {"value": calculated["ibu"], "unit": "IBUs"}
        normalized["color_estimate"] = {"value": calculated["color_srm"], "unit": "SRM"}

        # Clear all children first so delete-orphan cascade removes the old
        # rows in a flush before new rows go in.
        existing.fermentables.clear()
        existing.hops.clear()
        existing.cultures.clear()
        existing.miscs.clear()
        existing.mash_steps.clear()
        existing.fermentation_steps.clear()
        existing.water_profiles.clear()
        existing.water_adjustments.clear()
        await db.flush()

        # Apply scalar fields from normalized dict directly onto existing.
        serializer = RecipeSerializer()
        existing.name = normalized["name"]
        if "type" in normalized:
            existing.type = normalized["type"]
        if "author" in normalized:
            existing.author = normalized["author"]
        if "notes" in normalized:
            existing.notes = normalized["notes"]
        # Resolve free-text "style" to BJCP Style row (None on miss leaves
        # style_id unchanged is wrong — explicit no-style intent should clear it.
        # When the payload omits "style", leave existing.style_id alone.)
        if "style" in recipe:
            existing.style_id = await _resolve_style_id(db, recipe.get("style"))
        serializer._extract_recipe_vitals(existing, normalized)
        serializer._extract_boil_info(existing, normalized)
        serializer._extract_efficiency(existing, normalized)
        serializer._extract_carbonation(existing, normalized)

        if "ingredients" in normalized:
            serializer._serialize_ingredients(existing, normalized["ingredients"])
        if "mash" in normalized:
            serializer._serialize_mash(existing, normalized["mash"])
        if "fermentation" in normalized:
            serializer._serialize_fermentation(existing, normalized["fermentation"])
        if "waters" in normalized:
            serializer._serialize_water(existing, normalized["waters"])

        await db.commit()

        stmt = select(Recipe).options(
            selectinload(Recipe.fermentables),
            selectinload(Recipe.hops),
            selectinload(Recipe.cultures),
        ).where(Recipe.id == recipe_id)
        saved = (await db.execute(stmt)).scalar_one()

        return {
            "success": True,
            "recipe_id": saved.id,
            "name": saved.name,
            "type": saved.type,
            "batch_size_liters": saved.batch_size_liters,
            "og": saved.og,
            "fg": saved.fg,
            "abv": saved.abv,
            "ibu": saved.ibu,
            "color_srm": saved.color_srm,
            "fermentables_count": len(saved.fermentables),
            "hops_count": len(saved.hops),
            "cultures_count": len(saved.cultures),
            "message": f"Recipe '{saved.name}' (ID {saved.id}) updated successfully",
        }

    except KeyError as e:
        await db.rollback()
        return {
            "error": f"Missing required field in recipe: {e}",
            "hint": "Ensure recipe has at minimum: name, and optionally ingredients.fermentable_additions, ingredients.hop_additions, ingredients.culture_additions"
        }
    except Exception as e:
        await db.rollback()
        logger.exception(f"Failed to update recipe {recipe_id}: {e}")
        return {"error": f"Failed to update recipe: {str(e)}"}


def _format_fermentables_for_review(fermentables) -> str:
    """Build the grain-bill summary string for the review prompt."""
    if not fermentables:
        return "No fermentables specified"

    total_kg = sum(f.amount_kg for f in fermentables if f.amount_kg)
    lines = []
    for f in sorted(fermentables, key=lambda x: x.amount_kg or 0, reverse=True):
        amount = f.amount_kg or 0
        pct = (amount / total_kg * 100) if total_kg > 0 else 0
        color_str = f" ({f.color_srm:.0f} SRM)" if f.color_srm else ""
        lines.append(f"- {f.name}: {amount:.2f} kg ({pct:.0f}%){color_str}")
    return "\n".join(lines)


def _format_hops_for_review(hops) -> str:
    """Build the hop-schedule summary string for the review prompt."""
    if not hops:
        return "No hops specified"

    def _time(h):
        return h.time_min if h.time_min is not None else 0

    lines = []
    for h in sorted(hops, key=_time, reverse=True):
        use = (h.use or "boil").lower()
        aa = h.alpha_acid_percent
        aa_str = f" ({aa:.1f}% AA)" if aa else ""
        t = _time(h)
        if "dry" in use:
            timing = "dry hop"
        elif "whirlpool" in use:
            timing = "whirlpool"
        elif t == 0:
            timing = "flameout"
        else:
            timing = f"{t:.0f} min"
        lines.append(f"- {h.name}: {h.amount_grams:.0f}g @ {timing}{aa_str}")
    return "\n".join(lines)


def _format_yeast_for_review(cultures) -> str:
    """Build the yeast summary string for the review prompt."""
    if not cultures:
        return "No yeast specified"
    c = cultures[0]
    parts = [c.name]
    if c.producer:
        parts.append(f"by {c.producer}")
    atten = getattr(c, "attenuation_percent", None) or getattr(
        c, "attenuation_min_percent", None
    )
    if atten:
        parts.append(f"({atten:.0f}% attenuation)")
    return " ".join(parts)


async def _load_style_guidelines(
    db: AsyncSession, style: Optional[Style]
) -> tuple[bool, str, str]:
    """Build BJCP guidelines string from a Style ORM object.

    Returns (found, style_name, guidelines_text).
    """
    if not style:
        return False, "", ""

    lines = [f"**{style.name}** (BJCP {style.category_number}{style.style_letter or ''})"]
    if style.description:
        lines.append(f"\n**Description:** {style.description}")

    stats = []
    if style.og_min and style.og_max:
        stats.append(f"OG: {style.og_min:.3f}-{style.og_max:.3f}")
    if style.fg_min and style.fg_max:
        stats.append(f"FG: {style.fg_min:.3f}-{style.fg_max:.3f}")
    if style.abv_min and style.abv_max:
        stats.append(f"ABV: {style.abv_min:.1f}-{style.abv_max:.1f}%")
    if style.ibu_min and style.ibu_max:
        stats.append(f"IBU: {int(style.ibu_min)}-{int(style.ibu_max)}")
    if style.srm_min and style.srm_max:
        stats.append(f"SRM: {style.srm_min:.0f}-{style.srm_max:.0f}")
    if stats:
        lines.append(f"\n**Vital Statistics:** {', '.join(stats)}")
    if style.comments:
        lines.append(f"\n**Comments:** {style.comments}")

    return True, style.name, "\n".join(lines)


def _compute_style_compliance(recipe: Recipe, target_style: Style) -> dict[str, Any]:
    """Compute OG/FG/ABV/IBU/SRM compliance for a recipe vs a BJCP style.

    Returns a dict with keys: compliance, issues, suggestions, style_fit_score,
    style_fit_score_scale, overall_status, current_stats.
    """
    from backend.services.brewing import calculate_recipe_stats as brewing_calculate_stats

    current_stats = brewing_calculate_stats(recipe)
    compliance: dict[str, Any] = {}
    issues: list[str] = []
    suggestions: list[str] = []

    def check_range(stat_name, value, min_val, max_val, unit=""):
        r = {
            "value": value, "min": min_val, "max": max_val,
            "unit": unit, "status": "unknown",
        }
        if min_val is None or max_val is None:
            r["status"] = "no_guideline"
            return r
        if value < min_val:
            r["status"] = "below"
            r["deviation"] = round(min_val - value, 3)
            issues.append(f"{stat_name} ({value}{unit}) is below style minimum ({min_val}{unit})")
        elif value > max_val:
            r["status"] = "above"
            r["deviation"] = round(value - max_val, 3)
            issues.append(f"{stat_name} ({value}{unit}) is above style maximum ({max_val}{unit})")
        else:
            r["status"] = "in_range"
        return r

    compliance["og"] = check_range("OG", current_stats["og"], target_style.og_min, target_style.og_max)
    compliance["fg"] = check_range("FG", current_stats["fg"], target_style.fg_min, target_style.fg_max)
    compliance["abv"] = check_range("ABV", current_stats["abv"], target_style.abv_min, target_style.abv_max, "%")
    compliance["ibu"] = check_range("IBU", current_stats["ibu"], target_style.ibu_min, target_style.ibu_max)
    compliance["srm"] = check_range("SRM", current_stats["color_srm"], target_style.srm_min, target_style.srm_max)

    stats_checked = [c for c in compliance.values() if c["status"] != "no_guideline"]
    in_range_count = sum(1 for c in stats_checked if c["status"] == "in_range")
    score = round((in_range_count / len(stats_checked)) * 10, 1) if stats_checked else 0

    if compliance["og"]["status"] == "below":
        suggestions.append("Increase grain bill to raise OG, or reduce batch size")
    elif compliance["og"]["status"] == "above":
        suggestions.append("Reduce grain bill to lower OG, or increase batch size")
    if compliance["ibu"]["status"] == "below":
        suggestions.append("Add more bittering hops or increase boil time to raise IBU")
    elif compliance["ibu"]["status"] == "above":
        suggestions.append("Reduce hop amounts or boil times to lower IBU")
    if compliance["srm"]["status"] == "below":
        suggestions.append("Add specialty malts (crystal, caramel) to increase color")
    elif compliance["srm"]["status"] == "above":
        suggestions.append("Reduce colored malts or substitute lighter base malts")
    if (
        compliance["abv"]["status"] == "below"
        and compliance["og"]["status"] == "in_range"
    ):
        suggestions.append("Use a higher-attenuating yeast to increase ABV")
    elif (
        compliance["abv"]["status"] == "above"
        and compliance["og"]["status"] == "in_range"
    ):
        suggestions.append("Use a lower-attenuating yeast to reduce ABV")

    return {
        "compliance": compliance,
        "issues": issues,
        "suggestions": suggestions,
        "style_fit_score": score,
        "style_fit_score_scale": "0-10 (10 = every stat in range)",
        "overall_status": "in_style" if not issues else "needs_adjustment",
        "current_stats": current_stats,
    }


async def review_recipe(
    db: AsyncSession,
    recipe_id: int,
    user_id: Optional[str] = None,
) -> dict[str, Any]:
    """Run the BJCP recipe review — returns BOTH the narrative review text
    and the numeric style compliance block in one call.

    This is the primary recipe-review tool. The LLM should call this whenever
    the user asks for a "review", "critique", "check", or "style review" on a
    recipe. The advanced review_recipe_style tool is rarely needed since the
    compliance block here covers the same numeric data.
    """
    stmt = select(Recipe).options(
        selectinload(Recipe.style),
        selectinload(Recipe.fermentables),
        selectinload(Recipe.hops),
        selectinload(Recipe.cultures),
    ).where(Recipe.id == recipe_id)

    settings = get_settings()
    if not settings.is_local and user_id:
        stmt = stmt.where(Recipe.user_id == user_id)

    result = await db.execute(stmt)
    recipe = result.scalar_one_or_none()
    if not recipe:
        return {"error": f"Recipe with ID {recipe_id} not found"}

    # Build LLMService from the same db-backed config the chat path uses.
    # The global singleton from services/llm/service.py is never initialised
    # at startup (no init_llm_service call in main.lifespan), so reading it
    # here would always report 'not configured'.
    from backend.routers.assistant import get_llm_config

    service = LLMService(await get_llm_config(db))
    if not service.config.is_configured():
        return {"error": "AI assistant is not configured. Enable it in Settings."}

    style_found, style_name, style_guidelines = await _load_style_guidelines(
        db, recipe.style
    )

    # Compute compliance first (when there's a style) so the narrative prompt
    # and the bundled compliance block use the SAME recalculated stats.
    # Otherwise stored recipe.og/fg/etc — which may be null or stale for
    # imported recipes — would feed the narrative while the compliance block
    # used freshly-calculated values, producing a self-contradicting response.
    compliance_block: Optional[dict[str, Any]] = None
    if recipe.style is not None:
        compliance_block = _compute_style_compliance(recipe, recipe.style)
        stats = compliance_block["current_stats"]
    else:
        from backend.services.brewing import calculate_recipe_stats as brewing_calculate_stats
        stats = brewing_calculate_stats(recipe) if (recipe.fermentables or recipe.hops) else {
            "og": recipe.og or 0,
            "fg": recipe.fg or 0,
            "abv": recipe.abv or 0,
            "ibu": recipe.ibu or 0,
            "color_srm": recipe.color_srm or 0,
        }

    try:
        prompt_path = PROMPTS_DIR / "recipe-review.prompty"
        p = prompty.load(str(prompt_path))
        rendered = prompty.prepare(p, inputs={
            "recipe_name": recipe.name or "Untitled Recipe",
            "style_name": style_name if style_found else (
                recipe.style.name if recipe.style else "Unknown"
            ),
            "og": stats["og"],
            "fg": stats["fg"],
            "abv": stats["abv"],
            "ibu": stats["ibu"],
            "color_srm": stats["color_srm"],
            "fermentables_summary": _format_fermentables_for_review(recipe.fermentables),
            "hops_summary": _format_hops_for_review(recipe.hops),
            "yeast_info": _format_yeast_for_review(recipe.cultures),
            "style_guidelines": style_guidelines if style_found else "",
        })

        review_text = await service.chat(messages=rendered, temperature=0.5)

        response: dict[str, Any] = {
            "review": review_text,
            "style_found": style_found,
            "style_name": style_name if style_found else None,
            "model": service.config.effective_model,
        }

        if compliance_block is not None:
            response.update(compliance_block)
            response["target_style"] = {
                "id": recipe.style.id,
                "name": recipe.style.name,
                "category": recipe.style.category,
                "guide": recipe.style.guide,
            }

        return response
    except Exception as e:
        logger.exception(f"Recipe review failed for recipe {recipe_id}: {e}")
        return {"error": f"Recipe review failed: {str(e)}"}


# Backwards-compatible alias for older callers / tests. New code should use
# review_recipe.
review_recipe_narrative = review_recipe


async def review_recipe_style(
    db: AsyncSession,
    recipe_id: int,
    style_id: Optional[str] = None,
    auto_fix: bool = False,
    user_id: Optional[str] = None,
) -> dict[str, Any]:
    """Review a recipe against BJCP style guidelines.

    Compares the recipe's stats (OG, FG, ABV, IBU, SRM) against the target style's
    ranges and returns a detailed compliance analysis with suggestions.
    """
    from backend.services.brewing import calculate_recipe_stats as brewing_calculate_stats

    # Fetch recipe with all ingredients and ownership check
    stmt = select(Recipe).options(
        selectinload(Recipe.style),
        selectinload(Recipe.fermentables),
        selectinload(Recipe.hops),
        selectinload(Recipe.cultures),
    ).where(Recipe.id == recipe_id)

    if user_id:
        stmt = stmt.where(_user_owns_recipe_condition(user_id))

    result = await db.execute(stmt)
    recipe = result.scalar_one_or_none()

    if not recipe:
        return {"error": f"Recipe with ID {recipe_id} not found"}

    # Determine target style
    target_style = None
    if style_id:
        style_result = await db.execute(select(Style).where(Style.id == style_id))
        target_style = style_result.scalar_one_or_none()
        if not target_style:
            return {"error": f"Style '{style_id}' not found"}
    elif recipe.style_id:
        style_result = await db.execute(select(Style).where(Style.id == recipe.style_id))
        target_style = style_result.scalar_one_or_none()

    if not target_style:
        return {
            "error": "No target style specified. Either set a style on the recipe or provide a style_id parameter.",
            "hint": "Use search_styles to find available BJCP styles."
        }

    compliance_block = _compute_style_compliance(recipe, target_style)
    current_stats = compliance_block["current_stats"]
    compliance = compliance_block["compliance"]
    issues = compliance_block["issues"]

    response = {
        "recipe_id": recipe.id,
        "recipe_name": recipe.name,
        "target_style": {
            "id": target_style.id,
            "name": target_style.name,
            "category": target_style.category,
            "guide": target_style.guide,
        },
        **compliance_block,
    }

    # Auto-fix if requested (limited scope - just update batch size for OG issues)
    if auto_fix and issues:
        fixes_applied = []

        # Fix OG by adjusting batch size (simplest fix)
        if compliance["og"]["status"] == "below" and target_style.og_min:
            # Calculate required batch size reduction
            target_og = (target_style.og_min + target_style.og_max) / 2
            current_og = current_stats["og"]
            if current_og > 1.0:
                # ratio of gravity points
                ratio = (target_og - 1) / (current_og - 1)
                new_batch_size = round(recipe.batch_size_liters / ratio, 1)
                if 10 <= new_batch_size <= 50:  # Reasonable range
                    recipe.batch_size_liters = new_batch_size
                    fixes_applied.append(f"Reduced batch size to {new_batch_size}L to target OG {target_og:.3f}")

        elif compliance["og"]["status"] == "above" and target_style.og_max:
            target_og = (target_style.og_min + target_style.og_max) / 2
            current_og = current_stats["og"]
            if current_og > 1.0:
                ratio = (target_og - 1) / (current_og - 1)
                new_batch_size = round(recipe.batch_size_liters / ratio, 1)
                if 10 <= new_batch_size <= 50:
                    recipe.batch_size_liters = new_batch_size
                    fixes_applied.append(f"Increased batch size to {new_batch_size}L to target OG {target_og:.3f}")

        if fixes_applied:
            # Recalculate stats after fixes
            new_stats = brewing_calculate_stats(recipe)
            recipe.og = new_stats["og"]
            recipe.fg = new_stats["fg"]
            recipe.abv = new_stats["abv"]
            recipe.ibu = new_stats["ibu"]
            recipe.color_srm = new_stats["color_srm"]
            await db.commit()

            response["auto_fix_applied"] = True
            response["fixes_applied"] = fixes_applied
            response["updated_stats"] = new_stats
        else:
            response["auto_fix_applied"] = False
            response["auto_fix_note"] = "Auto-fix could not resolve issues automatically. Manual adjustment recommended."

    return response
