"""Recipe management tools for the AI brewing assistant."""

import logging
import math
from typing import Any, Optional

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.config import get_settings
from backend.models import Recipe, Style

logger = logging.getLogger(__name__)


def _user_owns_recipe_condition(user_id: Optional[str]):
    """Create a SQLAlchemy condition for recipe ownership.

    In LOCAL mode: includes user's recipes + "local" user + unclaimed (NULL)
    In CLOUD mode: strict user_id filtering
    """
    settings = get_settings()
    if settings.is_local:
        return or_(
            Recipe.user_id == user_id,
            Recipe.user_id == "local",
            Recipe.user_id.is_(None),
        )
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
        if use in ["boil", "first_wort"]:
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
        elif use == "whirlpool":
            # Whirlpool hops contribute ~10-20% of boil utilization
            utilization = 0.05  # Rough estimate
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


async def save_recipe(
    db: AsyncSession,
    recipe: dict[str, Any],
    name_override: Optional[str] = None,
    user_id: Optional[str] = None,
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

    # Recalculate current stats from ingredients
    current_stats = brewing_calculate_stats(recipe)

    # Compare against style guidelines
    compliance = {}
    issues = []
    suggestions = []

    def check_range(stat_name: str, value: float, min_val: Optional[float], max_val: Optional[float], unit: str = ""):
        """Check if a value is within range and return compliance info."""
        result = {
            "value": value,
            "min": min_val,
            "max": max_val,
            "unit": unit,
            "status": "unknown"
        }

        if min_val is None or max_val is None:
            result["status"] = "no_guideline"
            return result

        if value < min_val:
            result["status"] = "below"
            result["deviation"] = round(min_val - value, 3)
            issues.append(f"{stat_name} ({value}{unit}) is below style minimum ({min_val}{unit})")
        elif value > max_val:
            result["status"] = "above"
            result["deviation"] = round(value - max_val, 3)
            issues.append(f"{stat_name} ({value}{unit}) is above style maximum ({max_val}{unit})")
        else:
            result["status"] = "in_range"

        return result

    # Check each stat
    compliance["og"] = check_range("OG", current_stats["og"], target_style.og_min, target_style.og_max)
    compliance["fg"] = check_range("FG", current_stats["fg"], target_style.fg_min, target_style.fg_max)
    compliance["abv"] = check_range("ABV", current_stats["abv"], target_style.abv_min, target_style.abv_max, "%")
    compliance["ibu"] = check_range("IBU", current_stats["ibu"], target_style.ibu_min, target_style.ibu_max)
    compliance["srm"] = check_range("SRM", current_stats["color_srm"], target_style.srm_min, target_style.srm_max)

    # Calculate compliance score
    stats_checked = [c for c in compliance.values() if c["status"] != "no_guideline"]
    in_range_count = sum(1 for c in stats_checked if c["status"] == "in_range")
    score = round((in_range_count / len(stats_checked)) * 10, 1) if stats_checked else 0

    # Generate suggestions based on issues
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

    if compliance["abv"]["status"] != "in_range" and compliance["og"]["status"] != "in_range":
        # ABV follows OG, so the OG suggestion applies
        pass
    elif compliance["abv"]["status"] == "below" and compliance["og"]["status"] == "in_range":
        suggestions.append("Use a higher-attenuating yeast to increase ABV")
    elif compliance["abv"]["status"] == "above" and compliance["og"]["status"] == "in_range":
        suggestions.append("Use a lower-attenuating yeast to reduce ABV")

    # Build response
    response = {
        "recipe_id": recipe.id,
        "recipe_name": recipe.name,
        "target_style": {
            "id": target_style.id,
            "name": target_style.name,
            "category": target_style.category,
            "guide": target_style.guide,
        },
        "style_fit_score": score,
        "compliance": compliance,
        "issues": issues,
        "suggestions": suggestions,
        "overall_status": "in_style" if not issues else "needs_adjustment",
        "current_stats": current_stats,
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
