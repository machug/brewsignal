"""Brewing calculations for recipe statistics.

Provides deterministic server-side calculation of OG, FG, ABV, IBU, and color
from recipe ingredients. These calculations replace LLM-based estimation.
"""
import math
from dataclasses import asdict, dataclass
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

# Fermentable types added to the kettle rather than mashed: they contribute
# their full potential, so brewhouse efficiency must not be applied.
NO_EFFICIENCY_TYPES = {"sugar", "extract", "dry extract", "liquid extract", "honey", "fruit", "juice"}


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


def _note(assumptions: list[str] | None, text: str) -> None:
    """Record an assumption once (no-op when the caller does not collect them)."""
    if assumptions is not None and text not in assumptions:
        assumptions.append(text)


def calculate_og_from_fermentables(
    fermentables: list["RecipeFermentable"],
    batch_liters: float,
    efficiency: float,
    assumptions: list[str] | None = None,
) -> tuple[float, float]:
    """Calculate OG and color (SRM) from fermentable ingredients.

    Args:
        fermentables: List of RecipeFermentable models
        batch_liters: Batch size in liters
        efficiency: Brewhouse efficiency as decimal (0.72 = 72%)
        assumptions: Optional list that collects a line for each estimated input

    Returns:
        Tuple of (og, color_srm). SRM is not capped.
    """
    if batch_liters <= 0:
        batch_liters = 20  # Default

    if efficiency > 1:
        efficiency = efficiency / 100

    total_gravity_points = 0.0
    total_mcu = 0.0  # Malt Color Units
    batch_gal = batch_liters / 3.785

    for ferm in fermentables:
        amount_kg = ferm.amount_kg or 0
        if amount_kg <= 0:
            continue

        if not ferm.yield_percent or ferm.yield_percent <= 0:
            _note(assumptions, f"Estimated yield for {ferm.name}")
        potential = get_extract_potential(ferm.name, ferm.yield_percent)

        # gravity points = (lbs * PPG * efficiency) / gallons; 1 kg = 2.205 lbs
        ferm_type = (ferm.type or "").lower()
        ferm_efficiency = 1.0 if ferm_type in NO_EFFICIENCY_TYPES else efficiency
        grain_lbs = amount_kg * 2.205
        total_gravity_points += (grain_lbs * potential * ferm_efficiency) / batch_gal

        if ferm.color_srm is None:
            _note(assumptions, f"Estimated colour for {ferm.name}")
            color_lov = 3  # pale malt
        else:
            color_lov = ferm.color_srm
        total_mcu += (grain_lbs * color_lov) / (batch_liters * 0.264172)

    og = 1.0 + (total_gravity_points / 1000)

    # Morey equation: SRM = 1.4922 * MCU^0.6859
    srm = 1.4922 * (total_mcu ** 0.6859) if total_mcu > 0 else 0.0
    return og, srm


def hop_stand_temp_factor(timing: dict) -> float:
    """Alpha-acid isomerisation rate at the stand temperature, relative to a boil.

    Malowicki's Arrhenius fit, the relation Brewfather uses for its aroma hop
    utilisation (80 C -> 0.23, 90.2 C -> 0.50). No recorded temperature means
    a boil-hot stand (factor 1), so whirlpool hops saved before temperatures
    were captured keep their IBU.
    """
    temp = (timing.get("temperature") or {}).get("value")
    if temp is None:
        return 1.0
    return min(1.0, 2.39e11 * math.exp(-9773 / (float(temp) + 273.15)))


_UNIT_MINUTES = {
    "day": 1440, "days": 1440, "d": 1440,
    "hr": 60, "hrs": 60, "h": 60, "hour": 60, "hours": 60,
    "s": 1 / 60, "sec": 1 / 60, "secs": 1 / 60, "second": 1 / 60, "seconds": 1 / 60,
}


def _duration_minutes(timing: dict) -> float:
    """Hop timing duration in minutes; units other than day/hour/second count as minutes."""
    duration = timing.get("duration")
    if isinstance(duration, dict):
        value, unit = duration.get("value"), duration.get("unit")
    else:
        value, unit = duration, None
    try:
        value = float(value or 0)
    except (TypeError, ValueError):
        return 0.0
    return value * _UNIT_MINUTES.get(str(unit or "min").lower(), 1)


