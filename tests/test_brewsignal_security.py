"""Security-focused tests for BrewSignal Recipe Format v1.0.

This test suite focuses on identifying security vulnerabilities:
- Input validation bypass
- Type confusion attacks
- Injection risks
- Resource exhaustion (DoS)
- Data validation bypass
- JSON parsing vulnerabilities
"""
import pytest
from pydantic import ValidationError
from backend.services.brewsignal_format import (
    BrewSignalRecipe,
    BeerJSONToBrewSignalConverter,
    BrewSignalToBeerJSONConverter,
)


# ==============================================================================
# Input Validation Vulnerabilities
# ==============================================================================

class TestInputValidation:
    """Test input validation edge cases and bypass attempts."""

    def test_name_exceeds_max_length(self):
        """Recipe name exceeding max_length should be rejected."""
        long_name = "A" * 201  # max_length=200
        with pytest.raises(ValidationError) as exc_info:
            BrewSignalRecipe(name=long_name, og=1.050, fg=1.010)
        assert "at most 200" in str(exc_info.value).lower()

    def test_empty_name_rejected(self):
        """Empty name should be rejected (min_length=1)."""
        with pytest.raises(ValidationError):
            BrewSignalRecipe(name="", og=1.050, fg=1.010)

    def test_null_byte_in_name(self):
        """Null bytes in name should be handled safely."""
        name_with_null = "Test\x00Recipe"
        recipe = BrewSignalRecipe(name=name_with_null, og=1.050, fg=1.010)
        # Pydantic allows null bytes - application layer must sanitize
        assert "\x00" in recipe.name

    def test_unicode_injection_in_name(self):
        """Unicode control characters in name."""
        malicious_name = "Test\u202e\u0007Recipe"  # Right-to-left override, bell
        recipe = BrewSignalRecipe(name=malicious_name, og=1.050, fg=1.010)
        # Pydantic allows unicode - verify no code execution
        assert recipe.name == malicious_name

    def test_sql_injection_pattern_in_name(self):
        """SQL injection patterns should be safely stored as strings."""
        sql_name = "'; DROP TABLE recipes; --"
        recipe = BrewSignalRecipe(name=sql_name, og=1.050, fg=1.010)
        # Should be safely stored as literal string
        assert recipe.name == sql_name

    def test_xss_pattern_in_notes(self):
        """XSS patterns in notes should be safely stored."""
        xss_notes = "<script>alert('XSS')</script>"
        recipe = BrewSignalRecipe(
            name="Test",
            og=1.050,
            fg=1.010,
            notes=xss_notes
        )
        # Should be safely stored - frontend must escape on display
        assert recipe.notes == xss_notes

    def test_command_injection_pattern_in_author(self):
        """Command injection patterns should be safely stored."""
        cmd_author = "test; rm -rf /"
        recipe = BrewSignalRecipe(
            name="Test",
            author=cmd_author,
            og=1.050,
            fg=1.010
        )
        assert recipe.author == cmd_author

    def test_path_traversal_in_origin(self):
        """Path traversal patterns in ingredient origin."""
        from backend.services.brewsignal_format import BrewSignalFermentable
        ferm = BrewSignalFermentable(
            name="Malt",
            amount_kg=5.0,
            origin="../../../etc/passwd"
        )
        # Should be stored as literal string
        assert ferm.origin == "../../../etc/passwd"


# ==============================================================================
# Type Confusion Attacks
# ==============================================================================

