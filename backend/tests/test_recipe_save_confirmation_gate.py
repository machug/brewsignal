"""Tests for the save/update confirmation gate (tilt_ui-i3i).

save_recipe and update_recipe must not persist anything unless the LLM
explicitly passes user_confirmed=True. The gate prevents the assistant from
silently saving a recipe in the middle of a design conversation — the
contract is "review + ask + save," not "infer and write."
"""

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Recipe
from backend.services.llm.tools.recipe import save_recipe, update_recipe


VALID_RECIPE = {
    "name": "Gated IPA",
    "type": "all-grain",
    "batch_size_liters": 20,
    "fermentables": [{"name": "Pale Ale Malt", "amount_kg": 4.5}],
    "hops": [{"name": "Centennial", "amount_g": 30, "time_minutes": 60,
              "use": "boil", "alpha_acid": 10.0}],
    "cultures": [{"name": "US-05"}],
}


@pytest_asyncio.fixture
async def saved_recipe_id(test_db: AsyncSession) -> int:
    """Bootstrap an existing recipe so update_recipe gating can be exercised."""
    result = await save_recipe(
        db=test_db,
        recipe=VALID_RECIPE,
        user_confirmed=True,
        user_id="test-user",
    )
    assert result.get("success") is True, result
    return result["recipe_id"]


class TestSaveRecipeConfirmationGate:
    @pytest.mark.asyncio
    async def test_save_without_confirmation_does_not_persist(
        self, test_db: AsyncSession
    ):
        result = await save_recipe(
            db=test_db,
            recipe=VALID_RECIPE,
            user_id="test-user",
        )
        assert result.get("requires_confirmation") is True
        assert result.get("success") is not True
        # Nothing committed.
        rows = (await test_db.execute(select(Recipe))).scalars().all()
        assert rows == []

    @pytest.mark.asyncio
    async def test_save_with_confirmation_false_is_blocked(
        self, test_db: AsyncSession
    ):
        result = await save_recipe(
            db=test_db,
            recipe=VALID_RECIPE,
            user_confirmed=False,
            user_id="test-user",
        )
        assert result.get("requires_confirmation") is True
        assert result.get("success") is not True

    @pytest.mark.asyncio
    async def test_save_with_confirmation_true_persists(
        self, test_db: AsyncSession
    ):
        result = await save_recipe(
            db=test_db,
            recipe=VALID_RECIPE,
            user_confirmed=True,
            user_id="test-user",
        )
        assert result.get("success") is True
        rows = (await test_db.execute(select(Recipe))).scalars().all()
        assert len(rows) == 1


class TestUpdateRecipeConfirmationGate:
    @pytest.mark.asyncio
    async def test_update_without_confirmation_does_not_mutate(
        self, test_db: AsyncSession, saved_recipe_id: int
    ):
        result = await update_recipe(
            db=test_db,
            recipe_id=saved_recipe_id,
            recipe={**VALID_RECIPE, "name": "Renamed"},
            user_id="test-user",
        )
        assert result.get("requires_confirmation") is True
        assert result.get("success") is not True
        recipe = (
            await test_db.execute(select(Recipe).where(Recipe.id == saved_recipe_id))
        ).scalar_one()
        assert recipe.name == "Gated IPA"

    @pytest.mark.asyncio
    async def test_update_with_confirmation_true_mutates(
        self, test_db: AsyncSession, saved_recipe_id: int
    ):
        result = await update_recipe(
            db=test_db,
            recipe_id=saved_recipe_id,
            recipe={**VALID_RECIPE, "name": "Renamed"},
            user_confirmed=True,
            user_id="test-user",
        )
        assert result.get("success") is True
        recipe = (
            await test_db.execute(select(Recipe).where(Recipe.id == saved_recipe_id))
        ).scalar_one()
        assert recipe.name == "Renamed"
