"""Recipe stats for the API: eager-load helpers, effective stats, legacy columns.

The numbers come from brewing.calculate_recipe_stats; nothing here stores them
except fill_legacy_columns (deleted in Task 5 with the legacy columns).
"""
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import Select, select
from sqlalchemy.orm import selectinload

from ..models import Batch, Recipe, RecipeDetailResponse, RecipeResponse
from .brewing import calculate_recipe_stats


def recipe_with_ingredients_stmt() -> Select:
    return select(Recipe).options(
        selectinload(Recipe.style),
        selectinload(Recipe.fermentables),
        selectinload(Recipe.hops),
        selectinload(Recipe.cultures),
    )


def batch_with_recipe_options() -> list:
    return [
        selectinload(Batch.recipe).selectinload(Recipe.style),
        selectinload(Batch.recipe).selectinload(Recipe.fermentables),
        selectinload(Batch.recipe).selectinload(Recipe.hops),
        selectinload(Batch.recipe).selectinload(Recipe.cultures),
    ]


@dataclass
class EffectiveStats:
    og: float | None
    fg: float | None
    abv: float | None
    ibu: float | None
    srm: float | None
    source: Literal["calculated", "declared", "empty"]


def effective_stats(recipe: Recipe) -> EffectiveStats:
    """Per field: calculated value if not None, else target_*, else None."""
    calc = calculate_recipe_stats(recipe)
    names = ("og", "fg", "abv", "ibu", "srm")
    if calc is not None:
        calculated = {n: getattr(calc, n) for n in names}
    else:
        calculated = dict.fromkeys(names)
    values = {n: calculated[n] if calculated[n] is not None else getattr(recipe, f"target_{n}") for n in names}
    if calc is not None:
        source = "calculated"
    elif any(v is not None for v in values.values()):
        source = "declared"
    else:
        source = "empty"
    return EffectiveStats(source=source, **values)


def fill_legacy_columns(recipe: Recipe) -> None:
    """Write recipe.og/fg/abv/ibu/color_srm from the calculator (until Task 5).

    Leaves them untouched when there is nothing to calculate.
    """
    stats = calculate_recipe_stats(recipe)
    if stats is None:
        return
    recipe.og, recipe.fg, recipe.abv = stats.og, stats.fg, stats.abv
    recipe.ibu, recipe.color_srm = stats.ibu, stats.srm


def to_recipe_response(recipe: Recipe) -> RecipeResponse:
    return RecipeResponse.model_validate(recipe)


def to_recipe_detail_response(recipe: Recipe) -> RecipeDetailResponse:
    return RecipeDetailResponse.model_validate(recipe)
