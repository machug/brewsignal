"""Tests for water profile extraction from Brewfather JSON import."""
import pytest
from pathlib import Path

from backend.services.importers.recipe_importer import RecipeImporter


@pytest.mark.asyncio
async def test_brewfather_water_profiles_extracted(test_db):
    """Test that water profiles are extracted from Brewfather JSON."""
    # Load actual Brewfather test file
    test_file = Path("docs/Brewfather_RECIPE_PhilterXPAClone_20251207.json")
    with open(test_file, "r") as f:
        content = f.read()

    # Import recipe
    importer = RecipeImporter()
    result = await importer.import_recipe(content, "brewfather", test_db)

    # Verify success
    assert result.success is True
    assert result.recipe is not None

    # Verify water profiles were created
    assert len(result.recipe.water_profiles) >= 1

    # Find and verify source profile
    source_profiles = [p for p in result.recipe.water_profiles if p.profile_type == 'source']
    assert len(source_profiles) == 1
    source = source_profiles[0]
    assert source.name == "Shearwater"
    assert source.calcium_ppm == pytest.approx(9.98, rel=0.01)
    assert source.magnesium_ppm == pytest.approx(0.860, rel=0.01)
    assert source.sodium_ppm == pytest.approx(3.026, rel=0.01)
    assert source.chloride_ppm == pytest.approx(6.53, rel=0.01)
    assert source.sulfate_ppm == pytest.approx(14.58, rel=0.01)
    assert source.bicarbonate_ppm == pytest.approx(11.4243, rel=0.01)
    assert source.ph == pytest.approx(6.3, rel=0.01)

    # Find and verify target profile
    target_profiles = [p for p in result.recipe.water_profiles if p.profile_type == 'target']
    assert len(target_profiles) == 1
    target = target_profiles[0]
    assert target.calcium_ppm == pytest.approx(110, rel=0.01)
    assert target.chloride_ppm == pytest.approx(50, rel=0.01)

    # Find and verify mash profile
    mash_profiles = [p for p in result.recipe.water_profiles if p.profile_type == 'mash']
    assert len(mash_profiles) == 1
    mash = mash_profiles[0]
    assert mash.calcium_ppm == pytest.approx(113.094, rel=0.01)
    assert mash.magnesium_ppm == pytest.approx(18.412, rel=0.01)

    # Find and verify sparge profile
    sparge_profiles = [p for p in result.recipe.water_profiles if p.profile_type == 'sparge']
    assert len(sparge_profiles) == 1
    sparge = sparge_profiles[0]
    assert sparge.calcium_ppm == pytest.approx(112.979, rel=0.01)


@pytest.mark.asyncio
async def test_brewfather_water_profiles_minimal_json(test_db):
    """Test water profile extraction from minimal Brewfather JSON."""
    bf_json = '''{
        "name": "Test Recipe",
        "type": "All Grain",
        "batchSize": 20,
        "boilTime": 60,
        "equipment": {"efficiency": 75},
        "fermentables": [{"name": "Pale Malt", "amount": 5}],
        "water": {
            "source": {
                "name": "Melbourne",
                "calcium": 10,
                "magnesium": 2,
                "sodium": 5,
                "chloride": 10,
                "sulfate": 5,
                "bicarbonate": 20,
                "ph": 7.0
            },
            "target": {
                "name": "Balanced",
                "calcium": 80,
                "magnesium": 5,
                "sodium": 10,
                "chloride": 50,
                "sulfate": 80,
                "bicarbonate": 50
            },
            "mash": {
                "calcium": 61,
                "magnesium": 4,
                "sodium": 8,
                "chloride": 35,
                "sulfate": 55,
                "bicarbonate": 30
            },
            "sparge": {
                "calcium": 61,
                "magnesium": 4,
                "sodium": 8,
                "chloride": 35,
                "sulfate": 55,
                "bicarbonate": 30
            }
        }
    }'''

    # Import recipe
    importer = RecipeImporter()
    result = await importer.import_recipe(bf_json, 'brewfather', test_db)

    # Verify success
    assert result.success is True
    assert result.recipe is not None
    assert len(result.recipe.water_profiles) == 4

    # Verify source profile
    source = next(p for p in result.recipe.water_profiles if p.profile_type == 'source')
    assert source.name == "Melbourne"
    assert source.calcium_ppm == 10
    assert source.ph == 7.0

    # Verify target profile
    target = next(p for p in result.recipe.water_profiles if p.profile_type == 'target')
    assert target.name == "Balanced"
    assert target.calcium_ppm == 80
    assert target.sulfate_ppm == 80

    # Verify mash profile
    mash = next(p for p in result.recipe.water_profiles if p.profile_type == 'mash')
    assert mash.calcium_ppm == 61

    # Verify sparge profile
    sparge = next(p for p in result.recipe.water_profiles if p.profile_type == 'sparge')
    assert sparge.calcium_ppm == 61


