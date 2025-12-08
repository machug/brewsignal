"""Test BeerJSON validator using jsonschema."""
import pytest
import json
from backend.services.validators.beerjson_validator import BeerJSONValidator


def test_validate_brewfather_beerjson_output():
    """Test validating converted Brewfather BeerJSON against BeerJSON 1.0 schema.

    After fixes in Task 7, the Brewfather converter now produces spec-compliant
    BeerJSON output that passes validation.
    """
    # Load the converted BeerJSON from Task 6 (fixed in Task 7)
    with open("docs/Brewfather_to_BeerJSON_output.json", "r") as f:
        beerjson_data = json.load(f)

    validator = BeerJSONValidator()

    # Validate against BeerJSON 1.0 schema
    is_valid, errors = validator.validate(beerjson_data)

    # After fixes in Task 7, output should be fully spec-compliant
    if not is_valid:
        print(f"Validation errors: {errors}")
    assert is_valid is True
    assert errors == []


def test_validate_invalid_beerjson_missing_version():
    """Test that validator catches missing version field."""
    invalid_data = {
        "beerjson": {
            "recipes": []
        }
    }

    validator = BeerJSONValidator()
    is_valid, errors = validator.validate(invalid_data)

    assert is_valid is False
    assert len(errors) > 0
    assert any("version" in str(error).lower() for error in errors)


def test_validate_invalid_beerjson_wrong_version():
    """Test that validator catches invalid version type (string instead of number)."""
    invalid_data = {
        "beerjson": {
            "version": "2.0",  # Should be number, not string
            "recipes": []
        }
    }

    validator = BeerJSONValidator()
    is_valid, errors = validator.validate(invalid_data)

    assert is_valid is False
    assert len(errors) > 0
    assert any("version" in str(error).lower() or "type" in str(error).lower() for error in errors)


def test_validate_invalid_recipe_missing_name():
    """Test that validator catches missing recipe name."""
    invalid_data = {
        "beerjson": {
            "version": 1.0,  # Use number, not string
            "recipes": [
                {
                    "type": "All Grain"
                    # Missing required "name" field
                }
            ]
        }
    }

    validator = BeerJSONValidator()
    is_valid, errors = validator.validate(invalid_data)

    assert is_valid is False
    assert len(errors) > 0
    # Should fail due to missing required fields (name, author, efficiency, batch_size, ingredients)
    assert any("required" in str(error).lower() for error in errors)


def test_validate_invalid_unit_value():
    """Test that validator catches invalid unit values."""
    invalid_data = {
        "beerjson": {
            "version": "1.0",
            "recipes": [
                {
                    "name": "Test Recipe",
                    "type": "All Grain",
                    "batch_size": {
                        "value": 20.0,
                        "unit": "gallons"  # Invalid unit - should be "l"
                    }
                }
            ]
        }
    }

    validator = BeerJSONValidator()
    is_valid, errors = validator.validate(invalid_data)

    assert is_valid is False
    assert len(errors) > 0


def test_validate_valid_minimal_recipe():
    """Test validating a minimal valid BeerJSON recipe.

    BeerJSON schema requires: name, type, author, efficiency, batch_size, ingredients
    """
    valid_data = {
        "beerjson": {
            "version": 1.0,  # Number, not string
            "recipes": [
                {
                    "name": "Test Recipe",
                    "type": "all grain",
                    "author": "Test Author",
                    "efficiency": {
                        "brewhouse": {
                            "value": 0.75,
                            "unit": "%"
                        }
                    },
                    "batch_size": {
                        "value": 20.0,
                        "unit": "l"
                    },
                    "ingredients": {
                        "fermentable_additions": [
                            {
                                "name": "Pale Malt",
                                "type": "grain",
                                "origin": "US",
                                "amount": {
                                    "value": 5.0,
                                    "unit": "kg"
                                },
                                "yield": {
                                    "fine_grind": {
                                        "value": 0.80,
                                        "unit": "%"
                                    }
                                },
                                "color": {
                                    "value": 3.0,
                                    "unit": "Lovi"
                                }
                            }
                        ]
                    }
                }
            ]
        }
    }

    validator = BeerJSONValidator()
    is_valid, errors = validator.validate(valid_data)

    # Should pass validation
    if not is_valid:
        print(f"Validation errors: {errors}")
    assert is_valid is True
    assert errors == []


def test_schema_is_loaded():
    """Test that the BeerJSON schema is properly loaded."""
    validator = BeerJSONValidator()

    # Verify schema is loaded
    assert validator.schema is not None
    assert isinstance(validator.schema, dict)
    assert "$schema" in validator.schema or "type" in validator.schema
