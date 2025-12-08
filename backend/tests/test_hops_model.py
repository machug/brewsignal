import pytest
from backend.models import Recipe, RecipeHop
from backend.database import get_db, init_db


@pytest.mark.asyncio
async def test_create_hop_with_recipe():
    """Test creating a hop addition linked to a recipe."""
    await init_db()

    async for db in get_db():
        recipe = Recipe(name="Test IPA", og=1.065)
        db.add(recipe)
        await db.commit()
        await db.refresh(recipe)

        hop = RecipeHop(
            recipe_id=recipe.id,
            name="Cascade",
            alpha_acid_percent=5.5,
            amount_grams=28.0,  # 28g = 1oz
            form="Pellet",
            timing={"use": "Boil", "time": 60, "duration": {"value": 60, "unit": "min"}},
            format_extensions={"hop_type": "Bittering"}
        )
        db.add(hop)
        await db.commit()
        await db.refresh(hop)

        assert hop.id is not None
        assert hop.name == "Cascade"
        assert hop.timing["use"] == "Boil"
        assert hop.timing["time"] == 60
        break
