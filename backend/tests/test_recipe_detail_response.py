"""Integration test for recipe detail response with ingredients."""

import pytest
from backend.models import Recipe, RecipeFermentable, RecipeHop, RecipeCulture, RecipeMisc
from backend.database import get_db, init_db


@pytest.mark.asyncio
async def test_recipe_detail_response_with_ingredients():
    """Test that RecipeDetailResponse correctly includes all ingredients."""
    await init_db()

    async for db in get_db():
        # Create a recipe
        recipe = Recipe(
            name="Test IPA with Ingredients",
            author="Test Brewer",
            og=1.065,
            fg=1.012,
            ibu=60.0,
            batch_size_liters=20.0,
        )
        db.add(recipe)
        await db.commit()
        await db.refresh(recipe)

        # Add fermentables
        fermentable1 = RecipeFermentable(
            recipe_id=recipe.id,
            name="Pale Malt 2-Row",
            type="grain",
            amount_kg=5.0,
            yield_percent=80.0,
            color_srm=2.0,
            origin="US",
            supplier="Briess"
        )
        fermentable2 = RecipeFermentable(
            recipe_id=recipe.id,
            name="Munich Malt",
            type="grain",
            amount_kg=0.5,
            yield_percent=78.0,
            color_srm=10.0,
        )
        db.add(fermentable1)
        db.add(fermentable2)

        # Add hops
        hop1 = RecipeHop(
            recipe_id=recipe.id,
            name="Cascade",
            alpha_acid_percent=5.5,
            amount_grams=28.0,
            timing={"use": "add_to_boil", "duration": {"value": 60, "unit": "min"}},
            form="pellet",
            origin="US"
        )
        hop2 = RecipeHop(
            recipe_id=recipe.id,
            name="Citra",
            alpha_acid_percent=12.0,
            amount_grams=56.0,
            timing={"use": "add_to_fermentation", "phase": "primary", "duration": {"value": 7, "unit": "day"}},
            form="pellet",
            origin="US"
        )
        db.add(hop1)
        db.add(hop2)

        # Add culture (yeast)
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

        # Add misc
        misc = RecipeMisc(
            recipe_id=recipe.id,
            name="Irish Moss",
            type="Fining",
            use="Boil",
            time_min=15,
            amount_kg=0.005,
            amount_is_weight=True
        )
        db.add(misc)

        await db.commit()

        # Now fetch with selectinload
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        result = await db.execute(
            select(Recipe)
            .where(Recipe.id == recipe.id)
            .options(
                selectinload(Recipe.fermentables),
                selectinload(Recipe.hops),
                selectinload(Recipe.cultures),
                selectinload(Recipe.miscs),
            )
        )
        loaded_recipe = result.scalar_one()

        # Verify relationships are loaded
        assert loaded_recipe.name == "Test IPA with Ingredients"
        assert len(loaded_recipe.fermentables) == 2
        assert len(loaded_recipe.hops) == 2
        assert len(loaded_recipe.cultures) == 1
        assert len(loaded_recipe.miscs) == 1

        # Verify fermentable data
        assert loaded_recipe.fermentables[0].name == "Pale Malt 2-Row"
        assert loaded_recipe.fermentables[0].amount_kg == 5.0
        assert loaded_recipe.fermentables[1].name == "Munich Malt"

        # Verify hop data
        assert loaded_recipe.hops[0].name == "Cascade"
        assert loaded_recipe.hops[1].name == "Citra"

        # Verify culture data
        assert loaded_recipe.cultures[0].name == "Safale US-05"
        assert loaded_recipe.cultures[0].producer == "Fermentis"

        # Verify misc data
        assert loaded_recipe.miscs[0].name == "Irish Moss"

        # Test that Pydantic model can be created from ORM object
        from backend.models import RecipeDetailResponse
        response = RecipeDetailResponse.model_validate(loaded_recipe)

        assert response.id == recipe.id
        assert response.name == "Test IPA with Ingredients"
        assert len(response.fermentables) == 2
        assert len(response.hops) == 2
        assert len(response.cultures) == 1
        assert len(response.miscs) == 1

        # Verify serialization to dict
        response_dict = response.model_dump()
        assert response_dict["name"] == "Test IPA with Ingredients"
        assert len(response_dict["fermentables"]) == 2
        assert response_dict["fermentables"][0]["name"] == "Pale Malt 2-Row"
        assert response_dict["hops"][0]["name"] == "Cascade"
        assert response_dict["cultures"][0]["name"] == "Safale US-05"
        assert response_dict["miscs"][0]["name"] == "Irish Moss"

        break
