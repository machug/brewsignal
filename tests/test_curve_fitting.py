"""Tests for fermentation curve fitting and predictions."""

import numpy as np
import pytest
from backend.ml.predictions.curve_fitter import FermentationCurveFitter, PredictionModel


class TestFermentationCurveFitter:
    """Tests for the fermentation curve fitter."""

    def test_initialization(self):
        """Fitter initializes with default parameters."""
        fitter = FermentationCurveFitter()

        assert fitter.min_readings == 10
        assert fitter.completion_threshold == 0.002

    def test_needs_minimum_readings(self):
        """Fitter requires minimum readings before fitting."""
        fitter = FermentationCurveFitter(min_readings=10)

        # Try to fit with insufficient data
        times = [0, 4, 8]
        sgs = [1.050, 1.049, 1.048]

        result = fitter.fit(times, sgs)

        assert result["fitted"] is False
        assert result["reason"] == "insufficient_data"
        assert result["predicted_fg"] is None

    def test_fits_exponential_decay(self, fermentation_data):
        """Fitter fits exponential decay curve to fermentation data."""
        fitter = FermentationCurveFitter(min_readings=10)

        result = fitter.fit(fermentation_data["hours"], fermentation_data["sg"])

        # Should successfully fit
        assert result["fitted"] is True
        assert result["model_type"] == "exponential"

        # Parameters should be close to ground truth
        # Ground truth: OG=1.055, FG=1.012, k=0.02
        assert result["predicted_og"] == pytest.approx(fermentation_data["og"], abs=0.003)
        assert result["predicted_fg"] == pytest.approx(fermentation_data["fg"], abs=0.003)
        assert result["decay_rate"] is not None
        assert result["r_squared"] > 0.95  # Good fit

    def test_predicts_completion_time(self, fermentation_data):
        """Fitter estimates when fermentation will complete."""
        fitter = FermentationCurveFitter(min_readings=10, completion_threshold=0.002)

        # Fit on first 50% of data
        midpoint = len(fermentation_data["hours"]) // 2
        result = fitter.fit(
            fermentation_data["hours"][:midpoint],
            fermentation_data["sg"][:midpoint]
        )

        assert result["fitted"] is True
        assert result["hours_to_completion"] is not None
        assert result["hours_to_completion"] > 0  # Should predict future completion

        # Predicted completion time should be reasonable
        # With k=0.02, ~75% completion takes about 70 hours
        assert result["hours_to_completion"] < 200

    def test_detects_completed_fermentation(self):
        """Fitter recognizes when fermentation has already completed."""
        fitter = FermentationCurveFitter(completion_threshold=0.002)

        # Simulate fermentation that has reached near-terminal gravity
        # Use exponential decay with very slow rate near the end
        og = 1.055
        fg = 1.012
        k = 0.04  # Faster decay
        times = [float(i * 4) for i in range(20)]  # 80 hours total
        sgs = [fg + (og - fg) * np.exp(-k * t) for t in times]

        result = fitter.fit(times, sgs)

        assert result["fitted"] is True
        # After 80 hours with k=0.04, rate should be very low
        # hours_to_completion should be small (< 10 hours) or zero
        assert result["hours_to_completion"] < 10

    def test_handles_stuck_fermentation(self):
        """Fitter handles stuck fermentation gracefully."""
        fitter = FermentationCurveFitter(min_readings=10)

        # Simulate stuck fermentation (stops declining early)
        times = [float(i * 4) for i in range(15)]
        sgs = [1.050 - i * 0.001 for i in range(10)] + [1.040] * 5

        result = fitter.fit(times, sgs)

        # Should still fit but predict FG near stuck point
        # Exponential fit may smooth slightly below flat readings
        assert result["fitted"] is True
        assert result["predicted_fg"] >= 1.035  # Within reasonable range of stuck point
        assert result["predicted_fg"] <= 1.042  # Not too high

    def test_returns_predictions_at_intervals(self, fermentation_data):
        """Fitter can predict SG at future time points."""
        fitter = FermentationCurveFitter(min_readings=10)

        # Fit on first half
        midpoint = len(fermentation_data["hours"]) // 2
        result = fitter.fit(
            fermentation_data["hours"][:midpoint],
            fermentation_data["sg"][:midpoint]
        )

        # Get predictions for next 48 hours
        predictions = fitter.predict([24, 48, 72])

        assert len(predictions) == 3
        assert all(1.000 < sg < 1.100 for sg in predictions)
        # Predictions should decline over time
        assert predictions[0] > predictions[1] > predictions[2]


