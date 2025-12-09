"""Tests for BrewSignal Recipe Format v1.0 validation and conversion."""
import pytest
from pydantic import ValidationError
from backend.services.brewsignal_format import (
    BrewSignalRecipe,
    BeerJSONToBrewSignalConverter,
    BrewSignalToBeerJSONConverter,
)


# ==============================================================================
# Pydantic Validation Tests
# ==============================================================================

def test_minimal_valid_recipe():
    """Minimal recipe with only required fields validates."""
    recipe = BrewSignalRecipe(
        name="Test IPA",
        og=1.050,
        fg=1.010
    )
    assert recipe.name == "Test IPA"
    assert recipe.og == 1.050
    assert recipe.fg == 1.010


def test_missing_required_field():
    """Missing required field raises ValidationError."""
    with pytest.raises(ValidationError) as exc_info:
        BrewSignalRecipe(name="Test", og=1.050)
    assert "fg" in str(exc_info.value)


def test_og_out_of_range():
    """OG above 1.200 fails validation."""
    with pytest.raises(ValidationError):
        BrewSignalRecipe(name="Test", og=1.5, fg=1.010)


def test_fg_greater_than_og():
    """FG >= OG fails custom validator."""
    with pytest.raises(ValidationError) as exc_info:
        BrewSignalRecipe(name="Test", og=1.050, fg=1.055)
    assert "FG must be less than OG" in str(exc_info.value)


def test_exclude_none_fields():
    """None fields are excluded from dict export."""
    recipe = BrewSignalRecipe(name="Test", og=1.050, fg=1.010, abv=None)
    d = recipe.model_dump(exclude_none=True)
    assert "abv" not in d
    assert "name" in d


def test_complete_recipe_validates():
    """Complete recipe with all optional fields validates."""
    recipe = BrewSignalRecipe(
        name="West Coast IPA",
        author="Brewer Name",
        type="All Grain",
        style_id="bjcp-2021-21a",
        og=1.065,
        fg=1.012,
        abv=6.9,
        ibu=65.0,
        color_srm=7.0,
        batch_size_liters=19.0,
        boil_time_minutes=60,
        efficiency_percent=75.0,
        carbonation_vols=2.5,
        notes="Test notes"
    )
    assert recipe.name == "West Coast IPA"
    assert recipe.abv == 6.9


# ==============================================================================
# BeerJSON → BrewSignal Conversion Tests
# ==============================================================================

def test_convert_minimal_beerjson():
    """Convert minimal BeerJSON recipe."""
    beerjson = {
        "beerjson": {
            "version": 1.0,
            "recipes": [{
                "name": "Test IPA",
                "original_gravity": {"value": 1.065, "unit": "sg"},
                "final_gravity": {"value": 1.012, "unit": "sg"}
            }]
        }
    }

    converter = BeerJSONToBrewSignalConverter()
    result = converter.convert(beerjson)

    assert result["brewsignal_version"] == "1.0"
    assert result["recipe"]["name"] == "Test IPA"
    assert result["recipe"]["og"] == 1.065
    assert result["recipe"]["fg"] == 1.012


def test_convert_volume_units():
    """Volume conversions (gallons to liters)."""
    beerjson = {
        "beerjson": {
            "version": 1.0,
            "recipes": [{
                "name": "Test",
                "original_gravity": {"value": 1.050, "unit": "sg"},
                "final_gravity": {"value": 1.010, "unit": "sg"},
                "batch_size": {"value": 5, "unit": "gal"}
            }]
        }
    }

    converter = BeerJSONToBrewSignalConverter()
    result = converter.convert(beerjson)

    # 5 gallons ≈ 18.927 liters
    assert abs(result["recipe"]["batch_size_liters"] - 18.927) < 0.01


def test_convert_percent_units():
    """Percentage conversion (BeerJSON 0-1 to BrewSignal 0-100)."""
    beerjson = {
        "beerjson": {
            "version": 1.0,
            "recipes": [{
                "name": "Test",
                "original_gravity": {"value": 1.050, "unit": "sg"},
                "final_gravity": {"value": 1.010, "unit": "sg"},
                "alcohol_by_volume": {"value": 0.069, "unit": "%"},  # 0-1 scale
                "efficiency": {
                    "brewhouse": {"value": 0.75, "unit": "%"}  # 0-1 scale
                }
            }]
        }
    }

    converter = BeerJSONToBrewSignalConverter()
    result = converter.convert(beerjson)

    assert abs(result["recipe"]["abv"] - 6.9) < 0.01
    assert abs(result["recipe"]["efficiency_percent"] - 75.0) < 0.01


