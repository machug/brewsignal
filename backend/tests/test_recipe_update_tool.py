"""Tests for the update_recipe LLM tool (tilt_ui-3ps).

When the user asks the brewing assistant to edit a recipe, save_recipe always
creates a new row. update_recipe replaces an existing recipe by id (full
replacement of fields + children) so edits stay attached to the same recipe_id.
"""

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.models import Recipe, RecipeFermentable, RecipeHop, RecipeCulture
from backend.services.llm.tools.recipe import save_recipe, update_recipe


@pytest_asyncio.fixture
async def saved_recipe(test_db: AsyncSession) -> dict:
    """Save a baseline recipe via the tool and return its summary dict."""
    result = await save_recipe(
        db=test_db,
        recipe={
            "name": "Original IPA",
            "type": "all-grain",
            "batch_size_liters": 20,
            "fermentables": [
                {"name": "Pale Ale Malt", "amount_kg": 4.5},
                {"name": "Crystal 40", "amount_kg": 0.3},
            ],
            "hops": [
                {"name": "Centennial", "amount_g": 30, "time_minutes": 60,
                 "use": "boil", "alpha_acid": 10.0},
            ],
            "cultures": [
                {"name": "US-05", "producer": "Fermentis", "attenuation": 77},
            ],
        },
        user_confirmed=True,
        user_id="test-user",
    )
    assert result.get("success") is True, result
    return result


class TestUpdateRecipeTool:
    @pytest.mark.asyncio
    async def test_update_preserves_recipe_id(
        self, test_db: AsyncSession, saved_recipe: dict
    ):
        recipe_id = saved_recipe["recipe_id"]
        result = await update_recipe(
            db=test_db,
            recipe_id=recipe_id,
            recipe={
                "name": "Renamed IPA",
                "type": "all-grain",
                "batch_size_liters": 20,
                "fermentables": [{"name": "Pale Ale Malt", "amount_kg": 4.5}],
                "hops": [{"name": "Cascade", "amount_g": 40,
                          "time_minutes": 60, "use": "boil", "alpha_acid": 6.0}],
                "cultures": [{"name": "US-05"}],
            },
            user_confirmed=True,
            user_id="test-user",
        )
        assert result.get("success") is True, result
        assert result["recipe_id"] == recipe_id

    @pytest.mark.asyncio
    async def test_update_replaces_scalar_fields(
        self, test_db: AsyncSession, saved_recipe: dict
    ):
        recipe_id = saved_recipe["recipe_id"]
        await update_recipe(
            db=test_db,
            recipe_id=recipe_id,
            recipe={
                "name": "Renamed IPA",
                "notes": "Brewed for summer",
                "batch_size_liters": 25,
                "fermentables": [{"name": "Pale Ale Malt", "amount_kg": 5.0}],
                "hops": [{"name": "Cascade", "amount_g": 40,
                          "time_minutes": 60, "use": "boil", "alpha_acid": 6.0}],
                "cultures": [{"name": "US-05"}],
            },
            user_confirmed=True,
            user_id="test-user",
        )
        recipe = (
            await test_db.execute(select(Recipe).where(Recipe.id == recipe_id))
        ).scalar_one()
        assert recipe.name == "Renamed IPA"
        assert recipe.notes == "Brewed for summer"
        assert recipe.batch_size_liters == 25

    @pytest.mark.asyncio
    async def test_update_replaces_children(
        self, test_db: AsyncSession, saved_recipe: dict
    ):
        recipe_id = saved_recipe["recipe_id"]
        await update_recipe(
            db=test_db,
            recipe_id=recipe_id,
            recipe={
                "name": "Renamed IPA",
                "fermentables": [{"name": "Maris Otter", "amount_kg": 4.0}],
                "hops": [
                    {"name": "Mosaic", "amount_g": 50, "time_minutes": 10,
                     "use": "boil", "alpha_acid": 12.0},
                    {"name": "Citra", "amount_g": 60, "time_minutes": -1,
                     "use": "dry_hop", "alpha_acid": 11.0},
                ],
                "cultures": [{"name": "S-04"}],
            },
            user_confirmed=True,
            user_id="test-user",
        )
        recipe = (
            await test_db.execute(
                select(Recipe)
                .options(
                    selectinload(Recipe.fermentables),
                    selectinload(Recipe.hops),
                    selectinload(Recipe.cultures),
                )
                .where(Recipe.id == recipe_id)
            )
        ).scalar_one()
        assert [f.name for f in recipe.fermentables] == ["Maris Otter"]
        assert sorted(h.name for h in recipe.hops) == ["Citra", "Mosaic"]
        assert [c.name for c in recipe.cultures] == ["S-04"]

    @pytest.mark.asyncio
    async def test_update_recalculates_stats(
        self, test_db: AsyncSession, saved_recipe: dict
    ):
        recipe_id = saved_recipe["recipe_id"]
        result = await update_recipe(
            db=test_db,
            recipe_id=recipe_id,
            recipe={
                "name": "Big IPA",
                "batch_size_liters": 20,
                "fermentables": [{"name": "Pale Ale Malt", "amount_kg": 8.0}],
                "hops": [{"name": "Magnum", "amount_g": 50,
                          "time_minutes": 60, "use": "boil", "alpha_acid": 14.0}],
                "cultures": [{"name": "US-05", "attenuation": 77}],
            },
            user_confirmed=True,
            user_id="test-user",
        )
        assert result["og"] > saved_recipe["og"], (
            f"expected OG to rise from {saved_recipe['og']} to >{saved_recipe['og']}, "
            f"got {result['og']}"
        )

    @pytest.mark.asyncio
    async def test_update_returns_error_for_unknown_id(self, test_db: AsyncSession):
        result = await update_recipe(
            db=test_db,
            recipe_id=999999,
            recipe={
                "name": "Ghost",
                "fermentables": [{"name": "Pale", "amount_kg": 4}],
                "hops": [{"name": "Cascade", "amount_g": 30, "time_minutes": 60,
                          "use": "boil", "alpha_acid": 6}],
                "cultures": [{"name": "US-05"}],
            },
            user_confirmed=True,
            user_id="test-user",
        )
        assert "error" in result

    @pytest.mark.asyncio
    async def test_update_orphans_old_children(
        self, test_db: AsyncSession, saved_recipe: dict
    ):
        """After update, old hop/fermentable rows should be deleted, not just
        unlinked. delete-orphan cascade must fire."""
        recipe_id = saved_recipe["recipe_id"]
        await update_recipe(
            db=test_db,
            recipe_id=recipe_id,
            recipe={
                "name": "Renamed",
                "fermentables": [{"name": "Pilsner", "amount_kg": 4.0}],
                "hops": [{"name": "Saaz", "amount_g": 30, "time_minutes": 60,
                          "use": "boil", "alpha_acid": 4.0}],
                "cultures": [{"name": "US-05"}],
            },
            user_confirmed=True,
            user_id="test-user",
        )
        hops = (
            await test_db.execute(select(RecipeHop))
        ).scalars().all()
        assert {h.name for h in hops} == {"Saaz"}
        ferms = (
            await test_db.execute(select(RecipeFermentable))
        ).scalars().all()
        assert {f.name for f in ferms} == {"Pilsner"}
