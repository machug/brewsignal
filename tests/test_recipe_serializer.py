"""Test RecipeSerializer - converts BeerJSON dict to SQLAlchemy models."""
import pytest
import json
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.database import init_db, get_db
from backend.models import (
    Recipe, RecipeFermentable, RecipeHop, RecipeCulture, RecipeMisc,
    RecipeMashStep, RecipeFermentationStep, RecipeWaterProfile, RecipeWaterAdjustment
)
from backend.services.serializers.recipe_serializer import RecipeSerializer


@pytest.mark.asyncio
async def test_serialize_brewfather_beerjson_to_models():
    """Test serializing validated BeerJSON to SQLAlchemy models.

    This tests the complete pipeline from validated BeerJSON (Task 7 output)
    to persisted database models.
    """
    # Initialize database
    await init_db()

    # Load validated BeerJSON from Task 7
    with open("docs/Brewfather_to_BeerJSON_output.json", "r") as f:
        beerjson_data = json.load(f)

    recipe_dict = beerjson_data['beerjson']['recipes'][0]

    # Serialize to SQLAlchemy models
    serializer = RecipeSerializer()
    async for session in get_db():
        recipe = await serializer.serialize(recipe_dict, session)

        # Add to session and flush to get ID
        session.add(recipe)
        await session.flush()

        # Verify recipe was created
        assert recipe.id is not None
        assert recipe.name == "Philter XPA - Clone"
        assert recipe.type == "all grain"
        assert recipe.author == "Pig Den Brewing"

        # Verify batch size (extract value from BeerJSON unit object)
        assert recipe.batch_size_liters == 21.0

        # Verify gravity values (extract from unit objects)
        assert recipe.og == pytest.approx(1.040069094, abs=0.0001)
        assert recipe.fg == pytest.approx(1.008, abs=0.0001)

        # Verify ABV (stored as decimal, not percentage)
        assert recipe.abv == pytest.approx(0.042, abs=0.001)

        # Verify color and IBU
        assert recipe.color_srm == pytest.approx(3.8, abs=0.1)
        assert recipe.ibu == pytest.approx(28.7, abs=0.1)

        # Verify boil time
        assert recipe.boil_time_minutes == 60

        # Verify efficiency
        assert recipe.efficiency_percent == pytest.approx(73.0, abs=0.1)

        # Verify carbonation (stored as raw value)
        assert recipe.carbonation_vols == pytest.approx(2.4, abs=0.1)

        # Verify notes
        assert "Australian XPA" in recipe.notes

        # Commit and reload with relationships
        session.add(recipe)
        await session.commit()
        recipe_id = recipe.id
        await session.close()

    # Reload and verify relationships
    async for session in get_db():
        stmt = (
            select(Recipe)
            .where(Recipe.id == recipe_id)
            .options(
                selectinload(Recipe.fermentables),
                selectinload(Recipe.hops),
                selectinload(Recipe.cultures),
                selectinload(Recipe.miscs),
                selectinload(Recipe.mash_steps),
                selectinload(Recipe.fermentation_steps)
            )
        )
        result = await session.execute(stmt)
        recipe = result.scalar_one()

        # Verify fermentables (4 grains)
        assert len(recipe.fermentables) == 4

        ale_malt = next(f for f in recipe.fermentables if f.name == "Ale Malt")
        assert ale_malt.amount_kg == pytest.approx(2.733, abs=0.001)
        assert ale_malt.origin == "New Zealand"
        assert ale_malt.supplier == "Gladfield"
        assert ale_malt.color_srm == pytest.approx(3.0456853, abs=0.001)
        assert ale_malt.yield_percent == pytest.approx(81.4, abs=0.1)
        assert ale_malt.grain_group == "base"

        # Verify hops (6 additions)
        assert len(recipe.hops) == 6

        citra_boil = next(
            h for h in recipe.hops
            if h.name == "Citra" and h.timing.get('use') == 'add_to_boil'
        )
        assert citra_boil.amount_grams == pytest.approx(46.0, abs=0.1)
        assert citra_boil.alpha_acid_percent == pytest.approx(14.1, abs=0.1)
        assert citra_boil.form == "pellet"
        assert citra_boil.origin == "US"
        assert citra_boil.timing['duration']['value'] == 30.0
        assert citra_boil.timing['duration']['unit'] == 'min'

        # Verify dry hop
        citra_dryhop = next(
            h for h in recipe.hops
            if h.name == "Citra" and h.timing.get('use') == 'add_to_fermentation'
        )
        assert citra_dryhop.amount_grams == pytest.approx(31.5, abs=0.1)
        assert citra_dryhop.timing['duration']['value'] == 4
        assert citra_dryhop.timing['duration']['unit'] == 'day'

        # Verify cultures (yeast)
        assert len(recipe.cultures) >= 1

        yeast = recipe.cultures[0]
        assert "US-05" in yeast.name or "Safale" in yeast.name
        assert yeast.type in ['ale', 'lager', 'other']
        assert yeast.form in ['dry', 'liquid']

        # Verify mash steps
        assert len(recipe.mash_steps) >= 1

        first_step = recipe.mash_steps[0]
        assert first_step.step_number >= 1
        assert first_step.temp_c > 0
        assert first_step.time_minutes > 0

        await session.close()
        break


