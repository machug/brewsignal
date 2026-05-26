"""Tests for the renamed/bundled review_recipe tool (tilt_ui-sbb).

The narrative tool was previously named review_recipe_narrative and lived
alongside a separate review_recipe_style. The LLM consistently picked
review_recipe_style for "style review" requests despite a sharpened prompt.
This shrinks the surface area: review_recipe is now the single primary tool
and returns BOTH the narrative review text AND the numeric compliance block
in one call, so the LLM has one obvious choice.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import (
    Recipe, RecipeCulture, RecipeFermentable, RecipeHop, Style,
)
from backend.services.llm.tools.recipe import review_recipe


@pytest_asyncio.fixture
async def apa_style(test_db: AsyncSession) -> Style:
    style = Style(
        id="test-style-apa-bundled",
        guide="BJCP 2021",
        category_number="18",
        style_letter="B",
        name="Test Bundled APA",
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
async def recipe_in_style(
    test_db: AsyncSession, apa_style: Style
) -> Recipe:
    recipe = Recipe(
        name="In-Range APA",
        type="all-grain",
        style_id=apa_style.id,
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
        RecipeCulture(name="US-05", producer="Fermentis",
                      attenuation_min_percent=77)
    )
    test_db.add(recipe)
    await test_db.commit()
    await test_db.refresh(recipe)
    return recipe


@pytest_asyncio.fixture
async def recipe_no_style(test_db: AsyncSession) -> Recipe:
    recipe = Recipe(
        name="Unstyled",
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


def _service(chat_return="Looks good."):
    svc = MagicMock()
    svc.chat = AsyncMock(return_value=chat_return)
    svc.config.effective_model = "test-model"
    svc.config.is_configured.return_value = True
    return svc


class TestReviewRecipeBundled:
    @pytest.mark.asyncio
    async def test_returns_narrative_and_compliance_in_one_call(
        self, test_db: AsyncSession, recipe_in_style: Recipe
    ):
        with patch(
            "backend.services.llm.tools.recipe.get_llm_service",
            return_value=_service("Solid APA."),
        ):
            result = await review_recipe(
                db=test_db,
                recipe_id=recipe_in_style.id,
                user_id="test-user",
            )
        assert result.get("review") == "Solid APA."
        assert result.get("style_found") is True
        assert "compliance" in result, result
        assert "style_fit_score" in result
        assert result.get("style_fit_score_scale") == "0-10 (10 = every stat in range)"
        # Score is on a 0-10 scale derived from how many stats are in range.
        assert isinstance(result["style_fit_score"], (int, float))
        assert 0 <= result["style_fit_score"] <= 10

    @pytest.mark.asyncio
    async def test_compliance_block_has_all_five_stats(
        self, test_db: AsyncSession, apa_style: Style, recipe_in_style: Recipe
    ):
        with patch(
            "backend.services.llm.tools.recipe.get_llm_service",
            return_value=_service(),
        ):
            result = await review_recipe(
                db=test_db,
                recipe_id=recipe_in_style.id,
                user_id="test-user",
            )
        assert set(result["compliance"].keys()) == {"og", "fg", "abv", "ibu", "srm"}
        for stat in result["compliance"].values():
            assert "status" in stat
            assert stat["status"] in (
                "in_range", "below", "above", "no_guideline", "unknown",
            )

    @pytest.mark.asyncio
    async def test_recipe_without_style_omits_compliance_gracefully(
        self, test_db: AsyncSession, recipe_no_style: Recipe
    ):
        with patch(
            "backend.services.llm.tools.recipe.get_llm_service",
            return_value=_service("General feedback."),
        ):
            result = await review_recipe(
                db=test_db,
                recipe_id=recipe_no_style.id,
                user_id="test-user",
            )
        assert result.get("style_found") is False
        # Compliance block is None or omitted when there's no target style.
        assert result.get("compliance") in (None, {}) or "compliance" not in result

    @pytest.mark.asyncio
    async def test_unknown_recipe_id_returns_error(self, test_db: AsyncSession):
        with patch(
            "backend.services.llm.tools.recipe.get_llm_service",
            return_value=_service(),
        ):
            result = await review_recipe(
                db=test_db, recipe_id=999_999, user_id="test-user",
            )
        assert "error" in result