class TestTypeConfusion:
    """Test type confusion and type coercion vulnerabilities."""

    def test_og_as_string_rejected(self):
        """OG must be float, not string (type coercion prevented)."""
        with pytest.raises(ValidationError):
            BrewSignalRecipe(name="Test", og="1.050", fg=1.010)

    def test_og_as_array_rejected(self):
        """OG must be float, not array."""
        with pytest.raises(ValidationError):
            BrewSignalRecipe(name="Test", og=[1.050], fg=1.010)

    def test_og_as_dict_rejected(self):
        """OG must be float, not dict."""
        with pytest.raises(ValidationError):
            BrewSignalRecipe(name="Test", og={"value": 1.050}, fg=1.010)

    def test_negative_gravity_rejected(self):
        """Negative gravity values should be rejected."""
        with pytest.raises(ValidationError):
            BrewSignalRecipe(name="Test", og=-1.050, fg=1.010)

    def test_infinity_gravity_rejected(self):
        """Infinity should be rejected."""
        with pytest.raises(ValidationError):
            BrewSignalRecipe(name="Test", og=float('inf'), fg=1.010)

    def test_nan_gravity_rejected(self):
        """NaN should be rejected."""
        with pytest.raises(ValidationError):
            BrewSignalRecipe(name="Test", og=float('nan'), fg=1.010)

    def test_negative_amount_rejected(self):
        """Negative ingredient amounts should be rejected."""
        from backend.services.brewsignal_format import BrewSignalFermentable
        with pytest.raises(ValidationError):
            BrewSignalFermentable(name="Malt", amount_kg=-5.0)

    def test_zero_amount_rejected(self):
        """Zero ingredient amounts should be rejected (gt=0)."""
        from backend.services.brewsignal_format import BrewSignalFermentable
        with pytest.raises(ValidationError):
            BrewSignalFermentable(name="Malt", amount_kg=0.0)

    def test_percentage_overflow(self):
        """Percentage above 100 should be rejected."""
        with pytest.raises(ValidationError):
            BrewSignalRecipe(name="Test", og=1.050, fg=1.010, abv=150.0)

    def test_alpha_acid_overflow(self):
        """Alpha acid above 25% should be rejected."""
        from backend.services.brewsignal_format import BrewSignalHop, BrewSignalTiming
        with pytest.raises(ValidationError):
            BrewSignalHop(
                name="Hop",
                amount_grams=30.0,
                alpha_acid_percent=99.0,  # Exceeds 25% max
                timing=BrewSignalTiming(use="add_to_boil")
            )


# ==============================================================================
# JSON Parsing Vulnerabilities
# ==============================================================================

class TestJSONParsing:
    """Test JSON parsing vulnerabilities and edge cases."""

    def test_extra_fields_rejected(self):
        """Unknown fields should be rejected (extra='forbid')."""
        with pytest.raises(ValidationError) as exc_info:
            BrewSignalRecipe(
                name="Test",
                og=1.050,
                fg=1.010,
                unknown_field="malicious"
            )
        assert "extra" in str(exc_info.value).lower()

    def test_deeply_nested_extensions(self):
        """Deeply nested extensions dict (potential DoS)."""
        # Create deeply nested structure
        nested = {"a": {}}
        current = nested["a"]
        for i in range(100):
            current[str(i)] = {}
            current = current[str(i)]

        # Should not cause stack overflow
        recipe = BrewSignalRecipe(
            name="Test",
            og=1.050,
            fg=1.010,
            brewsignal_extensions=nested
        )
        assert recipe.brewsignal_extensions is not None

    def test_large_extensions_dict(self):
        """Very large extensions dict (potential DoS)."""
        large_dict = {f"key_{i}": f"value_{i}" for i in range(10000)}
        recipe = BrewSignalRecipe(
            name="Test",
            og=1.050,
            fg=1.010,
            brewsignal_extensions=large_dict
        )
        assert len(recipe.brewsignal_extensions) == 10000

    def test_duplicate_keys_in_converter(self):
        """Test JSON with duplicate keys (last value wins)."""
        import json

        # JSON with duplicate keys
        json_str = '{"name": "First", "name": "Second"}'
        data = json.loads(json_str)

        # Python's json.loads uses last value for duplicate keys
        assert data["name"] == "Second"


# ==============================================================================
# BeerJSON Converter Vulnerabilities
# ==============================================================================