def _calculate_ibu(
    hops: list["RecipeHop"],
    og: float,
    batch_liters: float,
    assumptions: list[str] | None = None,
) -> float:
    """Total IBU (Tinseth for the boil, Malowicki-scaled ramp for whirlpool).

    Args:
        hops: List of RecipeHop models (or fakes exposing the same attrs)
        og: Original gravity for utilization calculation
        batch_liters: Batch size in liters
        assumptions: Optional list that collects a line for each estimated input
    """
    if batch_liters <= 0:
        batch_liters = 20

    total_ibu = 0.0

    for hop in hops:
        if getattr(hop, "is_extract", False):
            # Abstrax-style extracts have no alpha acids and contribute zero
            # IBU regardless of timing/amount (tilt_ui-0l5).
            continue
        amount_g = hop.amount_grams or 0
        if amount_g <= 0:
            continue

        timing = hop.timing or {}
        use = (timing.get("use") or "boil").lower()
        minutes = _duration_minutes(timing)
        is_boil = use in ("boil", "add_to_boil", "mash", "add_to_mash", "first_wort")
        is_whirlpool = use in ("whirlpool", "add_to_whirlpool")
        # Dry hop / add_to_fermentation / add_to_package give 0 IBU; so does a 0 min boil hop.
        if not (is_whirlpool or (is_boil and minutes > 0)):
            continue

        name = getattr(hop, "name", None) or "hop"
        alpha_pct = hop.alpha_acid_percent
        if not alpha_pct or alpha_pct <= 0:
            _note(assumptions, f"Assumed 5% alpha for {name}")
            alpha_pct = 5
        if alpha_pct > 1:
            alpha_pct = alpha_pct / 100

        if is_boil:
            bigness = 1.65 * (0.000125 ** (og - 1))
            utilization = bigness * (1 - math.exp(-0.04 * minutes)) / 4.15
            # Missing form defaults to pellet (+10%); first-wort +10% (tilt_ui-nbh0).
            if "pellet" in (getattr(hop, "form", None) or "pellet").lower():
                utilization *= 1.10
            if use == "first_wort":
                utilization *= 1.10
        else:
            # Hop-stand: ramp from 5% to a 20% cap, scaled by stand temperature
            # (tilt_ui-23u, tilt_ui-2mxj).
            if (timing.get("temperature") or {}).get("value") is None:
                _note(assumptions, f"No whirlpool temperature for {name}: counted as boiling")
            utilization = min(0.05 + 0.005 * max(0.0, minutes), 0.20) * hop_stand_temp_factor(timing)

        total_ibu += (amount_g * alpha_pct * utilization * 1000) / batch_liters

    return total_ibu


def calculate_ibu_from_hops(
    hops: list["RecipeHop"],
    batch_liters: float,
    og: float,
    assumptions: list[str] | None = None,
) -> float:
    """Total IBU from hop additions; historical (hops, batch_liters, og) signature."""
    return _calculate_ibu(hops, og=og, batch_liters=batch_liters, assumptions=assumptions)


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

    fg = og - (og - 1) * attenuation
    abv = (og - fg) * 131.25
    return fg, abv


def get_attenuation_from_cultures(
    cultures: list["RecipeCulture"],
    recipe_attenuation: float | None = None,
    assumptions: list[str] | None = None,
) -> float:
    """Attenuation as a decimal (0.75 = 75%).

    Order: middle of the first culture's range, or its one set bound, then
    the recipe-level value, then 75%.
    """
    def frac(v: float) -> float:
        return v / 100 if v > 1 else v

    for culture in cultures:
        bounds = [
            frac(v) for v in (culture.attenuation_min_percent, culture.attenuation_max_percent)
            if v is not None and v > 0
        ]
        if bounds:
            return sum(bounds) / len(bounds)

    if recipe_attenuation is not None and recipe_attenuation > 0:
        return frac(recipe_attenuation)

    _note(assumptions, "Assumed 75% yeast attenuation")
    return 0.75


