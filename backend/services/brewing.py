"""Brewing calculations for recipe statistics.

Provides deterministic server-side calculation of OG, FG, ABV, IBU, and color
from recipe ingredients. These calculations replace LLM-based estimation.
"""
import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.models import Recipe, RecipeFermentable, RecipeHop, RecipeCulture


# Default extract potentials (points per pound per gallon, roughly)
# PPG values - multiply by kg conversion and divide by batch size for gravity points
DEFAULT_POTENTIALS = {
    # Base malts - high potential (~36-38 PPG)
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


def get_extract_potential(name: str, yield_percent: float | None = None) -> float:
    """Get extract potential for a grain by name or yield percentage.

    Args:
        name: Grain name to look up
        yield_percent: If provided (0-100), calculate from yield instead

    Returns:
        PPG (points per pound per gallon) value
    """
    # If yield_percent is provided, calculate from it
    # PPG = yield% * 46 (46 is max PPG for pure sugar)
    if yield_percent is not None and yield_percent > 0:
        if yield_percent > 1:
            yield_percent = yield_percent / 100
        return yield_percent * 46

    # Otherwise look up by name
    name_lower = name.lower()
    for key, val in DEFAULT_POTENTIALS.items():
        if key in name_lower:
            return val

    return 36  # Default for unknown grains


def calculate_og_from_fermentables(
    fermentables: list["RecipeFermentable"],
    batch_liters: float,
    efficiency: float
) -> tuple[float, float]:
    """Calculate OG and color (SRM) from fermentable ingredients.

    Args:
        fermentables: List of RecipeFermentable models
        batch_liters: Batch size in liters
        efficiency: Brewhouse efficiency as decimal (0.72 = 72%)

    Returns:
        Tuple of (og, color_srm)
    """
    if batch_liters <= 0:
        batch_liters = 20  # Default

    if efficiency > 1:
        efficiency = efficiency / 100

    total_gravity_points = 0
    total_mcu = 0  # Malt Color Units

    for ferm in fermentables:
        amount_kg = ferm.amount_kg or 0
        if amount_kg <= 0:
            continue

        # Get extract potential (PPG = points per pound per gallon)
        potential = get_extract_potential(ferm.name, ferm.yield_percent)

        # Convert to metric: gravity points = (lbs * PPG * efficiency) / gallons
        # Where: 1 kg = 2.205 lbs, 1 gallon = 3.785 liters
        grain_lbs = amount_kg * 2.205
        batch_gal = batch_liters / 3.785
        points = (grain_lbs * potential * efficiency) / batch_gal
        total_gravity_points += points

        # Color contribution (MCU)
        color_lov = ferm.color_srm or 3  # Default pale malt color
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

    return calculated_og, calculated_srm


def calculate_ibu_from_hops(
    hops: list["RecipeHop"],
    batch_liters: float,
    og: float
) -> float:
    """Calculate IBU from hop additions using Tinseth formula.

    Args:
        hops: List of RecipeHop models
        batch_liters: Batch size in liters
        og: Original gravity for utilization calculation

    Returns:
        Total IBU
    """
    if batch_liters <= 0:
        batch_liters = 20

    total_ibu = 0

    for hop in hops:
        amount_g = hop.amount_grams or 0
        if amount_g <= 0:
            continue

        alpha_pct = hop.alpha_acid_percent or 5
        if alpha_pct > 1:
            alpha_pct = alpha_pct / 100
        else:
            # Already decimal, keep as is
            pass

        # Get timing info
        timing = hop.timing or {}
        use = timing.get("use", "boil").lower()

        # Get boil time
        duration = timing.get("duration", {})
        if isinstance(duration, dict):
            boil_min = duration.get("value", 0)
        else:
            boil_min = float(duration) if duration else 0

        # Only calculate IBU for boil additions
        # Handle both naming conventions: "boil" vs "add_to_boil"
        if use in ["boil", "add_to_boil", "mash", "add_to_mash", "first_wort"]:
            # Tinseth utilization formula
            # Bigness factor = 1.65 * 0.000125^(OG - 1)
            bigness = 1.65 * (0.000125 ** (og - 1))

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
            # Whirlpool hops contribute ~10-20% of boil utilization
            utilization = 0.05
            ibu_contribution = (amount_g * alpha_pct * utilization * 1000) / batch_liters
            total_ibu += ibu_contribution
        # Dry hops (dry_hop, add_to_fermentation) don't contribute significant IBUs

    return total_ibu


def calculate_fg_and_abv(og: float, attenuation: float) -> tuple[float, float]:
    """Calculate FG and ABV from OG and yeast attenuation.

    Args:
        og: Original gravity
        attenuation: Apparent attenuation as decimal (0.75 = 75%)

    Returns:
        Tuple of (fg, abv)
    """
    if attenuation > 1:
        attenuation = attenuation / 100

    # FG = OG - (OG - 1) * attenuation
    fg = og - (og - 1) * attenuation

    # ABV = (OG - FG) * 131.25
    abv = (og - fg) * 131.25

    return fg, abv


def get_attenuation_from_cultures(
    cultures: list["RecipeCulture"],
    recipe_attenuation: float | None = None
) -> float:
    """Get attenuation from culture list or recipe-level value.

    Args:
        cultures: List of RecipeCulture models
        recipe_attenuation: Recipe-level yeast_attenuation fallback

    Returns:
        Attenuation as decimal (0.75 = 75%)
    """
    # Try to get from cultures
    for culture in cultures:
        atten = culture.attenuation_min_percent
        if atten is not None and atten > 0:
            if atten > 1:
                return atten / 100
            return atten

    # Fall back to recipe-level attenuation
    if recipe_attenuation is not None and recipe_attenuation > 0:
        if recipe_attenuation > 1:
            return recipe_attenuation / 100
        return recipe_attenuation

    # Default 75%
    return 0.75


def calculate_recipe_stats(recipe: "Recipe") -> dict[str, float]:
    """Calculate all brewing statistics for a recipe from its ingredients.

    Args:
        recipe: Recipe model with fermentables, hops, and cultures loaded

    Returns:
        Dict with og, fg, abv, ibu, color_srm
    """
    batch_liters = recipe.batch_size_liters or 20
    efficiency = recipe.efficiency_percent or 72
    if efficiency > 1:
        efficiency = efficiency / 100

    # Calculate OG and color from fermentables
    og, color_srm = calculate_og_from_fermentables(
        recipe.fermentables or [],
        batch_liters,
        efficiency
    )

    # Calculate IBU from hops
    ibu = calculate_ibu_from_hops(
        recipe.hops or [],
        batch_liters,
        og
    )

    # Get attenuation from cultures or recipe
    attenuation = get_attenuation_from_cultures(
        recipe.cultures or [],
        recipe.yeast_attenuation
    )

    # Calculate FG and ABV
    fg, abv = calculate_fg_and_abv(og, attenuation)

    return {
        "og": round(og, 3),
        "fg": round(fg, 3),
        "abv": round(abv, 1),
        "ibu": round(ibu, 0),
        "color_srm": round(color_srm, 1),
    }
