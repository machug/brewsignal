"""Unit tests for resolve_style_id alias handling (tilt_ui-ru9, fix #2).

Brewers type colloquial style names that aren't BJCP-canonical: "West Coast
IPA", "NEIPA", "XPA". Exact + substring matching misses all of these, so the
style_id lands NULL. A curated alias map maps the common shorthand to a
canonical BJCP name, which is then resolved through the normal lookup.

These run against the test_db fixture, which seeds the full BJCP 2021 set.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Style
from backend.services.style_resolver import resolve_style_id


class TestExactAndSubstring:
    """Regression: existing behavior must keep working."""

    @pytest.mark.asyncio
    async def test_exact_name(self, test_db: AsyncSession):
        assert await resolve_style_id(test_db, "American IPA") == "bjcp-2021-21a"

    @pytest.mark.asyncio
    async def test_case_insensitive(self, test_db: AsyncSession):
        assert await resolve_style_id(test_db, "american ipa") == "bjcp-2021-21a"

    @pytest.mark.asyncio
    async def test_unknown_returns_none(self, test_db: AsyncSession):
        assert await resolve_style_id(test_db, "Frankenstyle XYZ") is None

    @pytest.mark.asyncio
    async def test_empty_returns_none(self, test_db: AsyncSession):
        assert await resolve_style_id(test_db, "") is None
        assert await resolve_style_id(test_db, None) is None


class TestAliases:
    @pytest.mark.parametrize(
        "alias,expected",
        [
            ("West Coast IPA", "bjcp-2021-21a"),
            ("west coast ipa", "bjcp-2021-21a"),
            ("WCIPA", "bjcp-2021-21a"),
            ("NEIPA", "bjcp-2021-21c"),
            ("New England IPA", "bjcp-2021-21c"),
            ("Juicy IPA", "bjcp-2021-21c"),
            ("XPA", "bjcp-2021-18b"),
            ("Extra Pale Ale", "bjcp-2021-18b"),
            ("APA", "bjcp-2021-18b"),
            ("DIPA", "bjcp-2021-22a"),
            ("Imperial IPA", "bjcp-2021-22a"),
            ("Dry Stout", "bjcp-2021-15b"),
            ("Irish Dry Stout", "bjcp-2021-15b"),
        ],
    )
    @pytest.mark.asyncio
    async def test_alias_resolves(self, test_db: AsyncSession, alias, expected):
        assert await resolve_style_id(test_db, alias) == expected

    @pytest.mark.asyncio
    async def test_alias_with_surrounding_whitespace(self, test_db: AsyncSession):
        assert await resolve_style_id(test_db, "  NEIPA  ") == "bjcp-2021-21c"

    @pytest.mark.asyncio
    async def test_strict_mode_skips_substring(self, test_db: AsyncSession):
        # "IPA" substring-matches some style by default, but allow_substring=
        # False returns None (used by the noisy recipe.type backfill).
        assert await resolve_style_id(test_db, "IPA") is not None
        assert await resolve_style_id(test_db, "IPA", allow_substring=False) is None

    @pytest.mark.asyncio
    async def test_strict_mode_keeps_exact_and_alias(self, test_db: AsyncSession):
        assert await resolve_style_id(
            test_db, "Irish Stout", allow_substring=False
        ) == "bjcp-2021-15b"
        assert await resolve_style_id(
            test_db, "NEIPA", allow_substring=False
        ) == "bjcp-2021-21c"

    @pytest.mark.asyncio
    async def test_exact_alias_beats_substring_decoy(self, test_db: AsyncSession):
        """An exact alias hit must win over a loose substring match against
        some other row whose name merely contains the alias text."""
        decoy = Style(
            id="decoy-apa-experimental",
            guide="Custom",
            category_number="X",
            name="APA Experimental Sour",  # substring-matches "APA"
            category="Test",
            type="Ale",
        )
        test_db.add(decoy)
        await test_db.commit()
        # "APA" -> alias -> American Pale Ale (18b), NOT the decoy row.
        assert await resolve_style_id(test_db, "APA") == "bjcp-2021-18b"
