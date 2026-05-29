"""Regression: non-native imports must resolve style_id (tilt_ui-ru9).

The import orchestrator (services/importers/recipe_importer.py) converts
BeerXML/Brewfather into BeerJSON, then serializes to ORM. The serializer
drops the BeerJSON `style` object, and converters only carry a style
*name* (not our styles.id FK). Before this fix only native `brewsignal`
imports had style_id populated; every BeerXML/Brewfather import landed
with style_id=NULL even though the style name was present.

These tests exercise the real orchestrator path the POST /api/recipes/import
endpoint uses, asserting the style name is resolved against the BJCP styles
table (the test_db fixture seeds the full BJCP 2021 set).
"""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Recipe
from backend.services.importers.recipe_importer import RecipeImporter


def _beerxml(style_block: str) -> str:
    return f"""<?xml version="1.0"?>
<RECIPES><RECIPE>
<NAME>Import Style IPA</NAME>
<VERSION>1</VERSION>
<TYPE>All Grain</TYPE>
<BREWER>Test Brewer</BREWER>
<BATCH_SIZE>20.0</BATCH_SIZE>
<BOIL_SIZE>24.0</BOIL_SIZE>
<OG>1.065</OG><FG>1.012</FG>
{style_block}
<FERMENTABLES><FERMENTABLE><NAME>Pale Malt</NAME><AMOUNT>5.0</AMOUNT><TYPE>Grain</TYPE></FERMENTABLE></FERMENTABLES>
<HOPS><HOP><NAME>Cascade</NAME><AMOUNT>0.028</AMOUNT><ALPHA>5.5</ALPHA><USE>Boil</USE><TIME>60</TIME></HOP></HOPS>
<YEASTS><YEAST><NAME>US-05</NAME><LABORATORY>Fermentis</LABORATORY></YEAST></YEASTS>
</RECIPE></RECIPES>
"""


STYLE_BLOCK = """<STYLE>
  <NAME>American IPA</NAME>
  <CATEGORY>IPA</CATEGORY>
  <VERSION>1</VERSION>
  <STYLE_GUIDE>BJCP 2021</STYLE_GUIDE>
  <TYPE>Ale</TYPE>
</STYLE>"""


async def _import(db: AsyncSession, content: str) -> Recipe:
    result = await RecipeImporter().import_recipe(content, None, db)
    assert result.success, result.errors
    await db.commit()
    return (
        await db.execute(select(Recipe).where(Recipe.id == result.recipe.id))
    ).scalar_one()


class TestBeerXMLImportStyleResolution:
    @pytest.mark.asyncio
    async def test_beerxml_style_name_resolves_to_style_id(
        self, test_db: AsyncSession
    ):
        recipe = await _import(test_db, _beerxml(STYLE_BLOCK))
        # test_db seeds the real BJCP 2021 set; "American IPA" is 21a.
        assert recipe.style_id == "bjcp-2021-21a"

    @pytest.mark.asyncio
    async def test_unknown_style_name_leaves_style_id_null(
        self, test_db: AsyncSession
    ):
        block = STYLE_BLOCK.replace(
            "American IPA", "Totally Nonexistent Frankenstyle"
        )
        recipe = await _import(test_db, _beerxml(block))
        assert recipe.style_id is None

    @pytest.mark.asyncio
    async def test_no_style_block_leaves_style_id_null(
        self, test_db: AsyncSession
    ):
        recipe = await _import(test_db, _beerxml(""))
        assert recipe.style_id is None
