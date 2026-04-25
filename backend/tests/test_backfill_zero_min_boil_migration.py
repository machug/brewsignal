"""Tests for the zero-min-boil → whirlpool backfill migration."""
import pytest

from backend.migrations.backfill_zero_min_boil_to_whirlpool import (
    _is_zero_min_boil_timing,
    _is_zero_min_boil_ext_hop,
)


class TestZeroMinBoilDetectors:
    """The migration is straightforward UPDATE-by-row logic; the only
    branching lives in these two predicates. End-to-end behaviour is
    verified by running the migration against the production database
    on deploy and inspecting affected recipes."""

    @pytest.mark.parametrize("timing,expected", [
        ({"use": "add_to_boil", "duration": {"value": 0, "unit": "min"}}, True),
        ({"use": "boil", "duration": {"value": 0, "unit": "min"}}, True),
        ({"use": "Add_To_Boil", "duration": {"value": 0, "unit": "min"}}, True),
        ({"use": "add_to_boil", "duration": 0}, True),  # legacy scalar
        ({"use": "add_to_boil", "duration": {"value": 60, "unit": "min"}}, False),
        ({"use": "add_to_whirlpool", "duration": {"value": 0, "unit": "min"}}, False),
        ({"use": "add_to_fermentation", "duration": {"value": 4, "unit": "day"}}, False),
        ({"use": "add_to_boil"}, True),  # missing duration treated as 0
        ({}, False),  # no use
        (None, False),
        ("not a dict", False),
    ])
    def test_timing_detector(self, timing, expected):
        assert _is_zero_min_boil_timing(timing) is expected

    @pytest.mark.parametrize("hop,expected", [
        ({"use": "add_to_boil", "boil_time_minutes": 0}, True),
        ({"use": "boil", "boil_time_minutes": 0}, True),
        ({"use": "Add_To_Boil", "boil_time_minutes": 0}, True),
        ({"use": "add_to_boil", "boil_time_minutes": 60}, False),
        ({"use": "add_to_whirlpool", "boil_time_minutes": 0}, False),
        ({"use": "dry_hop", "boil_time_minutes": 5760}, False),
        ({"use": "add_to_boil"}, True),  # missing boil_time_minutes treated as 0
        ({}, False),
        ("not a dict", False),
    ])
    def test_ext_hop_detector(self, hop, expected):
        assert _is_zero_min_boil_ext_hop(hop) is expected