@pytest.mark.asyncio
async def test_brewfather_no_water_data(test_db):
    """Test that import succeeds even without water data."""
    bf_json = '''{
        "name": "Simple Recipe",
        "type": "All Grain",
        "batchSize": 20,
        "boilTime": 60,
        "equipment": {"efficiency": 75},
        "fermentables": [{"name": "Pale Malt", "amount": 5}]
    }'''

    # Import recipe
    importer = RecipeImporter()
    result = await importer.import_recipe(bf_json, 'brewfather', test_db)

    # Verify success
    assert result.success is True
    assert result.recipe is not None
    # Water profiles are added to the recipe object during serialization,
    # but since there's no water data, the list should be empty.
    # Check the in-memory list before DB flush to avoid lazy loading issues.
    # The water_profiles list was populated during serialization (before flush),
    # so it should be empty if no water data was in the source.
    await test_db.refresh(result.recipe, ['water_profiles'])
    assert len(result.recipe.water_profiles) == 0


@pytest.mark.asyncio
async def test_brewfather_partial_water_data(test_db):
    """Test that partial water data is handled gracefully."""
    bf_json = '''{
        "name": "Partial Water Recipe",
        "type": "All Grain",
        "batchSize": 20,
        "boilTime": 60,
        "equipment": {"efficiency": 75},
        "fermentables": [{"name": "Pale Malt", "amount": 5}],
        "water": {
            "source": {
                "name": "Tap Water",
                "calcium": 50
            }
        }
    }'''

    # Import recipe
    importer = RecipeImporter()
    result = await importer.import_recipe(bf_json, 'brewfather', test_db)

    # Verify success
    assert result.success is True
    assert result.recipe is not None

    # Only source profile should be created
    assert len(result.recipe.water_profiles) == 1
    source = result.recipe.water_profiles[0]
    assert source.profile_type == 'source'
    assert source.name == "Tap Water"
    assert source.calcium_ppm == 50
    # Other fields should be None
    assert source.magnesium_ppm is None
    assert source.sodium_ppm is None


