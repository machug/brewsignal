import pytest
from backend.models import Recipe, RecipeHop
from backend.database import get_db, init_db


@pytest.mark.asyncio
async def test_create_hop_with_recipe():
    """Test creating a hop addition linked to a recipe."""
    await init_db()

    async for db in get_db():
        recipe = Recipe(name="Test IPA", og_target=1.065)
        db.add(recipe)
        await db.commit()
        await db.refresh(recipe)

        hop = RecipeHop(
            recipe_id=recipe.id,
            name="Cascade",
            alpha_percent=5.5,
            amount_kg=0.028,  # 28g = 1oz
            use="Boil",
            time_min=60,
            form="Pellet",
            type="Bittering"
        )
        db.add(hop)
        await db.commit()
        await db.refresh(hop)

        assert hop.id is not None
        assert hop.name == "Cascade"
        assert hop.use == "Boil"
        assert hop.time_min == 60
        break