def test_reject_fahrenheit_temperature():
    """Non-Celsius temperatures raise ValueError."""
    beerjson = {
        "beerjson": {
            "version": 1.0,
            "recipes": [{
                "name": "Test",
                "original_gravity": {"value": 1.050, "unit": "sg"},
                "final_gravity": {"value": 1.010, "unit": "sg"},
                "ingredients": {
                    "culture_additions": [{
                        "name": "US-05",
                        "temperature_range": {
                            "minimum": {"value": 60, "unit": "F"}  # Fahrenheit!
                        }
                    }]
                }
            }]
        }
    }

    converter = BeerJSONToBrewSignalConverter()

    with pytest.raises(ValueError) as exc_info:
        converter.convert(beerjson)

    assert "Celsius" in str(exc_info.value)
    assert "F" in str(exc_info.value)


def test_multi_yeast_takes_first():
    """Multiple yeast cultures - take first, ignore rest."""
    beerjson = {
        "beerjson": {
            "version": 1.0,
            "recipes": [{
                "name": "Test",
                "original_gravity": {"value": 1.050, "unit": "sg"},
                "final_gravity": {"value": 1.010, "unit": "sg"},
                "ingredients": {
                    "culture_additions": [
                        {"name": "US-05", "type": "ale"},
                        {"name": "WLP001", "type": "ale"}  # Ignored
                    ]
                }
            }]
        }
    }

    converter = BeerJSONToBrewSignalConverter()
    result = converter.convert(beerjson)

    assert result["recipe"]["yeast"]["name"] == "US-05"
    # Second culture is dropped (documented limitation)


def test_convert_fermentables():
    """Convert fermentable additions."""
    beerjson = {
        "beerjson": {
            "version": 1.0,
            "recipes": [{
                "name": "Test",
                "original_gravity": {"value": 1.050, "unit": "sg"},
                "final_gravity": {"value": 1.010, "unit": "sg"},
                "ingredients": {
                    "fermentable_additions": [{
                        "name": "Pale Malt",
                        "type": "grain",
                        "amount": {"value": 5.0, "unit": "kg"},
                        "color": {"value": 2.0, "unit": "SRM"},
                        "yield": {
                            "fine_grind": {"value": 0.80, "unit": "%"}
                        }
                    }]
                }
            }]
        }
    }

    converter = BeerJSONToBrewSignalConverter()
    result = converter.convert(beerjson)

    ferm = result["recipe"]["fermentables"][0]
    assert ferm["name"] == "Pale Malt"
    assert ferm["type"] == "grain"
    assert ferm["amount_kg"] == 5.0
    assert ferm["color_srm"] == 2.0
    assert abs(ferm["yield_percent"] - 80.0) < 0.01


def test_convert_hops():
    """Convert hop additions."""
    beerjson = {
        "beerjson": {
            "version": 1.0,
            "recipes": [{
                "name": "Test",
                "original_gravity": {"value": 1.050, "unit": "sg"},
                "final_gravity": {"value": 1.010, "unit": "sg"},
                "ingredients": {
                    "hop_additions": [{
                        "name": "Cascade",
                        "origin": "United States",
                        "form": "pellet",
                        "amount": {"value": 30.0, "unit": "g"},
                        "alpha_acid": {"value": 0.055, "unit": "%"},
                        "timing": {
                            "use": "add_to_boil",
                            "duration": {"value": 60, "unit": "min"}
                        }
                    }]
                }
            }]
        }
    }

    converter = BeerJSONToBrewSignalConverter()
    result = converter.convert(beerjson)

    hop = result["recipe"]["hops"][0]
    assert hop["name"] == "Cascade"
    assert hop["form"] == "pellet"
    assert hop["amount_grams"] == 30.0
    assert abs(hop["alpha_acid_percent"] - 5.5) < 0.01
    assert hop["timing"]["use"] == "add_to_boil"


# ==============================================================================
# BrewSignal → BeerJSON Conversion Tests
# ==============================================================================

def test_convert_brewsignal_to_beerjson():
    """Convert BrewSignal recipe to BeerJSON."""
    brewsignal = {
        "brewsignal_version": "1.0",
        "recipe": {
            "name": "Test IPA",
            "og": 1.065,
            "fg": 1.012,
            "abv": 6.9,
            "batch_size_liters": 19.0
        }
    }

    converter = BrewSignalToBeerJSONConverter()
    result = converter.convert(brewsignal)

    assert result["beerjson"]["version"] == 1.0
    assert result["beerjson"]["recipes"][0]["name"] == "Test IPA"
    assert result["beerjson"]["recipes"][0]["original_gravity"]["value"] == 1.065
    assert result["beerjson"]["recipes"][0]["original_gravity"]["unit"] == "sg"
    assert result["beerjson"]["recipes"][0]["final_gravity"]["value"] == 1.012


