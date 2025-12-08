import pytest
from backend.models import Recipe, RecipeCulture
from backend.database import get_db, init_db


@pytest.mark.asyncio
async def test_create_culture_with_recipe():
    """Test creating culture (yeast) linked to a recipe."""
    await init_db()

    async for db in get_db():
        recipe = Recipe(name="Test Ale")
        db.add(recipe)
        await db.commit()
        await db.refresh(recipe)

        culture = RecipeCulture(
            recipe_id=recipe.id,
            name="Safale US-05",
            producer="Fermentis",
            product_id="US-05",
            type="ale",
            form="dry",
            attenuation_min_percent=81.0,
            attenuation_max_percent=81.0,
            temp_min_c=15.0,
            temp_max_c=24.0,
        )
        db.add(culture)
        await db.commit()
        await db.refresh(culture)

        assert culture.id is not None
        assert culture.name == "Safale US-05"
        break
