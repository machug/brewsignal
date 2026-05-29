"""Tests for fermentable color enrichment from the reference table (tilt_ui-81n).

The LLM save path computes SRM from the normalized fermentable's `color`,
defaulting missing colors to ~3 (pale). When the model omits the color of a
dark grain, the whole recipe reads as pale (a stout shows ~3 SRM). The seeded
Fermentable reference table knows real colors (Roasted Barley = 500), so we
enrich missing colors from it before the SRM calc runs.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.fermentable_colors import (
    enrich_fermentable_colors,
    resolve_fermentable_color_srm,
)


class TestResolveColor:
    @pytest.mark.asyncio
    async def test_exact_name(self, test_db: AsyncSession):
        assert await resolve_fermentable_color_srm(test_db, "Roasted Barley") == 500

    @pytest.mark.asyncio
    async def test_case_insensitive(self, test_db: AsyncSession):
        assert await resolve_fermentable_color_srm(test_db, "roasted barley") == 500

    @pytest.mark.asyncio
    async def test_unknown_returns_none(self, test_db: AsyncSession):
        assert await resolve_fermentable_color_srm(test_db, "Unobtainium Malt") is None

    @pytest.mark.asyncio
    async def test_empty_returns_none(self, test_db: AsyncSession):
        assert await resolve_fermentable_color_srm(test_db, "") is None
        assert await resolve_fermentable_color_srm(test_db, None) is None


class TestEnrich:
    @pytest.mark.asyncio
    async def test_fills_missing_dark_grain_color(self, test_db: AsyncSession):
        normalized = {
            "ingredients": {
                "fermentable_additions": [
                    {"name": "Roasted Barley", "amount": {"value": 0.4, "unit": "kg"}},
                ]
            }
        }
        count = await enrich_fermentable_colors(test_db, normalized)
        ferm = normalized["ingredients"]["fermentable_additions"][0]
        assert count == 1
        assert ferm["color"] == {"value": 500.0, "unit": "SRM"}

    @pytest.mark.asyncio
    async def test_does_not_overwrite_provided_color(self, test_db: AsyncSession):
        normalized = {
            "ingredients": {
                "fermentable_additions": [
                    {
                        "name": "Roasted Barley",
                        "amount": {"value": 0.4, "unit": "kg"},
                        "color": {"value": 600, "unit": "SRM"},
                    },
                ]
            }
        }
        count = await enrich_fermentable_colors(test_db, normalized)
        assert count == 0
        assert normalized["ingredients"]["fermentable_additions"][0]["color"][
            "value"
        ] == 600

    @pytest.mark.asyncio
    async def test_reference_overrides_guessed_color(self, test_db: AsyncSession):
        # Normalizer guessed Chocolate Malt = 400 (hard-coded map); seeded
        # reference says 350 and must win. Guess marker is stripped.
        normalized = {
            "ingredients": {
                "fermentable_additions": [
                    {
                        "name": "Chocolate Malt",
                        "amount": {"value": 0.2, "unit": "kg"},
                        "color": {"value": 400, "unit": "SRM"},
                        "_color_guessed": True,
                    },
                ]
            }
        }
        count = await enrich_fermentable_colors(test_db, normalized)
        ferm = normalized["ingredients"]["fermentable_additions"][0]
        assert count == 1
        assert ferm["color"]["value"] == 350
        assert "_color_guessed" not in ferm

    @pytest.mark.asyncio
    async def test_unknown_grain_left_uncolored(self, test_db: AsyncSession):
        normalized = {
            "ingredients": {
                "fermentable_additions": [
                    {"name": "Unobtainium Malt", "amount": {"value": 1, "unit": "kg"}},
                ]
            }
        }
        count = await enrich_fermentable_colors(test_db, normalized)
        assert count == 0
        assert "color" not in normalized["ingredients"]["fermentable_additions"][0]

    @pytest.mark.asyncio
    async def test_no_fermentables_is_noop(self, test_db: AsyncSession):
        assert await enrich_fermentable_colors(test_db, {}) == 0
        assert await enrich_fermentable_colors(test_db, {"ingredients": {}}) == 0