class TestConverterSecurity:
    """Test security issues in BeerJSON <-> BrewSignal converters."""

    def test_missing_required_fields_in_beerjson(self):
        """Missing required BeerJSON fields should raise error."""
        converter = BeerJSONToBrewSignalConverter()

        beerjson = {
            "beerjson": {
                "version": 1.0,
                "recipes": [{}]  # Missing name, og, fg
            }
        }

        with pytest.raises(KeyError):
            converter.convert(beerjson)

    def test_missing_beerjson_key(self):
        """Missing 'beerjson' key should raise error."""
        converter = BeerJSONToBrewSignalConverter()

        malformed = {
            "version": 1.0,
            "recipes": [{"name": "Test", "og": 1.050, "fg": 1.010}]
        }

        with pytest.raises(KeyError):
            converter.convert(malformed)

    def test_empty_recipes_array(self):
        """Empty recipes array should raise error."""
        converter = BeerJSONToBrewSignalConverter()

        beerjson = {
            "beerjson": {
                "version": 1.0,
                "recipes": []  # Empty array
            }
        }

        with pytest.raises(IndexError):
            converter.convert(beerjson)

    def test_invalid_unit_in_volume(self):
        """Unknown volume unit should raise ValueError."""
        converter = BeerJSONToBrewSignalConverter()

        beerjson = {
            "beerjson": {
                "version": 1.0,
                "recipes": [{
                    "name": "Test",
                    "original_gravity": {"value": 1.050, "unit": "sg"},
                    "final_gravity": {"value": 1.010, "unit": "sg"},
                    "batch_size": {"value": 5, "unit": "hogsheads"}  # Invalid unit
                }]
            }
        }

        with pytest.raises(ValueError) as exc_info:
            converter.convert(beerjson)
        assert "Unknown volume unit" in str(exc_info.value)

    def test_invalid_unit_in_mass(self):
        """Unknown mass unit should raise ValueError."""
        converter = BeerJSONToBrewSignalConverter()

        beerjson = {
            "beerjson": {
                "version": 1.0,
                "recipes": [{
                    "name": "Test",
                    "original_gravity": {"value": 1.050, "unit": "sg"},
                    "final_gravity": {"value": 1.010, "unit": "sg"},
                    "ingredients": {
                        "fermentable_additions": [{
                            "name": "Malt",
                            "amount": {"value": 5.0, "unit": "stones"}  # Invalid unit
                        }]
                    }
                }]
            }
        }

        with pytest.raises(ValueError) as exc_info:
            converter.convert(beerjson)
        assert "Unknown mass unit" in str(exc_info.value)

    def test_invalid_unit_in_time(self):
        """Unknown time unit should raise ValueError."""
        converter = BeerJSONToBrewSignalConverter()

        beerjson = {
            "beerjson": {
                "version": 1.0,
                "recipes": [{
                    "name": "Test",
                    "original_gravity": {"value": 1.050, "unit": "sg"},
                    "final_gravity": {"value": 1.010, "unit": "sg"},
                    "boil": {
                        "boil_time": {"value": 60, "unit": "fortnights"}  # Invalid unit
                    }
                }]
            }
        }

        with pytest.raises(ValueError) as exc_info:
            converter.convert(beerjson)
        assert "Unknown time unit" in str(exc_info.value)

    def test_temperature_unit_injection(self):
        """Non-Celsius temperature should be rejected."""
        converter = BeerJSONToBrewSignalConverter()

        # Already tested in main tests, verify it raises ValueError
        beerjson = {
            "beerjson": {
                "version": 1.0,
                "recipes": [{
                    "name": "Test",
                    "original_gravity": {"value": 1.050, "unit": "sg"},
                    "final_gravity": {"value": 1.010, "unit": "sg"},
                    "ingredients": {
                        "culture_additions": [{
                            "name": "Yeast",
                            "temperature_range": {
                                "minimum": {"value": 60, "unit": "F"}
                            }
                        }]
                    }
                }]
            }
        }

        with pytest.raises(ValueError) as exc_info:
            converter.convert(beerjson)
        assert "Celsius" in str(exc_info.value)

    def test_unit_object_without_value_key(self):
        """Unit object missing 'value' key should raise error."""
        converter = BeerJSONToBrewSignalConverter()

        beerjson = {
            "beerjson": {
                "version": 1.0,
                "recipes": [{
                    "name": "Test",
                    "original_gravity": {"unit": "sg"},  # Missing 'value'
                    "final_gravity": {"value": 1.010, "unit": "sg"}
                }]
            }
        }

        with pytest.raises(KeyError):
            converter.convert(beerjson)

    def test_unit_object_without_unit_key(self):
        """Unit object missing 'unit' key should raise error."""
        converter = BeerJSONToBrewSignalConverter()

        beerjson = {
            "beerjson": {
                "version": 1.0,
                "recipes": [{
                    "name": "Test",
                    "original_gravity": {"value": 1.050, "unit": "sg"},
                    "final_gravity": {"value": 1.010, "unit": "sg"},
                    "batch_size": {"value": 5}  # Missing 'unit'
                }]
            }
        }

        with pytest.raises(KeyError):
            converter.convert(beerjson)


# ==============================================================================
# Resource Exhaustion (DoS) Risks
# ==============================================================================

