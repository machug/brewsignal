"""Recipe stats for the API: eager-load helpers, effective stats, batch snapshots.

The numbers come from brewing.calculate_recipe_stats; nothing stores them on recipes.
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


LIVE_STATUSES = ("planning", "brewing")
_EXPECTED_FIELDS = ("og", "fg", "abv", "ibu", "srm")


def snapshot_expected(batch: Batch, recipe: Recipe | None) -> None:
    """Freeze the recipe's effective stats on the batch (D6). None clears them."""
    stats = effective_stats(recipe) if recipe is not None else None
    for name in _EXPECTED_FIELDS:
        setattr(batch, f"expected_{name}", getattr(stats, name) if stats else None)


def _expected(batch: Batch, name: str, recipe: Recipe | None = None) -> float | None:
    """planning/brewing read the recipe live (batch.recipe must be loaded with
    ingredients, or pass recipe); later statuses read the snapshot."""
    if (batch.status or "planning") in LIVE_STATUSES:
        recipe = recipe if recipe is not None else getattr(batch, "recipe", None)
        return getattr(effective_stats(recipe), name) if recipe is not None else None
    return getattr(batch, f"expected_{name}")


def batch_recipe_og(batch: Batch, recipe: Recipe | None = None) -> float | None:
    """The recipe's OG for this batch (live or snapshot), ignoring measured_og."""
    return _expected(batch, "og", recipe)


def batch_expected_og(batch: Batch, recipe: Recipe | None = None) -> float | None:
    return batch.measured_og or batch_recipe_og(batch, recipe)


def batch_expected_fg(batch: Batch, recipe: Recipe | None = None) -> float | None:
    return _expected(batch, "fg", recipe)


def batch_expected_abv(batch: Batch, recipe: Recipe | None = None) -> float | None:
    return _expected(batch, "abv", recipe)


def to_recipe_response(recipe: Recipe) -> RecipeResponse:
    return RecipeResponse.model_validate(recipe)


def to_recipe_detail_response(recipe: Recipe) -> RecipeDetailResponse:
    return RecipeDetailResponse.model_validate(recipe)
