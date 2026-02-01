"""Test Pydantic response models for mash, fermentation, and water data."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.models import (
    MashStepResponse,
    FermentationStepResponse,
    WaterProfileResponse,
    WaterAdjustmentResponse,
    RecipeDetailResponse,
    Recipe,
    RecipeMashStep,
    RecipeFermentationStep,
)


def test_mash_step_response_model():
    """Test MashStepResponse can be created with valid data."""
    data = {
        "id": 1,
        "step_number": 1,
        "name": "Mash",
        "type": "temperature",
        "temp_c": 65.0,
        "time_minutes": 60,
        "ramp_time_minutes": None,
    }
    response = MashStepResponse(**data)
    assert response.name == "Mash"
    assert response.temp_c == 65.0
    assert response.time_minutes == 60


def test_fermentation_step_response_model():
    """Test FermentationStepResponse can be created with valid data."""
    data = {
        "id": 1,
        "step_number": 1,
        "type": "primary",
        "temp_c": 19.0,
        "time_days": 14,
    }
    response = FermentationStepResponse(**data)
    assert response.type == "primary"
    assert response.temp_c == 19.0
    assert response.time_days == 14


def test_water_profile_response_model():
    """Test WaterProfileResponse can be created with valid data."""
    data = {
        "id": 1,
        "profile_type": "source",
        "name": "Reverse Osmosis",
        "calcium_ppm": 1.0,
        "magnesium_ppm": 0.0,
        "sodium_ppm": 8.0,
        "chloride_ppm": 4.0,
        "sulfate_ppm": 1.0,
        "bicarbonate_ppm": 16.0,
        "ph": 7.0,
    }
    response = WaterProfileResponse(**data)
    assert response.profile_type == "source"
    assert response.calcium_ppm == 1.0


def test_water_adjustment_response_model():
    """Test WaterAdjustmentResponse can be created with valid data."""
    data = {
        "id": 1,
        "stage": "mash",
        "volume_liters": 13.29,
        "calcium_sulfate_g": 1.5,
        "calcium_chloride_g": 1.7,
        "acid_type": "lactic",
        "acid_ml": 1.0,
    }
    response = WaterAdjustmentResponse(**data)
    assert response.stage == "mash"
    assert response.calcium_sulfate_g == 1.5


def test_recipe_detail_response_includes_mash_steps():
    """Test RecipeDetailResponse has mash_steps field."""
    data = {
        "id": 1,
        "name": "Test Recipe",
        "created_at": "2026-02-01T00:00:00Z",
        "mash_steps": [
            {"id": 1, "step_number": 1, "name": "Mash", "type": "temperature", "temp_c": 65.0, "time_minutes": 60}
        ],
        "fermentation_steps": [],
        "water_profiles": [],
        "water_adjustments": [],
        "fermentables": [],
        "hops": [],
        "cultures": [],
        "miscs": [],
    }
    response = RecipeDetailResponse(**data)
    assert len(response.mash_steps) == 1
    assert response.mash_steps[0].name == "Mash"


def test_recipe_detail_response_includes_all_water_fields():
    """Test RecipeDetailResponse has all new water-related fields."""
    data = {
        "id": 1,
        "name": "Test Recipe",
        "created_at": "2026-02-01T00:00:00Z",
        "mash_steps": [],
        "fermentation_steps": [
            {"id": 1, "step_number": 1, "type": "primary", "temp_c": 19.0, "time_days": 14}
        ],
        "water_profiles": [
            {"id": 1, "profile_type": "source", "calcium_ppm": 1.0}
        ],
        "water_adjustments": [
            {"id": 1, "stage": "mash", "calcium_sulfate_g": 1.5}
        ],
        "fermentables": [],
        "hops": [],
        "cultures": [],
        "miscs": [],
    }
    response = RecipeDetailResponse(**data)
    assert len(response.fermentation_steps) == 1
    assert len(response.water_profiles) == 1
    assert len(response.water_adjustments) == 1


@pytest.mark.asyncio
async def test_recipe_loads_mash_and_fermentation_steps(test_db: AsyncSession):
    """Test that recipe can load mash and fermentation steps via selectinload."""
    # Create a recipe with mash and fermentation steps
    recipe = Recipe(name="Test Mash Recipe", author="Test")
    test_db.add(recipe)
    await test_db.commit()
    await test_db.refresh(recipe)

    # Add mash steps
    mash_step = RecipeMashStep(
        recipe_id=recipe.id,
        step_number=1,
        name="Mash",
        type="temperature",
        temp_c=65.0,
        time_minutes=60,
    )
    test_db.add(mash_step)

    # Add fermentation step
    ferm_step = RecipeFermentationStep(
        recipe_id=recipe.id,
        step_number=1,
        type="primary",
        temp_c=19.0,
        time_days=14,
    )
    test_db.add(ferm_step)
    await test_db.commit()

    # Fetch with selectinload (all relationships needed for RecipeDetailResponse)
    result = await test_db.execute(
        select(Recipe)
        .where(Recipe.id == recipe.id)
        .options(
            selectinload(Recipe.mash_steps),
            selectinload(Recipe.fermentation_steps),
            selectinload(Recipe.water_profiles),
            selectinload(Recipe.water_adjustments),
            selectinload(Recipe.fermentables),
            selectinload(Recipe.hops),
            selectinload(Recipe.cultures),
            selectinload(Recipe.miscs),
        )
    )
    loaded = result.scalar_one()

    assert len(loaded.mash_steps) == 1
    assert loaded.mash_steps[0].name == "Mash"
    assert len(loaded.fermentation_steps) == 1
    assert loaded.fermentation_steps[0].type == "primary"

    # Verify Pydantic model works
    response = RecipeDetailResponse.model_validate(loaded)
    assert len(response.mash_steps) == 1
    assert len(response.fermentation_steps) == 1
