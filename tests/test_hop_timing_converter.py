"""Test hop timing conversion utility."""
import pytest
from backend.services.hop_timing_converter import convert_hop_timing_safe, convert_hop_timing_batch


class TestConvertHopTimingSafe:
    """Test hop timing conversion for various input scenarios."""

    def test_boil_hop_with_time(self):
        """Boil hops should get add_to_boil use with duration."""
        result = convert_hop_timing_safe("Boil", 60)

        assert result is not None
        assert result["use"] == "add_to_boil"
        assert result["continuous"] is False
        assert result["duration"] == {"value": 60, "unit": "min"}

    def test_dry_hop_with_time(self):
        """Dry hops should get add_to_fermentation use with duration in days."""
        result = convert_hop_timing_safe("Dry Hop", 1440)  # 1 day in minutes

        assert result is not None
        assert result["use"] == "add_to_fermentation"
        assert result["continuous"] is False
        assert result["duration"] == {"value": 1, "unit": "day"}
        assert result["phase"] == "primary"

    def test_dry_hop_fractional_days(self):
        """Dry hop with fractional days should be converted to int."""
        result = convert_hop_timing_safe("Dry Hop", 2880)  # 2 days

        assert result["duration"]["value"] == 2
        assert result["duration"]["unit"] == "day"

    def test_mash_hop(self):
        """Mash hops should get add_to_mash use."""
        result = convert_hop_timing_safe("Mash", 60)

        assert result is not None
        assert result["use"] == "add_to_mash"
        assert result["continuous"] is False
        # Mash hops typically don't have duration in the mapping
        assert "duration" not in result

    def test_first_wort_hop(self):
        """First wort hops should map to add_to_boil but without duration.

        Duration is only added for "Boil" and "Aroma" use types, not "First Wort".
        """
        result = convert_hop_timing_safe("First Wort", 90)

        assert result is not None
        assert result["use"] == "add_to_boil"
        assert result["continuous"] is False
        # First Wort doesn't get duration in current implementation
        assert "duration" not in result

    def test_aroma_hop(self):
        """Aroma hops should map to add_to_boil with duration."""
        result = convert_hop_timing_safe("Aroma", 5)

        assert result is not None
        assert result["use"] == "add_to_boil"
        assert result["duration"] == {"value": 5, "unit": "min"}

    def test_unknown_use_returns_none(self):
        """Unknown use values should return None."""
        result = convert_hop_timing_safe("Unknown", 60)
        assert result is None

    def test_empty_string_use_returns_none(self):
        """Empty string use should return None."""
        result = convert_hop_timing_safe("", 60)
        assert result is None

    def test_none_use_returns_none(self):
        """None use should return None."""
        result = convert_hop_timing_safe(None, 60)
        assert result is None

    def test_null_time_still_creates_timing(self):
        """Null time should still create timing object, just without duration."""
        result = convert_hop_timing_safe("Boil", None)

        assert result is not None
        assert result["use"] == "add_to_boil"
        assert result["continuous"] is False
        assert "duration" not in result

    def test_zero_time_no_duration(self):
        """Zero time should not add duration field."""
        result = convert_hop_timing_safe("Boil", 0)

        assert result is not None
        assert result["use"] == "add_to_boil"
        assert "duration" not in result

    def test_negative_time_no_duration(self):
        """Negative time should not add duration field."""
        result = convert_hop_timing_safe("Boil", -10)

        assert result is not None
        assert result["use"] == "add_to_boil"
        assert "duration" not in result

    def test_whitespace_only_use_returns_none(self):
        """Whitespace-only use should be treated as empty."""
        result = convert_hop_timing_safe("   ", 60)
        # Note: Current implementation only checks for empty string, not whitespace
        # This would need to be enhanced if whitespace handling is required
        assert result is None


class TestConvertHopTimingBatch:
    """Test batch conversion of hop timing."""

    def test_batch_conversion_multiple_hops(self):
        """Should convert multiple hops in batch."""
        hops = [
            ("Boil", 60),
            ("Dry Hop", 1440),
            ("Mash", 0)
        ]

        results = convert_hop_timing_batch(hops)

        assert len(results) == 3
        assert results[0]["use"] == "add_to_boil"
        assert results[1]["use"] == "add_to_fermentation"
        assert results[2]["use"] == "add_to_mash"

    def test_batch_conversion_with_invalid_hops(self):
        """Should handle invalid hops in batch."""
        hops = [
            ("Boil", 60),
            ("Unknown", 60),
            (None, 60),
            ("", 60)
        ]

        results = convert_hop_timing_batch(hops)

        assert len(results) == 4
        assert results[0] is not None
        assert results[1] is None
        assert results[2] is None
        assert results[3] is None

    def test_batch_conversion_empty_list(self):
        """Should handle empty hop list."""
        results = convert_hop_timing_batch([])
        assert results == []

    def test_batch_conversion_with_tuples_missing_time(self):
        """Should handle tuples with missing time field."""
        hops = [
            ("Boil",),  # No time
        ]

        results = convert_hop_timing_batch(hops)

        assert len(results) == 1
        assert results[0] is not None
        assert results[0]["use"] == "add_to_boil"
        assert "duration" not in results[0]


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_very_large_time_value(self):
        """Should handle very large time values."""
        result = convert_hop_timing_safe("Boil", 10000)

        assert result is not None
        assert result["duration"]["value"] == 10000

    def test_very_small_positive_time(self):
        """Should handle very small positive time values."""
        result = convert_hop_timing_safe("Boil", 0.1)

        assert result is not None
        assert result["duration"]["value"] == 0.1

    def test_float_time_values(self):
        """Should handle float time values."""
        result = convert_hop_timing_safe("Boil", 45.5)

        assert result is not None
        assert result["duration"]["value"] == 45.5

    def test_case_sensitivity(self):
        """Use values are case-sensitive."""
        # Lowercase should not match
        result = convert_hop_timing_safe("boil", 60)
        assert result is None

        # Correct case should work
        result = convert_hop_timing_safe("Boil", 60)
        assert result is not None

    def test_dry_hop_zero_time(self):
        """Dry hop with zero time should not have duration."""
        result = convert_hop_timing_safe("Dry Hop", 0)

        assert result is not None
        assert result["use"] == "add_to_fermentation"
        assert "duration" not in result
        # Should still have phase even without duration
        assert "phase" not in result  # phase only added when duration exists
