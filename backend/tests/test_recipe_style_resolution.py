"""Tests for BJCP style resolution in save_recipe / update_recipe (tilt_ui-3vc).

When the brewing assistant passes a style name in the recipe payload
(e.g. "American IPA"), save_recipe should look up the matching BJCP
Style row and set Recipe.style_id so review_recipe_narrative and the
detail-page review can find the target style without the user supplying
style_id manually.
"""

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Recipe, Style
from backend.services.llm.tools.recipe import save_recipe, update_recipe


@pytest_asyncio.fixture
async def style_apa(test_db: AsyncSession) -> Style:
    style = Style(
        id="test-style-apa-resolve",
        guide="BJCP 2021",
        category_number="18",
        style_letter="B",
        name="Test American Pale Ale",
        category="Pale American Ale",
        type="Ale",
    )
    test_db.add(style)
    await test_db.commit()
    return style


def _recipe_payload(style_value):
    payload = {
        "name": "Style Resolve IPA",
        "type": "all-grain",
        "batch_size_liters": 20,
        "fermentables": [{"name": "Pale Ale Malt", "amount_kg": 4.5}],
        "hops": [{"name": "Centennial", "amount_g": 30, "time_minutes": 60,
                  "use": "boil", "alpha_acid": 10.0}],
        "cultures": [{"name": "US-05"}],
    }
    if style_value is not None:
        payload["style"] = style_value
    return payload


class TestSaveRecipeStyleResolution:
    @pytest.mark.asyncio
    async def test_resolves_style_name_to_style_id(
        self, test_db: AsyncSession, style_apa: Style
    ):
        result = await save_recipe(
            db=test_db,
            recipe=_recipe_payload("Test American Pale Ale"),
            user_confirmed=True,
            user_id="test-user",
        )
        assert result.get("success") is True, result
        recipe = (
            await test_db.execute(select(Recipe).where(Recipe.id == result["recipe_id"]))
        ).scalar_one()
        assert recipe.style_id == style_apa.id

    @pytest.mark.asyncio
    async def test_resolves_style_name_case_insensitive(
        self, test_db: AsyncSession, style_apa: Style
    ):
        result = await save_recipe(
            db=test_db,
            recipe=_recipe_payload("test american pale ale"),
            user_confirmed=True,
            user_id="test-user",
        )
        assert result.get("success") is True
        recipe = (
            await test_db.execute(select(Recipe).where(Recipe.id == result["recipe_id"]))
        ).scalar_one()
        assert recipe.style_id == style_apa.id

    @pytest.mark.asyncio
    async def test_unknown_style_name_leaves_style_id_null(
        self, test_db: AsyncSession
    ):
        result = await save_recipe(
            db=test_db,
            recipe=_recipe_payload("Nonexistent Frankenstyle XYZ"),
            user_confirmed=True,
            user_id="test-user",
        )
        assert result.get("success") is True
        recipe = (
            await test_db.execute(select(Recipe).where(Recipe.id == result["recipe_id"]))
        ).scalar_one()
        assert recipe.style_id is None

    @pytest.mark.asyncio
    async def test_no_style_field_leaves_style_id_null(self, test_db: AsyncSession):
        result = await save_recipe(
            db=test_db,
            recipe=_recipe_payload(None),
            user_confirmed=True,
            user_id="test-user",
        )
        assert result.get("success") is True
        recipe = (
            await test_db.execute(select(Recipe).where(Recipe.id == result["recipe_id"]))
        ).scalar_one()
        assert recipe.style_id is None


class TestUpdateRecipeStyleResolution:
    @pytest.mark.asyncio
    async def test_update_can_set_style_for_existing_recipe(
        self, test_db: AsyncSession, style_apa: Style
    ):
        # Create without style first
        created = await save_recipe(
            db=test_db,
            recipe=_recipe_payload(None),
            user_confirmed=True,
            user_id="test-user",
        )
        rid = created["recipe_id"]
        # Update with style name
        await update_recipe(
            db=test_db,
            recipe_id=rid,
            recipe=_recipe_payload("Test American Pale Ale"),
            user_confirmed=True,
            user_id="test-user",
        )
        recipe = (
            await test_db.execute(select(Recipe).where(Recipe.id == rid))
        ).scalar_one()
        assert recipe.style_id == style_apa.id