@pytest.mark.asyncio
async def test_serialize_extracts_unit_values():
    """Test that serializer correctly extracts values from BeerJSON unit objects."""
    await init_db()

    # Minimal BeerJSON recipe with unit objects
    recipe_dict = {
        "name": "Test Recipe",
        "type": "all grain",
        "author": "Test Author",
        "batch_size": {
            "value": 20.0,
            "unit": "l"
        },
        "original_gravity": {
            "value": 1.050,
            "unit": "sg"
        },
        "final_gravity": {
            "value": 1.010,
            "unit": "sg"
        },
        "alcohol_by_volume": {
            "value": 0.052,
            "unit": "%"
        },
        "ibu_estimate": {
            "value": 35.0,
            "unit": "1"
        },
        "color_estimate": {
            "value": 5.5,
            "unit": "SRM"
        },
        "boil": {
            "boil_time": {
                "value": 60.0,
                "unit": "min"
            }
        },
        "efficiency": {
            "brewhouse": {
                "value": 0.75,
                "unit": "%"
            }
        },
        "carbonation": 2.5,
        "ingredients": {
            "fermentable_additions": []
        }
    }

    serializer = RecipeSerializer()
    async for session in get_db():
        recipe = await serializer.serialize(recipe_dict, session)

        # Verify unit extraction
        assert recipe.batch_size_liters == 20.0
        assert recipe.og == pytest.approx(1.050)
        assert recipe.fg == pytest.approx(1.010)
        assert recipe.abv == pytest.approx(0.052)
        assert recipe.ibu == pytest.approx(35.0)
        assert recipe.color_srm == pytest.approx(5.5)
        assert recipe.boil_time_minutes == 60
        assert recipe.efficiency_percent == pytest.approx(75.0)
        assert recipe.carbonation_vols == pytest.approx(2.5)

        await session.close()
        break


@pytest.mark.asyncio
async def test_serialize_handles_optional_fields():
    """Test that serializer handles missing optional fields gracefully."""
    await init_db()

    # Minimal required fields only
    recipe_dict = {
        "name": "Minimal Recipe",
        "type": "extract",
        "author": "Test",
        "batch_size": {
            "value": 19.0,
            "unit": "l"
        },
        "efficiency": {
            "brewhouse": {
                "value": 0.70,
                "unit": "%"
            }
        },
        "ingredients": {
            "fermentable_additions": [
                {
                    "name": "Pale Malt Extract",
                    "type": "extract",
                    "origin": "US",
                    "amount": {
                        "value": 3.0,
                        "unit": "kg"
                    },
                    "yield": {
                        "fine_grind": {
                            "value": 0.80,
                            "unit": "%"
                        }
                    },
                    "color": {
                        "value": 2.0,
                        "unit": "SRM"
                    }
                }
            ]
        }
    }

    serializer = RecipeSerializer()
    async for session in get_db():
        recipe = await serializer.serialize(recipe_dict, session)

        # Required fields
        assert recipe.name == "Minimal Recipe"
        assert recipe.batch_size_liters == 19.0

        # Optional fields should be None
        assert recipe.og is None
        assert recipe.fg is None
        assert recipe.abv is None
        assert recipe.ibu is None
        assert recipe.color_srm is None
        assert recipe.boil_time_minutes is None
        assert recipe.carbonation_vols is None

        # Should have one fermentable
        session.add(recipe)
        await session.commit()
        assert len(recipe.fermentables) == 1

        await session.close()
        break