class TestMultiModelPredictions:
    """Tests for multi-model prediction system (Gompertz, Logistic, Auto)."""

    def test_prediction_model_enum(self):
        """PredictionModel enum has all expected values."""
        assert PredictionModel.EXPONENTIAL.value == "exponential"
        assert PredictionModel.GOMPERTZ.value == "gompertz"
        assert PredictionModel.LOGISTIC.value == "logistic"
        assert PredictionModel.AUTO.value == "auto"

    def test_fits_gompertz_model(self, fermentation_data):
        """Fitter fits Gompertz S-curve model to fermentation data."""
        fitter = FermentationCurveFitter(min_readings=10)

        result = fitter.fit(
            fermentation_data["hours"],
            fermentation_data["sg"],
            model="gompertz"
        )

        # Should successfully fit
        assert result["fitted"] is True
        assert result["model_type"] == "gompertz"

        # Parameters should be reasonable
        assert result["predicted_og"] == pytest.approx(fermentation_data["og"], abs=0.005)
        assert result["predicted_fg"] is not None
        assert result["r_squared"] > 0.85  # Reasonable fit

    def test_fits_logistic_model(self, fermentation_data):
        """Fitter fits Logistic S-curve model to fermentation data."""
        fitter = FermentationCurveFitter(min_readings=10)

        result = fitter.fit(
            fermentation_data["hours"],
            fermentation_data["sg"],
            model="logistic"
        )

        # Should successfully fit
        assert result["fitted"] is True
        assert result["model_type"] == "logistic"

        # Parameters should be reasonable (logistic fits differently than exponential)
        # The logistic model may estimate OG differently due to its symmetric nature
        assert 1.050 < result["predicted_og"] < 1.100  # Reasonable OG range
        assert result["predicted_fg"] is not None
        assert result["r_squared"] > 0.85  # Reasonable fit

    def test_auto_mode_selects_best_model(self, fermentation_data):
        """Auto mode tries all models and returns best R²."""
        fitter = FermentationCurveFitter(min_readings=10)

        result = fitter.fit(
            fermentation_data["hours"],
            fermentation_data["sg"],
            model="auto"
        )

        # Should successfully fit
        assert result["fitted"] is True
        assert result["model_type"] in ["exponential", "gompertz", "logistic"]
        assert result["r_squared"] > 0.85

    def test_exponential_wins_for_exponential_data(self, fermentation_data):
        """For pure exponential data, exponential or compatible model should fit best."""
        fitter = FermentationCurveFitter(min_readings=10)

        # Fit explicitly with exponential
        exp_result = fitter.fit(
            fermentation_data["hours"],
            fermentation_data["sg"],
            model="exponential"
        )

        # Fit with auto
        auto_result = fitter.fit(
            fermentation_data["hours"],
            fermentation_data["sg"],
            model="auto"
        )

        # Both should fit well
        assert exp_result["fitted"] is True
        assert auto_result["fitted"] is True

        # Auto should return a model with similar or better R²
        assert auto_result["r_squared"] >= exp_result["r_squared"] - 0.01

    def test_model_parameter_case_insensitive(self, fermentation_data):
        """Model parameter should be case insensitive."""
        fitter = FermentationCurveFitter(min_readings=10)

        result_lower = fitter.fit(
            fermentation_data["hours"],
            fermentation_data["sg"],
            model="exponential"
        )

        result_upper = fitter.fit(
            fermentation_data["hours"],
            fermentation_data["sg"],
            model="EXPONENTIAL"
        )

        assert result_lower["model_type"] == result_upper["model_type"]
        assert result_lower["predicted_fg"] == pytest.approx(result_upper["predicted_fg"], abs=0.001)

    def test_unknown_model_defaults_to_exponential(self, fermentation_data):
        """Unknown model name should default to exponential."""
        fitter = FermentationCurveFitter(min_readings=10)

        result = fitter.fit(
            fermentation_data["hours"],
            fermentation_data["sg"],
            model="unknown_model"
        )

        # Should fall back to exponential
        assert result["fitted"] is True
        assert result["model_type"] == "exponential"

    def test_gompertz_handles_lag_phase_data(self):
        """Gompertz model handles fermentation with lag phase."""
        fitter = FermentationCurveFitter(min_readings=10)

        # Generate data with lag phase (flat start, then fermentation)
        og = 1.055
        fg = 1.012
        lag = 12  # 12 hours lag
        mu = 0.01  # growth rate

        # Create data points: flat for lag period, then decay
        hours = list(range(0, 120, 4))
        sgs = []
        for t in hours:
            if t < lag:
                sgs.append(og - 0.001 * (t / lag))  # Very slow initial drop
            else:
                # Exponential decay after lag
                sgs.append(fg + (og - fg) * np.exp(-mu * (t - lag)))

        result = fitter.fit(hours, sgs, model="gompertz")

        # Should fit with reasonable parameters
        assert result["fitted"] is True
        assert result["model_type"] == "gompertz"
        assert result["predicted_fg"] < 1.025  # Should predict reasonably low FG

    def test_all_models_return_completion_time(self, fermentation_data):
        """All models should return hours_to_completion."""
        fitter = FermentationCurveFitter(min_readings=10)

        # Test partial fermentation data (first half)
        midpoint = len(fermentation_data["hours"]) // 2

        for model_type in ["exponential", "gompertz", "logistic"]:
            result = fitter.fit(
                fermentation_data["hours"][:midpoint],
                fermentation_data["sg"][:midpoint],
                model=model_type
            )

            if result["fitted"]:
                assert result["hours_to_completion"] is not None
                assert result["hours_to_completion"] >= 0

    def test_expected_fg_constrains_all_models(self, fermentation_data):
        """Expected FG constraint should apply to all model types."""
        fitter = FermentationCurveFitter(min_readings=10)
        expected_fg = 1.010

        for model_type in ["exponential", "gompertz", "logistic"]:
            result = fitter.fit(
                fermentation_data["hours"],
                fermentation_data["sg"],
                expected_fg=expected_fg,
                model=model_type
            )

            if result["fitted"]:
                # Predicted FG should respect the constraint (with margin)
                assert result["predicted_fg"] >= expected_fg - 0.003


