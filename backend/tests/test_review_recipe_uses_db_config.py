"""Tests for the LLM-service source used by review_recipe (tilt_ui-bzx).

review_recipe was calling the global LLMService singleton, but nothing
initialises that singleton at startup, so it returned an
"AI assistant is not configured" error in production. The chat path
builds its own LLMService(config) from get_llm_config(db). This module
pins that review_recipe does the same — builds from db, not singleton.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import (
    Config, Recipe, RecipeCulture, RecipeFermentable, RecipeHop, Style,
)
from backend.services.llm.tools.recipe import review_recipe


@pytest_asyncio.fixture
async def configured_llm(test_db: AsyncSession):
    """Seed the Config table with a working LLM provider so get_llm_config
    returns a configured LLMConfig."""
    rows = [
        Config(key="ai_enabled", value="true"),
        Config(key="ai_provider", value='"openrouter"'),
        Config(key="ai_model", value='"anthropic/claude-sonnet-4"'),
        Config(key="ai_api_key", value='"sk-or-test"'),
    ]
    test_db.add_all(rows)
    await test_db.commit()


@pytest_asyncio.fixture
async def style_apa(test_db: AsyncSession) -> Style:
    style = Style(
        id="test-style-apa-bzx",
        guide="BJCP 2021",
        category_number="18",
        style_letter="B",
        name="Test APA",
        category="Pale American Ale",
        type="Ale",
        og_min=1.045, og_max=1.060,
        fg_min=1.010, fg_max=1.015,
        abv_min=4.5, abv_max=6.2,
        ibu_min=30, ibu_max=50,
        srm_min=5, srm_max=10,
    )
    test_db.add(style)
    await test_db.commit()
    return style


@pytest_asyncio.fixture
async def recipe_in_style(test_db: AsyncSession, style_apa: Style) -> Recipe:
    recipe = Recipe(
        name="Configured APA",
        type="all-grain",
        style_id=style_apa.id,
        batch_size_liters=20,
        og=1.052, fg=1.012, abv=5.2, ibu=38, color_srm=7,
        user_id="test-user",
    )
    recipe.fermentables.append(
        RecipeFermentable(name="Pale Ale Malt", amount_kg=4.5, color_srm=3)
    )
    recipe.hops.append(
        RecipeHop(name="Centennial", amount_grams=30, alpha_acid_percent=10.0,
                  timing={"use": "add_to_boil",
                          "duration": {"value": 60, "unit": "min"}})
    )
    recipe.cultures.append(
        RecipeCulture(name="US-05", attenuation_min_percent=77)
    )
    test_db.add(recipe)
    await test_db.commit()
    await test_db.refresh(recipe)
    return recipe


class TestReviewRecipeUsesDbConfig:
    @pytest.mark.asyncio
    async def test_runs_review_when_db_has_configured_llm(
        self, test_db: AsyncSession, recipe_in_style: Recipe, configured_llm
    ):
        """When ai_enabled=true and an api_key is set in Config, review_recipe
        must NOT short-circuit to the 'not configured' error path."""
        fake_chat = AsyncMock(return_value="Looks good.")

        # Patch the LLMService class so the chat call is mocked but
        # is_configured() reflects the DB-loaded config (which is enabled).
        class FakeLLMService:
            def __init__(self, cfg):
                self.config = MagicMock()
                self.config.effective_model = cfg.model or "test-model"
                self.config.is_configured.return_value = cfg.enabled and bool(
                    cfg.api_key
                )

            async def chat(self, messages, **kwargs):
                return await fake_chat(messages, **kwargs)

        with patch(
            "backend.services.llm.tools.recipe.LLMService",
            FakeLLMService,
        ):
            result = await review_recipe(
                db=test_db,
                recipe_id=recipe_in_style.id,
                user_id="test-user",
            )

        assert "error" not in result, (
            f"review_recipe returned an error with a configured LLM in the "
            f"DB — it is probably still using the uninit'd singleton "
            f"instead of building from db. Got: {result}"
        )
        assert result["review"] == "Looks good."
        fake_chat.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_errors_when_db_llm_disabled(
        self, test_db: AsyncSession, recipe_in_style: Recipe
    ):
        # No Config rows seeded → ai_enabled=false → is_configured()=False.
        result = await review_recipe(
            db=test_db,
            recipe_id=recipe_in_style.id,
            user_id="test-user",
        )
        assert "error" in result
        assert "configured" in result["error"].lower()
