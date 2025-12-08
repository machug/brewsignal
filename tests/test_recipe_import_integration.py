"""Integration test for BeerXML import with new BeerJSON schema."""

import os
import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession
from backend.database import engine, init_db
from backend.models import Recipe, RecipeHop, RecipeCulture
from backend.services.recipe_importer import import_beerxml_to_db


@pytest.fixture(autouse=True)
async def cleanup_db():
    """Clean up database before test."""
    await engine.dispose()
    test_db_path = 'data/fermentation.db'
    if os.path.exists(test_db_path):
        os.remove(test_db_path)
    yield


@pytest.mark.asyncio
async def test_import_beerxml_with_new_schema():
    """Test that BeerXML import works with new BeerJSON schema."""
    # Initialize database
    await init_db()

    # Read test BeerXML file
    with open('docs/Brewfather_BeerXML_PhilterXPAClone_20251207.xml', 'r') as f:
        xml_content = f.read()

    # Create session and import recipe
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        recipe_id = await import_beerxml_to_db(session, xml_content)

        # Verify recipe was created with new field names
        result = await session.execute(
            select(Recipe).where(Recipe.id == recipe_id)
        )
        recipe = result.scalar_one()

        assert recipe.id == recipe_id
        assert recipe.name is not None
        # Verify new BeerJSON field names exist (may be None if not in BeerXML)
        assert hasattr(recipe, 'og')
        assert hasattr(recipe, 'fg')
        assert hasattr(recipe, 'ibu')
        assert hasattr(recipe, 'color_srm')
        assert hasattr(recipe, 'batch_size_liters')

        # Verify hops use new schema
        result = await session.execute(
            select(RecipeHop).where(RecipeHop.recipe_id == recipe_id)
        )
        hops = result.scalars().all()

        assert len(hops) > 0
        for hop in hops:
            assert hop.alpha_acid_percent is not None  # New field name
            assert hop.amount_grams is not None  # New field name (converted from kg)
            # beta_acid_percent should be preserved if present in original
            if hop.beta_acid_percent:
                assert hop.beta_acid_percent > 0

        # Verify cultures (yeasts) were created
        result = await session.execute(
            select(RecipeCulture).where(RecipeCulture.recipe_id == recipe_id)
        )
        cultures = result.scalars().all()

        assert len(cultures) > 0
        for culture in cultures:
            assert culture.name is not None
