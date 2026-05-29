"""Build recipe_fermentables / recipe_hops rows from the editor's
format_extensions payload.

The web editor (POST/PUT /api/recipes) historically wrote ingredients only to
recipes.format_extensions, leaving the recipe_hops / recipe_fermentables
relationship tables empty (tilt_ui-9y7). Downstream consumers — server-side
stat recalculation, LLM round-trips, sync — read the relationship tables and
saw nothing. format_extensions also omits grain colors (tilt_ui-hfi).

This module treats format_extensions as the transient editor cache and the
relationship tables as the source of truth: it maps the editor ingredient
shapes into ORM rows, enriching missing grain colors from the seeded reference
table so the recipe's color is correct.
"""
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Recipe, RecipeFermentable, RecipeHop
from .fermentable_colors import resolve_fermentable_color_srm


def _num(value: Any) -> Optional[float]:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _potential_to_yield(potential_sg: Optional[float]) -> Optional[float]:
    """Invert the editor's yield->potential mapping (1 + yield/100 * 0.046)
    so OG-relevant extract potential survives the round-trip as yield_percent."""
    if potential_sg is None:
        return None
    return (potential_sg - 1.0) / 0.046 * 100


async def _build_fermentables(
    db: AsyncSession, rows: list[dict[str, Any]]
) -> list[RecipeFermentable]:
    total_kg = sum((_num(r.get("amount_kg")) or 0.0) for r in rows) or 0.0
    built: list[RecipeFermentable] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        # Editor sends color under color_srm or (legacy) color_lovibond; both
        # are SRM here. Fall back to the seeded reference table by name so dark
        # grains aren't stored color-less (tilt_ui-hfi).
        color = _num(r.get("color_srm"))
        if color is None:
            color = _num(r.get("color_lovibond"))
        if color is None:
            color = await resolve_fermentable_color_srm(db, r.get("name"))
        amount_kg = _num(r.get("amount_kg")) or 0.0
        built.append(
            RecipeFermentable(
                name=r.get("name") or "Unknown Grain",
                type=r.get("type"),
                amount_kg=amount_kg,
                color_srm=color,
                percentage=(amount_kg / total_kg * 100) if total_kg else None,
                # Preserve OG-relevant extract potential: editor sends
                # potential_sg, the column is yield_percent.
                yield_percent=_num(r.get("yield_percent"))
                or _potential_to_yield(_num(r.get("potential_sg"))),
                origin=r.get("origin"),
                supplier=r.get("maltster") or r.get("supplier"),
                # Keep the full editor row so no metadata is lost on rebuild.
                format_extensions=r,
            )
        )
    return built


def _build_hops(rows: list[dict[str, Any]]) -> list[RecipeHop]:
    built: list[RecipeHop] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        is_extract = bool(r.get("is_extract"))
        # Editor `use` is already the short BeerJSON-ish form the IBU calc and
        # detail page understand ("boil", "dry_hop", "whirlpool", ...). Keep it
        # verbatim in timing; the IBU calc reads timing.use + duration.value.
        use = r.get("use") or ("dry_hop" if is_extract else "boil")
        timing: dict[str, Any] = {"use": use, "continuous": False}
        boil_min = _num(r.get("boil_time_minutes"))
        if boil_min is not None:
            timing["duration"] = {"value": boil_min, "unit": "min"}
        built.append(
            RecipeHop(
                name=r.get("name") or "Unknown Hop",
                amount_grams=_num(r.get("amount_grams")) or 0.0,
                alpha_acid_percent=_num(r.get("alpha_acid_percent")),
                beta_acid_percent=_num(r.get("beta_acid_percent")),
                form=r.get("form"),
                origin=r.get("origin"),
                is_extract=is_extract,
                amount_ml=_num(r.get("amount_ml")) if is_extract else None,
                timing=timing,
                # Keep the full editor row (purpose, etc.) for round-trip.
                format_extensions=r,
            )
        )
    return built


async def hydrate_recipe_ingredients(
    db: AsyncSession, recipe: Recipe, fmt_ext: Optional[dict[str, Any]]
) -> bool:
    """Populate recipe.fermentables / recipe.hops from format_extensions.

    A present key (even an empty list) is authoritative and rebuilds that
    collection; an absent key leaves the existing collection untouched. Returns
    True if fermentables were (re)built (so the caller can recompute color).
    """
    if not isinstance(fmt_ext, dict):
        return False

    ferms = fmt_ext.get("fermentables")
    hops = fmt_ext.get("hops")

    rebuilt_fermentables = False
    if ferms is not None:
        recipe.fermentables.clear()
        for ferm in await _build_fermentables(db, ferms):
            recipe.fermentables.append(ferm)
        rebuilt_fermentables = True

    if hops is not None:
        recipe.hops.clear()
        for hop in _build_hops(hops):
            recipe.hops.append(hop)

    return rebuilt_fermentables