class TestResourceExhaustion:
    """Test resource exhaustion and DoS vulnerabilities."""

    def test_maximum_batch_size(self):
        """Batch size at maximum should be accepted."""
        recipe = BrewSignalRecipe(
            name="Test",
            og=1.050,
            fg=1.010,
            batch_size_liters=1000.0  # Maximum allowed
        )
        assert recipe.batch_size_liters == 1000.0

    def test_excessive_batch_size_rejected(self):
        """Batch size exceeding maximum should be rejected."""
        with pytest.raises(ValidationError):
            BrewSignalRecipe(
                name="Test",
                og=1.050,
                fg=1.010,
                batch_size_liters=1001.0  # Exceeds max
            )

    def test_maximum_boil_time(self):
        """Boil time at maximum should be accepted."""
        recipe = BrewSignalRecipe(
            name="Test",
            og=1.050,
            fg=1.010,
            boil_time_minutes=300  # Maximum allowed
        )
        assert recipe.boil_time_minutes == 300

    def test_excessive_boil_time_rejected(self):
        """Boil time exceeding maximum should be rejected."""
        with pytest.raises(ValidationError):
            BrewSignalRecipe(
                name="Test",
                og=1.050,
                fg=1.010,
                boil_time_minutes=301  # Exceeds max
            )

    def test_large_fermentables_list(self):
        """Very large fermentables list (potential DoS)."""
        from backend.services.brewsignal_format import BrewSignalFermentable

        # Create 1000 fermentables
        fermentables = [
            BrewSignalFermentable(name=f"Malt_{i}", amount_kg=0.1)
            for i in range(1000)
        ]

        recipe = BrewSignalRecipe(
            name="Test",
            og=1.050,
            fg=1.010,
            fermentables=fermentables
        )

        # Should handle large lists without crashing
        assert len(recipe.fermentables) == 1000

    def test_large_hops_list(self):
        """Very large hops list (potential DoS)."""
        from backend.services.brewsignal_format import BrewSignalHop, BrewSignalTiming

        # Create 1000 hops
        hops = [
            BrewSignalHop(
                name=f"Hop_{i}",
                amount_grams=1.0,
                timing=BrewSignalTiming(use="add_to_boil")
            )
            for i in range(1000)
        ]

        recipe = BrewSignalRecipe(
            name="Test",
            og=1.050,
            fg=1.010,
            hops=hops
        )

        # Should handle large lists without crashing
        assert len(recipe.hops) == 1000


# ==============================================================================
# Edge Cases and Boundary Conditions
# ==============================================================================

class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_minimum_og_value(self):
        """OG at minimum boundary (1.0)."""
        # FG must be >= 1.0 and < OG, so use 1.0 (water baseline)
        # This represents theoretical minimum where nothing fermented
        recipe = BrewSignalRecipe(name="Test", og=1.001, fg=1.0)
        assert recipe.og == 1.001

    def test_maximum_og_value(self):
        """OG at maximum boundary (1.2)."""
        recipe = BrewSignalRecipe(name="Test", og=1.2, fg=1.1)
        assert recipe.og == 1.2

    def test_og_below_minimum_rejected(self):
        """OG below minimum should be rejected."""
        with pytest.raises(ValidationError):
            BrewSignalRecipe(name="Test", og=0.999, fg=0.990)

    def test_og_above_maximum_rejected(self):
        """OG above maximum should be rejected."""
        with pytest.raises(ValidationError):
            BrewSignalRecipe(name="Test", og=1.201, fg=1.1)

    def test_very_long_notes(self):
        """Very long notes field should be rejected (DoS protection)."""
        long_notes = "A" * 100_000  # 100 KB of text (exceeds 10KB limit)
        with pytest.raises(ValidationError):
            BrewSignalRecipe(
                name="Test",
                og=1.050,
                fg=1.010,
                notes=long_notes
            )

    def test_percentage_conversion_precision(self):
        """Test precision in percentage conversion."""
        converter = BeerJSONToBrewSignalConverter()

        beerjson = {
            "beerjson": {
                "version": 1.0,
                "recipes": [{
                    "name": "Test",
                    "original_gravity": {"value": 1.050, "unit": "sg"},
                    "final_gravity": {"value": 1.010, "unit": "sg"},
                    "alcohol_by_volume": {"value": 0.123456789, "unit": "%"}
                }]
            }
        }

        result = converter.convert(beerjson)
        # Verify precision is maintained
        assert abs(result["recipe"]["abv"] - 12.3456789) < 0.0001


# ==============================================================================
# Integration with Recipe Import (File Upload)
# ==============================================================================

class TestFileUploadSecurity:
    """Test security issues related to file upload integration."""

    def test_converter_with_malformed_beerjson_structure(self):
        """Malformed BeerJSON structure should raise appropriate errors."""
        converter = BeerJSONToBrewSignalConverter()

        # Missing recipes array
        beerjson = {
            "beerjson": {
                "version": 1.0
            }
        }

        with pytest.raises(KeyError):
            converter.convert(beerjson)

    def test_converter_with_null_values(self):
        """Null values in required fields should raise error."""
        converter = BeerJSONToBrewSignalConverter()

        beerjson = {
            "beerjson": {
                "version": 1.0,
                "recipes": [{
                    "name": None,  # Required field is null
                    "original_gravity": {"value": 1.050, "unit": "sg"},
                    "final_gravity": {"value": 1.010, "unit": "sg"}
                }]
            }
        }

        # Should fail validation when creating BrewSignalRecipe
        with pytest.raises(ValidationError):
            result = converter.convert(beerjson)
            BrewSignalRecipe(**result["recipe"])