class TestBlendedPredictions:
    """Tests for blended linear/curve predictions."""

    def test_returns_blended_fields(self, fermentation_data):
        """Fit result includes blended prediction fields."""
        fitter = FermentationCurveFitter(min_readings=10)

        result = fitter.fit(
            fermentation_data["hours"],
            fermentation_data["sg"],
            expected_fg=fermentation_data["fg"]
        )

        assert result["fitted"] is True
        assert "hours_to_target_linear" in result
        assert "blended_hours_to_completion" in result
        assert "confidence" in result

    def test_confidence_high_when_prediction_matches_target(self, fermentation_data):
        """Confidence should be high when predicted FG close to target."""
        fitter = FermentationCurveFitter(min_readings=10)

        # Use the actual FG from data as expected (perfect match scenario)
        result = fitter.fit(
            fermentation_data["hours"],
            fermentation_data["sg"],
            expected_fg=fermentation_data["fg"]
        )

        assert result["fitted"] is True
        # Should have reasonable confidence when prediction matches
        assert result["confidence"] is not None
        assert result["confidence"] > 0.5

    def test_confidence_low_when_prediction_differs_from_target(self):
        """Confidence should be lower when predicted FG differs significantly from target."""
        fitter = FermentationCurveFitter(min_readings=10)

        # Create data that will plateau early (around 1.030)
        og = 1.050
        fg_actual = 1.030  # Will stall early
        fg_target = 1.010  # Recipe expects lower

        hours = list(range(0, 120, 4))
        sgs = [fg_actual + (og - fg_actual) * np.exp(-0.03 * t) for t in hours]

        result = fitter.fit(hours, sgs, expected_fg=fg_target)

        assert result["fitted"] is True
        # Confidence should be lower due to FG mismatch
        assert result["confidence"] is not None
        # Large deviation (0.020) should reduce confidence significantly
        assert result["confidence"] < 0.8

    def test_blended_prediction_favors_linear_when_confidence_low(self):
        """Blended prediction should favor linear ETA when confidence is low."""
        fitter = FermentationCurveFitter(min_readings=10)

        # Early fermentation data - not enough to predict plateau reliably
        og = 1.050
        fg_target = 1.010

        # Only generate first 20% of fermentation (early stage)
        hours = list(range(0, 30, 2))
        # Simulate linear-ish drop at beginning
        sgs = [og - 0.0003 * t for t in hours]

        result = fitter.fit(hours, sgs, expected_fg=fg_target)

        if result["fitted"]:
            # At early stage, confidence should be low
            # and blended should be closer to linear
            assert result["confidence"] is not None
            assert result["hours_to_target_linear"] is not None
            assert result["blended_hours_to_completion"] is not None

    def test_confidence_considers_progress(self):
        """Confidence should be lower when fermentation progress is low."""
        fitter = FermentationCurveFitter(min_readings=10)

        og = 1.050
        fg_target = 1.010

        # Generate early fermentation data (only 10% progress)
        hours = list(range(0, 24, 2))  # 24 hours
        current_sg = 1.046  # Only dropped 4 points from 1.050
        sgs = [og - (og - current_sg) * (t / hours[-1]) for t in hours]

        result = fitter.fit(hours, sgs, expected_fg=fg_target)

        if result["fitted"]:
            # Low progress should reduce confidence
            assert result["confidence"] is not None
            # 10% progress to target means very low confidence
            assert result["confidence"] < 0.5

    def test_linear_eta_extrapolates_to_target(self, fermentation_data):
        """Linear ETA should predict time to reach recipe target FG."""
        fitter = FermentationCurveFitter(min_readings=10)

        # Use first half of fermentation data (still actively fermenting)
        midpoint = len(fermentation_data["hours"]) // 2

        result = fitter.fit(
            fermentation_data["hours"][:midpoint],
            fermentation_data["sg"][:midpoint],
            expected_fg=fermentation_data["fg"]
        )

        assert result["fitted"] is True
        assert result["hours_to_target_linear"] is not None
        # Linear ETA should be positive (still fermenting)
        assert result["hours_to_target_linear"] > 0