@pytest.mark.asyncio
async def test_serialize_mash_steps():
    """Test serialization of mash steps from BeerJSON."""
    await init_db()

    recipe_dict = {
        "name": "Mash Test",
        "type": "all grain",
        "author": "Test",
        "batch_size": {"value": 20.0, "unit": "l"},
        "efficiency": {"brewhouse": {"value": 0.75, "unit": "%"}},
        "ingredients": {"fermentable_additions": []},
        "mash": {
            "name": "Single Infusion",
            "mash_steps": [
                {
                    "name": "Saccharification",
                    "type": "temperature",
                    "step_temperature": {
                        "value": 65.0,
                        "unit": "C"
                    },
                    "step_time": {
                        "value": 60.0,
                        "unit": "min"
                    }
                },
                {
                    "name": "Mash Out",
                    "type": "temperature",
                    "step_temperature": {
                        "value": 76.0,
                        "unit": "C"
                    },
                    "step_time": {
                        "value": 10.0,
                        "unit": "min"
                    }
                }
            ]
        }
    }

    serializer = RecipeSerializer()
    async for session in get_db():
        recipe = await serializer.serialize(recipe_dict, session)
        session.add(recipe)
        await session.commit()

        # Reload with mash steps
        await session.refresh(recipe, ['mash_steps'])

        assert len(recipe.mash_steps) == 2

        step1 = recipe.mash_steps[0]
        assert step1.name == "Saccharification"
        assert step1.type == "temperature"
        assert step1.temp_c == pytest.approx(65.0)
        assert step1.time_minutes == 60
        assert step1.step_number == 1

        step2 = recipe.mash_steps[1]
        assert step2.name == "Mash Out"
        assert step2.temp_c == pytest.approx(76.0)
        assert step2.time_minutes == 10
        assert step2.step_number == 2

        await session.close()
        break


@pytest.mark.asyncio
async def test_serialize_fermentation_steps():
    """Test serialization of fermentation steps from BeerJSON."""
    await init_db()

    recipe_dict = {
        "name": "Fermentation Test",
        "type": "all grain",
        "author": "Test",
        "batch_size": {"value": 20.0, "unit": "l"},
        "efficiency": {"brewhouse": {"value": 0.75, "unit": "%"}},
        "ingredients": {"fermentable_additions": []},
        "fermentation": {
            "fermentation_steps": [
                {
                    "name": "Primary",
                    "step_temperature": {
                        "value": 18.0,
                        "unit": "C"
                    },
                    "step_time": {
                        "value": 14,
                        "unit": "day"
                    }
                },
                {
                    "name": "Cold Crash",
                    "step_temperature": {
                        "value": 2.0,
                        "unit": "C"
                    },
                    "step_time": {
                        "value": 3,
                        "unit": "day"
                    }
                }
            ]
        }
    }

    serializer = RecipeSerializer()
    async for session in get_db():
        recipe = await serializer.serialize(recipe_dict, session)
        session.add(recipe)
        await session.commit()

        # Reload with fermentation steps
        await session.refresh(recipe, ['fermentation_steps'])

        assert len(recipe.fermentation_steps) == 2

        step1 = recipe.fermentation_steps[0]
        assert step1.type == "primary"  # Derived from name
        assert step1.temp_c == pytest.approx(18.0)
        assert step1.time_days == 14
        assert step1.step_number == 1

        step2 = recipe.fermentation_steps[1]
        assert step2.temp_c == pytest.approx(2.0)
        assert step2.time_days == 3
        assert step2.step_number == 2

        await session.close()
        break
