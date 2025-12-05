"""Tests for batch temperature validation and related calculations."""
import pytest
from pydantic import ValidationError

from backend.models import BatchCreate, BatchUpdate


class TestTemperatureValidation:
    """Test temperature target and hysteresis validation."""

    # Valid Celsius ranges: temp_target 0-100°C, temp_hysteresis 0.05-5.5°C

    def test_temp_target_valid_range(self):
        """Test that valid temperature targets are accepted."""
        # Minimum boundary
        batch = BatchCreate(
            name="Test Batch",
            temp_target=0.0
        )
        assert batch.temp_target == 0.0

        # Typical fermentation temp
        batch = BatchCreate(
            name="Test Batch",
            temp_target=18.0
        )
        assert batch.temp_target == 18.0

        # Maximum boundary
        batch = BatchCreate(
            name="Test Batch",
            temp_target=100.0
        )
        assert batch.temp_target == 100.0

    def test_temp_target_below_minimum(self):
        """Test that temperatures below 0°C are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            BatchCreate(
                name="Test Batch",
                temp_target=-1.0
            )
        assert "temp_target must be between 0-100°C" in str(exc_info.value)

    def test_temp_target_above_maximum(self):
        """Test that temperatures above 100°C are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            BatchCreate(
                name="Test Batch",
                temp_target=101.0
            )
        assert "temp_target must be between 0-100°C" in str(exc_info.value)

    def test_temp_target_null_allowed(self):
        """Test that null temperature target is allowed."""
        batch = BatchCreate(
            name="Test Batch",
            temp_target=None
        )
        assert batch.temp_target is None

    def test_temp_hysteresis_valid_range(self):
        """Test that valid hysteresis values are accepted."""
        # Minimum boundary
        batch = BatchCreate(
            name="Test Batch",
            temp_hysteresis=0.05
        )
        assert batch.temp_hysteresis == 0.05

        # Typical value
        batch = BatchCreate(
            name="Test Batch",
            temp_hysteresis=0.5
        )
        assert batch.temp_hysteresis == 0.5

        # Maximum boundary
        batch = BatchCreate(
            name="Test Batch",
            temp_hysteresis=5.5
        )
        assert batch.temp_hysteresis == 5.5

    def test_temp_hysteresis_below_minimum(self):
        """Test that hysteresis below 0.05°C is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            BatchCreate(
                name="Test Batch",
                temp_hysteresis=0.04
            )
        assert "temp_hysteresis must be between 0.05-5.5°C" in str(exc_info.value)

    def test_temp_hysteresis_above_maximum(self):
        """Test that hysteresis above 5.5°C is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            BatchCreate(
                name="Test Batch",
                temp_hysteresis=5.6
            )
        assert "temp_hysteresis must be between 0.05-5.5°C" in str(exc_info.value)

    def test_temp_hysteresis_null_allowed(self):
        """Test that null hysteresis is allowed."""
        batch = BatchCreate(
            name="Test Batch",
            temp_hysteresis=None
        )
        assert batch.temp_hysteresis is None

    def test_batch_update_temp_validation(self):
        """Test that BatchUpdate has the same validation rules."""
        # Valid update
        batch_update = BatchUpdate(temp_target=20.0, temp_hysteresis=0.5)
        assert batch_update.temp_target == 20.0
        assert batch_update.temp_hysteresis == 0.5

        # Invalid temp_target
        with pytest.raises(ValidationError) as exc_info:
            BatchUpdate(temp_target=150.0)
        assert "temp_target must be between 0-100°C" in str(exc_info.value)

        # Invalid temp_hysteresis
        with pytest.raises(ValidationError) as exc_info:
            BatchUpdate(temp_hysteresis=10.0)
        assert "temp_hysteresis must be between 0.05-5.5°C" in str(exc_info.value)

    def test_combined_temp_control_settings(self):
        """Test that temperature control settings work together."""
        batch = BatchCreate(
            name="Test Batch",
            temp_target=18.0,
            temp_hysteresis=0.5,
            heater_entity_id="switch.fermenter_heater"
        )
        assert batch.temp_target == 18.0
        assert batch.temp_hysteresis == 0.5
        assert batch.heater_entity_id == "switch.fermenter_heater"


class TestABVCalculation:
    """Test ABV calculation from OG/FG (frontend logic documented here)."""

    # ABV formula: (OG - FG) × 131.25
    # This is tested in frontend but documented here for reference

    def test_abv_calculation_formula(self):
        """Document the ABV calculation formula used in frontend."""
        # Standard test case
        og = 1.050
        fg = 1.010
        expected_abv = (og - fg) * 131.25
        assert expected_abv == pytest.approx(5.25, rel=0.01)

        # Low gravity beer
        og = 1.040
        fg = 1.008
        expected_abv = (og - fg) * 131.25
        assert expected_abv == pytest.approx(4.2, rel=0.01)

        # High gravity beer
        og = 1.080
        fg = 1.015
        expected_abv = (og - fg) * 131.25
        assert expected_abv == pytest.approx(8.53, rel=0.01)

    def test_abv_edge_cases(self):
        """Test edge cases for ABV calculation."""
        # No attenuation (stuck fermentation)
        og = 1.050
        fg = 1.050
        expected_abv = (og - fg) * 131.25
        assert expected_abv == 0.0

        # Very high attenuation
        og = 1.050
        fg = 1.000
        expected_abv = (og - fg) * 131.25
        assert expected_abv == pytest.approx(6.56, rel=0.01)
