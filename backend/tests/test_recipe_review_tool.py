"""Tests for the review_recipe_narrative LLM tool (tilt_ui-95b).

Exposes the prompty-based BJCP recipe review (previously HTTP-only at
/api/assistant/review-recipe) as an LLM-callable tool so the brewing
assistant can run it itself during a conversation.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import (
    Recipe, RecipeCulture, RecipeFermentable, RecipeHop, Style,
)
from backend.services.llm.tools.recipe import review_recipe_narrative


@pytest_asyncio.fixture
async def style_apa(test_db: AsyncSession) -> Style:
    style = Style(
        id="test-style-apa",
        guide="BJCP 2021",
        category_number="18",
        style_letter="B",
        name="Test American Pale Ale",
        category="Pale American Ale",
        type="Ale",
        og_min=1.045, og_max=1.060,
        fg_min=1.010, fg_max=1.015,
        abv_min=4.5, abv_max=6.2,
        ibu_min=30, ibu_max=50,
        srm_min=5, srm_max=10,
        description="Refreshing American hop showcase.",
    )
    test_db.add(style)
    await test_db.commit()
    return style


@pytest_asyncio.fixture
async def recipe_with_style(
    test_db: AsyncSession, style_apa: Style
) -> Recipe:
    recipe = Recipe(
        name="Test APA",
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
        RecipeCulture(name="US-05", producer="Fermentis", attenuation_min_percent=77)
    )
    test_db.add(recipe)
    await test_db.commit()
    await test_db.refresh(recipe)
    return recipe


@pytest_asyncio.fixture
async def recipe_without_style(test_db: AsyncSession) -> Recipe:
    recipe = Recipe(
        name="Style-less Brew",
        type="all-grain",
        batch_size_liters=20,
        og=1.050, fg=1.012, abv=5.0, ibu=25, color_srm=8,
        user_id="test-user",
    )
    recipe.fermentables.append(
        RecipeFermentable(name="Pale Ale Malt", amount_kg=4.0)
    )
    test_db.add(recipe)
    await test_db.commit()
    await test_db.refresh(recipe)
    return recipe


class TestReviewRecipeNarrativeTool:
    @pytest.mark.asyncio
    async def test_returns_review_text_for_recipe_with_style(
        self, test_db: AsyncSession, recipe_with_style: Recipe
    ):
        mock_service = MagicMock()
        mock_service.chat = AsyncMock(return_value="This recipe fits the APA style well.")
        mock_service.config.effective_model = "test-model"
        mock_service.config.is_configured.return_value = True

        with patch(
            "backend.services.llm.tools.recipe.get_llm_service",
            return_value=mock_service,
        ):
            result = await review_recipe_narrative(
                db=test_db,
                recipe_id=recipe_with_style.id,
                user_id="test-user",
            )

        assert "error" not in result, result
        assert result["review"] == "This recipe fits the APA style well."
        assert result["style_found"] is True
        assert result["style_name"] == "Test American Pale Ale"
        assert result["model"] == "test-model"
        mock_service.chat.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_prompt_includes_recipe_stats_and_ingredients(
        self, test_db: AsyncSession, recipe_with_style: Recipe
    ):
        captured: dict = {}

        async def fake_chat(messages, **_kwargs):
            captured["messages"] = messages
            return "ok"

        mock_service = MagicMock()
        mock_service.chat = fake_chat
        mock_service.config.effective_model = "test-model"
        mock_service.config.is_configured.return_value = True

        with patch(
            "backend.services.llm.tools.recipe.get_llm_service",
            return_value=mock_service,
        ):
            await review_recipe_narrative(
                db=test_db,
                recipe_id=recipe_with_style.id,
                user_id="test-user",
            )

        rendered = "\n".join(
            m.get("content", "") if isinstance(m, dict) else str(m)
            for m in captured["messages"]
        )
        assert "Test APA" in rendered
        assert "Test American Pale Ale" in rendered
        assert "Pale Ale Malt" in rendered
        assert "Centennial" in rendered

    @pytest.mark.asyncio
    async def test_handles_recipe_without_style(
        self, test_db: AsyncSession, recipe_without_style: Recipe
    ):
        mock_service = MagicMock()
        mock_service.chat = AsyncMock(return_value="No style declared.")
        mock_service.config.effective_model = "test-model"
        mock_service.config.is_configured.return_value = True

        with patch(
            "backend.services.llm.tools.recipe.get_llm_service",
            return_value=mock_service,
        ):
            result = await review_recipe_narrative(
                db=test_db,
                recipe_id=recipe_without_style.id,
                user_id="test-user",
            )

        assert "error" not in result
        assert result["style_found"] is False
        assert result["review"] == "No style declared."

    @pytest.mark.asyncio
    async def test_recipe_not_found_returns_error(self, test_db: AsyncSession):
        mock_service = MagicMock()
        mock_service.config.is_configured.return_value = True
        with patch(
            "backend.services.llm.tools.recipe.get_llm_service",
            return_value=mock_service,
        ):
            result = await review_recipe_narrative(
                db=test_db, recipe_id=999_999, user_id="test-user",
            )
        assert "error" in result
        assert "999999" in result["error"] or "not found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_returns_error_when_llm_not_configured(
        self, test_db: AsyncSession, recipe_with_style: Recipe
    ):
        mock_service = MagicMock()
        mock_service.config.is_configured.return_value = False
        with patch(
            "backend.services.llm.tools.recipe.get_llm_service",
            return_value=mock_service,
        ):
            result = await review_recipe_narrative(
                db=test_db,
                recipe_id=recipe_with_style.id,
                user_id="test-user",
            )
        assert "error" in result