@pytest.mark.asyncio
async def test_brewfather_water_adjustments_extracted(test_db):
    """Test that water adjustments are extracted from Brewfather JSON."""
    bf_json = '''{
        "name": "Water Adjustments Recipe",
        "type": "All Grain",
        "batchSize": 20,
        "boilTime": 60,
        "equipment": {"efficiency": 75},
        "fermentables": [{"name": "Pale Malt", "amount": 5}],
        "water": {
            "mashAdjustments": {
                "calciumChloride": 1.7,
                "calciumSulfate": 1.5,
                "magnesiumSulfate": 2.2,
                "sodiumBicarbonate": 3.0,
                "sodiumChloride": 0.4,
                "volume": 13.29,
                "acids": [{"type": "lactic", "amount": 1.0, "concentration": 88}]
            },
            "spargeAdjustments": {
                "calciumChloride": 1.89,
                "calciumSulfate": 1.66,
                "magnesiumSulfate": 2.44,
                "sodiumChloride": 0.44,
                "volume": 14.75
            }
        }
    }'''

    # Import recipe
    importer = RecipeImporter()
    result = await importer.import_recipe(bf_json, 'brewfather', test_db)

    # Verify success
    assert result.success is True
    assert result.recipe is not None

    # Verify water adjustments were created
    assert len(result.recipe.water_adjustments) == 2

    # Find and verify mash adjustment
    mash_adj = next(a for a in result.recipe.water_adjustments if a.stage == 'mash')
    assert mash_adj.volume_liters == pytest.approx(13.29, rel=0.01)
    assert mash_adj.calcium_chloride_g == pytest.approx(1.7, rel=0.01)
    assert mash_adj.calcium_sulfate_g == pytest.approx(1.5, rel=0.01)
    assert mash_adj.magnesium_sulfate_g == pytest.approx(2.2, rel=0.01)
    assert mash_adj.sodium_bicarbonate_g == pytest.approx(3.0, rel=0.01)
    assert mash_adj.sodium_chloride_g == pytest.approx(0.4, rel=0.01)
    assert mash_adj.acid_type == 'lactic'
    assert mash_adj.acid_ml == pytest.approx(1.0, rel=0.01)
    assert mash_adj.acid_concentration_percent == pytest.approx(88, rel=0.01)

    # Find and verify sparge adjustment
    sparge_adj = next(a for a in result.recipe.water_adjustments if a.stage == 'sparge')
    assert sparge_adj.volume_liters == pytest.approx(14.75, rel=0.01)
    assert sparge_adj.calcium_chloride_g == pytest.approx(1.89, rel=0.01)
    assert sparge_adj.calcium_sulfate_g == pytest.approx(1.66, rel=0.01)
    assert sparge_adj.magnesium_sulfate_g == pytest.approx(2.44, rel=0.01)
    assert sparge_adj.sodium_chloride_g == pytest.approx(0.44, rel=0.01)
    # No acid for sparge in this test
    assert sparge_adj.acid_type is None


@pytest.mark.asyncio
async def test_brewfather_water_adjustments_from_real_file(test_db):
    """Test that water adjustments are extracted from actual Brewfather test file."""
    # Load actual Brewfather test file
    test_file = Path("docs/Brewfather_RECIPE_PhilterXPAClone_20251207.json")
    with open(test_file, "r") as f:
        content = f.read()

    # Import recipe
    importer = RecipeImporter()
    result = await importer.import_recipe(content, "brewfather", test_db)

    # Verify success
    assert result.success is True
    assert result.recipe is not None

    # Verify water adjustments were created
    assert len(result.recipe.water_adjustments) >= 2

    # Find and verify mash adjustment
    mash_adj = next(a for a in result.recipe.water_adjustments if a.stage == 'mash')
    assert mash_adj.volume_liters == pytest.approx(13.37, rel=0.01)
    assert mash_adj.calcium_chloride_g == pytest.approx(1.24, rel=0.01)
    assert mash_adj.calcium_sulfate_g == pytest.approx(4.47, rel=0.01)
    assert mash_adj.magnesium_sulfate_g == pytest.approx(2.38, rel=0.01)
    # Acid amount is 0 in this file
    assert mash_adj.acid_type == 'lactic'
    assert mash_adj.acid_ml == 0

    # Find and verify sparge adjustment
    sparge_adj = next(a for a in result.recipe.water_adjustments if a.stage == 'sparge')
    assert sparge_adj.volume_liters == pytest.approx(15.47, rel=0.01)
    assert sparge_adj.calcium_chloride_g == pytest.approx(1.43, rel=0.01)
    assert sparge_adj.calcium_sulfate_g == pytest.approx(5.17, rel=0.01)
    assert sparge_adj.magnesium_sulfate_g == pytest.approx(2.75, rel=0.01)
