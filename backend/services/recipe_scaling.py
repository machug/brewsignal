"""Proportional recipe scaling (tilt_ui-2kzp).

Scales every per-batch amount on a recipe by target/current batch ratio:
relationship tables (the source of truth) plus the recipe-level
format_extensions editor cache the UI reads. Concentration-style values
(gravities, IBU, SRM, efficiency, ppm targets, temperatures, times) are
left alone — stats are recomputed by the caller via calculate_recipe_stats
and should come out nearly unchanged, which doubles as a sanity check.
"""

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from backend.models import Recipe

# Salt masses are absolute grams for the adjusted volume, so they scale with
# it — that keeps the resulting ion ppm constant.
_WATER_SALT_FIELDS = (
    "calcium_sulfate_g",
    "calcium_chloride_g",
    "magnesium_sulfate_g",
    "sodium_bicarbonate_g",
    "calcium_carbonate_g",
    "calcium_hydroxide_g",
    "magnesium_chloride_g",
    "sodium_chloride_g",
)


def _scaled(value: Optional[float], ratio: float, ndigits: int) -> Optional[float]:
    if value is None:
        return None
    return round(value * ratio, ndigits)


def scale_recipe(recipe: "Recipe", target_batch_liters: float) -> float:
    """Scale ``recipe`` in place to ``target_batch_liters``. Returns the ratio.

    Requires recipe.batch_size_liters to be set and positive; the caller is
    responsible for validating that (and for recomputing stats after).
    """
    ratio = target_batch_liters / recipe.batch_size_liters

    for fermentable in recipe.fermentables:
        fermentable.amount_kg = _scaled(fermentable.amount_kg, ratio, 3)

    for hop in recipe.hops:
        hop.amount_grams = _scaled(hop.amount_grams, ratio, 1)
        hop.amount_ml = _scaled(hop.amount_ml, ratio, 1)

    for misc in recipe.miscs:
        # amount_kg holds the value in amount_unit units; every supported
        # unit (g/kg/ml/l/tsp/tbsp/items) is a per-batch dose.
        misc.amount_kg = _scaled(misc.amount_kg, ratio, 3)

    for culture in recipe.cultures:
        # ml/g scale linearly; packages do too (brewers round at pitch time).
        culture.amount = _scaled(culture.amount, ratio, 2)

    for step in recipe.mash_steps:
        step.infusion_amount_liters = _scaled(step.infusion_amount_liters, ratio, 2)

    for adjustment in recipe.water_adjustments:
        adjustment.volume_liters = _scaled(adjustment.volume_liters, ratio, 2)
        adjustment.acid_ml = _scaled(adjustment.acid_ml, ratio, 2)
        for field in _WATER_SALT_FIELDS:
            setattr(adjustment, field, _scaled(getattr(adjustment, field), ratio, 2))

    recipe.boil_size_l = _scaled(recipe.boil_size_l, ratio, 2)
    recipe.priming_sugar_amount_kg = _scaled(recipe.priming_sugar_amount_kg, ratio, 3)

    _scale_format_extensions(recipe, ratio)

    recipe.batch_size_liters = target_batch_liters
    return ratio


def _scale_format_extensions(recipe: "Recipe", ratio: float) -> None:
    """Scale the recipe-level editor cache (fermentables/hops mirrors).

    The UI reads these preferentially over the relationship tables, so they
    must stay in sync. Reassign a fresh dict — in-place mutation of a JSON
    column does not mark the attribute dirty.
    """
    ext = recipe.format_extensions
    if not isinstance(ext, dict):
        return

    new_ext = dict(ext)
    if isinstance(ext.get("fermentables"), list):
        new_ext["fermentables"] = [
            {**f, "amount_kg": _scaled(f.get("amount_kg"), ratio, 3)}
            if isinstance(f, dict)
            else f
            for f in ext["fermentables"]
        ]
    if isinstance(ext.get("hops"), list):
        new_ext["hops"] = [
            {
                **h,
                "amount_grams": _scaled(h.get("amount_grams"), ratio, 1),
                "amount_ml": _scaled(h.get("amount_ml"), ratio, 1),
            }
            if isinstance(h, dict)
            else h
            for h in ext["hops"]
        ]
    recipe.format_extensions = new_ext