# BJCP-style SRM colour chart, ported from frontend srmToHex.
_SRM_HEX = {
    1: "#FFE699", 2: "#FFD878", 3: "#FFCA5A", 4: "#FFBF42", 5: "#FBB123",
    6: "#F8A600", 7: "#F39C00", 8: "#EA8F00", 9: "#E58500", 10: "#DE7C00",
    11: "#D77200", 12: "#CF6900", 13: "#CB6200", 14: "#C35900", 15: "#BB5100",
    16: "#B54C00", 17: "#B04500", 18: "#A63E00", 19: "#A13700", 20: "#9B3200",
    25: "#7C2900", 30: "#5E1E00", 35: "#401500", 40: "#261000",
}


def srm_to_hex(srm: float) -> str:
    """Colour for an SRM value; clamps to 1..40."""
    clamped = max(1, min(40, srm))
    return _SRM_HEX[max(k for k in _SRM_HEX if k <= clamped)]


@dataclass(frozen=True)
class CalculatedStats:
    """Recipe stats from the calculator. Rounded here: SG 3 dp, IBU/SRM 1 dp, ABV 2 dp."""
    og: float
    fg: float
    abv: float
    ibu: float
    srm: float
    bu_gu: float
    calories_per_330ml: int
    color_hex: str
    assumptions: tuple[str, ...]

    def __post_init__(self):
        for name, dp in (("og", 3), ("fg", 3), ("abv", 2), ("ibu", 1), ("srm", 1), ("bu_gu", 2)):
            object.__setattr__(self, name, round(getattr(self, name), dp))

    def to_dict(self) -> dict:
        d = asdict(self)
        d["assumptions"] = list(self.assumptions)
        return d


def calculate_recipe_stats(recipe: "Recipe") -> CalculatedStats | None:
    """Calculate all stats for a recipe from its ingredients, or None with no fermentables.

    Pure: reads attributes only (no DB, no lazy loads). Inputs the recipe does
    not give are defaulted and listed in `assumptions`.
    """
    fermentables = [f for f in (recipe.fermentables or []) if (f.amount_kg or 0) > 0]
    if not fermentables:
        return None
    notes: list[str] = []

    batch_liters = recipe.batch_size_liters
    if not batch_liters or batch_liters <= 0:
        batch_liters = 20
        _note(notes, "Assumed 20 L batch")

    efficiency = recipe.efficiency_percent
    if not efficiency or efficiency <= 0:
        efficiency = 75
        if any((f.type or "").lower() not in NO_EFFICIENCY_TYPES for f in fermentables):
            _note(notes, "Assumed 75% brewhouse efficiency")

    og, srm = calculate_og_from_fermentables(fermentables, batch_liters, efficiency, notes)
    ibu = calculate_ibu_from_hops(recipe.hops or [], batch_liters, og, notes)
    attenuation = get_attenuation_from_cultures(
        recipe.cultures or [], recipe.yeast_attenuation, notes
    )
    fg, abv = calculate_fg_and_abv(og, attenuation)

    og_points = (og - 1) * 1000
    # Ported from frontend calculateCalories (330 mL serving) and calculateBUGU.
    calories = (abv * 0.79 * 7 + (fg - 1) * 1000 * 0.4) * 3.3

    return CalculatedStats(
        og=og, fg=fg, abv=abv, ibu=ibu, srm=srm,
        bu_gu=ibu / og_points if og_points > 0 else 0.0,
        calories_per_330ml=math.floor(calories + 0.5),
        color_hex=srm_to_hex(srm),
        assumptions=tuple(notes),
    )


def write_legacy_stats(recipe: "Recipe", stats: CalculatedStats | None) -> None:
    """Copy stats into the stored recipe.og/fg/abv/ibu/color_srm columns (until Task 5)."""
    if stats is None:
        return
    recipe.og, recipe.fg, recipe.abv = stats.og, stats.fg, stats.abv
    recipe.ibu, recipe.color_srm = stats.ibu, stats.srm