def test_wrap_percentages():
    """Percentage conversion (BrewSignal 0-100 to BeerJSON 0-1)."""
    brewsignal = {
        "brewsignal_version": "1.0",
        "recipe": {
            "name": "Test",
            "og": 1.050,
            "fg": 1.010,
            "abv": 6.9,  # 0-100 scale
            "efficiency_percent": 75.0  # 0-100 scale
        }
    }

    converter = BrewSignalToBeerJSONConverter()
    result = converter.convert(brewsignal)

    abv = result["beerjson"]["recipes"][0]["alcohol_by_volume"]
    assert abs(abv["value"] - 0.069) < 0.001  # 0-1 scale
    assert abv["unit"] == "%"

    eff = result["beerjson"]["recipes"][0]["efficiency"]["brewhouse"]
    assert abs(eff["value"] - 0.75) < 0.001  # 0-1 scale


def test_wrap_fermentables():
    """Convert BrewSignal fermentables to BeerJSON."""
    brewsignal = {
        "brewsignal_version": "1.0",
        "recipe": {
            "name": "Test",
            "og": 1.050,
            "fg": 1.010,
            "fermentables": [{
                "name": "Pale Malt",
                "type": "grain",
                "amount_kg": 5.0,
                "yield_percent": 80.0,
                "color_srm": 2.0
            }]
        }
    }

    converter = BrewSignalToBeerJSONConverter()
    result = converter.convert(brewsignal)

    ferm = result["beerjson"]["recipes"][0]["ingredients"]["fermentable_additions"][0]
    assert ferm["name"] == "Pale Malt"
    assert ferm["amount"]["value"] == 5.0
    assert ferm["amount"]["unit"] == "kg"
    assert abs(ferm["yield"]["fine_grind"]["value"] - 0.80) < 0.001


def test_wrap_hops():
    """Convert BrewSignal hops to BeerJSON."""
    brewsignal = {
        "brewsignal_version": "1.0",
        "recipe": {
            "name": "Test",
            "og": 1.050,
            "fg": 1.010,
            "hops": [{
                "name": "Cascade",
                "origin": "United States",
                "form": "pellet",
                "amount_grams": 30.0,
                "alpha_acid_percent": 5.5,
                "timing": {
                    "use": "add_to_boil",
                    "duration": {"value": 60, "unit": "min"}
                }
            }]
        }
    }

    converter = BrewSignalToBeerJSONConverter()
    result = converter.convert(brewsignal)

    hop = result["beerjson"]["recipes"][0]["ingredients"]["hop_additions"][0]
    assert hop["name"] == "Cascade"
    assert hop["amount"]["value"] == 30.0
    assert hop["amount"]["unit"] == "g"
    assert abs(hop["alpha_acid"]["value"] - 0.055) < 0.001


def test_wrap_yeast():
    """Convert BrewSignal yeast to BeerJSON culture."""
    brewsignal = {
        "brewsignal_version": "1.0",
        "recipe": {
            "name": "Test",
            "og": 1.050,
            "fg": 1.010,
            "yeast": {
                "name": "US-05",
                "producer": "Fermentis",
                "type": "ale",
                "form": "dry",
                "attenuation_percent": 81.0,
                "temp_min_c": 15.0,
                "temp_max_c": 24.0
            }
        }
    }

    converter = BrewSignalToBeerJSONConverter()
    result = converter.convert(brewsignal)

    culture = result["beerjson"]["recipes"][0]["ingredients"]["culture_additions"][0]
    assert culture["name"] == "US-05"
    assert culture["producer"] == "Fermentis"
    assert culture["temperature_range"]["minimum"]["value"] == 15.0
    assert culture["temperature_range"]["minimum"]["unit"] == "C"
    assert culture["temperature_range"]["maximum"]["value"] == 24.0
    assert abs(culture["attenuation_range"]["minimum"]["value"] - 0.81) < 0.001


# ==============================================================================
# Round-Trip Conversion Tests
# ==============================================================================

def test_roundtrip_beerjson_brewsignal_beerjson():
    """Round-trip: BeerJSON → BrewSignal → BeerJSON."""
    original = {
        "beerjson": {
            "version": 1.0,
            "recipes": [{
                "name": "Test IPA",
                "type": "all grain",
                "author": "Brewer",
                "original_gravity": {"value": 1.065, "unit": "sg"},
                "final_gravity": {"value": 1.012, "unit": "sg"},
                "alcohol_by_volume": {"value": 0.069, "unit": "%"},
                "ibu_estimate": {"value": 65.0, "unit": "1"},
                "color_estimate": {"value": 7.0, "unit": "SRM"},
                "batch_size": {"value": 19.0, "unit": "l"},
                "carbonation": 2.5,
            }]
        }
    }

    # Convert to BrewSignal
    to_bs = BeerJSONToBrewSignalConverter()
    brewsignal = to_bs.convert(original)

    # Convert back to BeerJSON
    to_bj = BrewSignalToBeerJSONConverter()
    result = to_bj.convert(brewsignal)

    # Compare key fields
    orig_recipe = original["beerjson"]["recipes"][0]
    result_recipe = result["beerjson"]["recipes"][0]

    assert result_recipe["name"] == orig_recipe["name"]
    assert result_recipe["original_gravity"]["value"] == orig_recipe["original_gravity"]["value"]
    assert result_recipe["final_gravity"]["value"] == orig_recipe["final_gravity"]["value"]
    assert abs(result_recipe["alcohol_by_volume"]["value"] - orig_recipe["alcohol_by_volume"]["value"]) < 0.001
    assert result_recipe["carbonation"] == orig_recipe["carbonation"]


def test_roundtrip_brewsignal_beerjson_brewsignal():
    """Round-trip: BrewSignal → BeerJSON → BrewSignal."""
    original = {
        "brewsignal_version": "1.0",
        "recipe": {
            "name": "Test IPA",
            "author": "Brewer",
            "type": "All Grain",
            "og": 1.065,
            "fg": 1.012,
            "abv": 6.9,
            "ibu": 65.0,
            "color_srm": 7.0,
            "batch_size_liters": 19.0,
            "carbonation_vols": 2.5
        }
    }

    # Convert to BeerJSON
    to_bj = BrewSignalToBeerJSONConverter()
    beerjson = to_bj.convert(original)

    # Convert back to BrewSignal
    to_bs = BeerJSONToBrewSignalConverter()
    result = to_bs.convert(beerjson)

    # Compare key fields
    orig_recipe = original["recipe"]
    result_recipe = result["recipe"]

    assert result_recipe["name"] == orig_recipe["name"]
    assert result_recipe["og"] == orig_recipe["og"]
    assert result_recipe["fg"] == orig_recipe["fg"]
    assert abs(result_recipe["abv"] - orig_recipe["abv"]) < 0.01
    assert result_recipe["ibu"] == orig_recipe["ibu"]
    assert result_recipe["color_srm"] == orig_recipe["color_srm"]
    assert result_recipe["batch_size_liters"] == orig_recipe["batch_size_liters"]
    assert result_recipe["carbonation_vols"] == orig_recipe["carbonation_vols"]


# ==============================================================================
# Fixtures
# ==============================================================================

@pytest.fixture
def full_beerjson_example():
    """Complete BeerJSON example for testing."""
    return {
        "beerjson": {
            "version": 1.0,
            "recipes": [{
                "name": "West Coast IPA",
                "type": "all grain",
                "author": "John Brewer",
                "original_gravity": {"value": 1.065, "unit": "sg"},
                "final_gravity": {"value": 1.012, "unit": "sg"},
                "alcohol_by_volume": {"value": 0.069, "unit": "%"},
                "ibu_estimate": {"value": 65.0, "unit": "1"},
                "color_estimate": {"value": 7.0, "unit": "SRM"},
                "batch_size": {"value": 19.0, "unit": "l"},
                "boil": {
                    "boil_time": {"value": 60, "unit": "min"}
                },
                "efficiency": {
                    "brewhouse": {"value": 0.75, "unit": "%"}
                },
                "carbonation": 2.5,
                "ingredients": {
                    "fermentable_additions": [{
                        "name": "2-Row Pale Malt",
                        "type": "grain",
                        "amount": {"value": 5.4, "unit": "kg"},
                        "color": {"value": 2.0, "unit": "SRM"},
                        "yield": {
                            "fine_grind": {"value": 0.80, "unit": "%"}
                        }
                    }],
                    "hop_additions": [{
                        "name": "Cascade",
                        "origin": "United States",
                        "form": "pellet",
                        "amount": {"value": 30.0, "unit": "g"},
                        "alpha_acid": {"value": 0.055, "unit": "%"},
                        "timing": {
                            "use": "add_to_boil",
                            "duration": {"value": 60, "unit": "min"}
                        }
                    }],
                    "culture_additions": [{
                        "name": "US-05",
                        "producer": "Fermentis",
                        "type": "ale",
                        "form": "dry",
                        "temperature_range": {
                            "minimum": {"value": 15.0, "unit": "C"},
                            "maximum": {"value": 24.0, "unit": "C"}
                        },
                        "attenuation_range": {
                            "minimum": {"value": 0.81, "unit": "%"},
                            "maximum": {"value": 0.81, "unit": "%"}
                        }
                    }]
                }
            }]
        }
    }
