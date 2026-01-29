"""Fermentation curve fitting for predictions.

Fits various models to fermentation data to predict:
- Final gravity (FG)
- Time to completion
- Future SG values

Supported models:
- Exponential decay: SG(t) = FG + (OG - FG) * exp(-k * t)
- Gompertz: S-curve with lag phase, better for ferments with delayed start
- Logistic: Symmetric S-curve, good for steady fermentation profiles

Where:
- OG: Original gravity (initial SG)
- FG: Final gravity (terminal SG)
- k: Decay/growth rate constant
- t: Time in hours
"""

import numpy as np
from scipy.optimize import curve_fit
from typing import Optional
from enum import Enum


class PredictionModel(str, Enum):
    """Available prediction model types."""
    EXPONENTIAL = "exponential"
    GOMPERTZ = "gompertz"
    LOGISTIC = "logistic"
    AUTO = "auto"  # Pick best R²


class FermentationCurveFitter:
    """Fits various curve models to fermentation gravity data.

    The fitter uses non-linear least squares to fit curves to SG readings
    over time. Supports multiple models for different fermentation profiles.

    Supported models:
    - Exponential: SG(t) = FG + (OG - FG) * exp(-k * t)
    - Gompertz: S-curve with lag phase for ferments with delayed starts
    - Logistic: Symmetric S-curve for steady fermentation profiles

    Predictions can be used for:
    - Estimating final gravity (FG)
    - Predicting completion time
    - Forecasting future SG values

    Blended Predictions:
    - Early in fermentation, curve fitting may predict premature plateau
    - Linear extrapolation to recipe target FG is more reliable early on
    - Confidence score determines blend: low confidence = favor linear
    """

    def __init__(
        self,
        min_readings: int = 10,
        completion_threshold: float = 0.002,  # SG per day
    ):
        """Initialize the curve fitter.

        Args:
            min_readings: Minimum readings required to fit curve
            completion_threshold: Daily SG change rate considered "complete"
        """
        self.min_readings = min_readings
        self.completion_threshold = completion_threshold

        # Fitted parameters (None until fit() is called)
        self.og: Optional[float] = None  # Original gravity
        self.fg: Optional[float] = None  # Final gravity
        self.k: Optional[float] = None   # Decay rate constant
        self.r_squared: Optional[float] = None  # Fit quality
        self.model_type: Optional[str] = None  # Current model type

    # =========================================================================
    # Model Functions
    # =========================================================================

    @staticmethod
    def _exp_decay(t, og, fg, k):
        """Exponential decay model: SG(t) = FG + (OG - FG) * exp(-k * t)"""
        return fg + (og - fg) * np.exp(-k * t)

    @staticmethod
    def _gompertz(t, og, fg, mu, lag):
        """Gompertz model: S-curve with lag phase.

        Better for ferments with an initial lag before active fermentation.
        SG(t) = OG - A * exp(-exp((mu*e/A)*(lag-t) + 1))

        Where A = OG - FG (total drop)
        """
        A = og - fg
        # Avoid divide by zero
        if A <= 0:
            return np.full_like(t, og)
        return og - A * np.exp(-np.exp((mu * np.e / A) * (lag - t) + 1))

    @staticmethod
    def _logistic(t, og, fg, k, t_half):
        """Logistic model: Symmetric S-curve.

        Good for steady, symmetric fermentation profiles.
        SG(t) = FG + (OG - FG) / (1 + exp(k * (t - t_half)))

        Where t_half = time to reach halfway point
        """
        return fg + (og - fg) / (1 + np.exp(k * (t - t_half)))

    def fit(
        self,
        times: list[float],
        sgs: list[float],
        expected_fg: Optional[float] = None,
        model: str = "auto",
    ) -> dict:
        """Fit a curve model to fermentation data.

        Args:
            times: Time points in hours since fermentation start
            sgs: Specific gravity readings
            expected_fg: Expected final gravity from recipe (used as lower bound)
            model: Model type to use: "exponential", "gompertz", "logistic", or "auto"

        Returns:
            Dictionary with fit results:
            - fitted: True if fit successful
            - model_type: Type of model used ("exponential", "gompertz", "logistic")
            - predicted_og: Fitted original gravity
            - predicted_fg: Fitted final gravity
            - decay_rate: Fitted decay constant k (or equivalent rate param)
            - r_squared: R² goodness of fit
            - hours_to_completion: Estimated hours until complete
            - reason: If not fitted, reason why
        """
        # Check minimum readings
        if len(times) < self.min_readings:
            return self._failure_result("insufficient_data")

        # Convert to numpy arrays
        times_arr = np.array(times, dtype=float)
        sgs_arr = np.array(sgs, dtype=float)

        # Initial parameter guesses
        og_guess = sgs_arr[0]  # First reading
        fg_guess = sgs_arr[-1]  # Last reading

        # Check if we have enough SG drop to make a meaningful prediction
        sg_drop = og_guess - sgs_arr[-1]
        if sg_drop < 0.005:
            return self._failure_result("insufficient_fermentation_progress")

        # Calculate FG lower bound
        if expected_fg is not None:
            fg_lower = max(1.000, expected_fg - 0.003)
        else:
            fg_lower = 1.000

        # Normalize model string
        model = model.lower() if model else "auto"

        # AUTO mode: try all models and pick the best R²
        if model == "auto":
            return self._fit_auto(times_arr, sgs_arr, og_guess, fg_guess, fg_lower, expected_fg)

        # Fit specific model
        if model == "exponential":
            return self._fit_exponential(times_arr, sgs_arr, og_guess, fg_guess, fg_lower, expected_fg)
        elif model == "gompertz":
            return self._fit_gompertz(times_arr, sgs_arr, og_guess, fg_guess, fg_lower, expected_fg)
        elif model == "logistic":
            return self._fit_logistic(times_arr, sgs_arr, og_guess, fg_guess, fg_lower, expected_fg)
        else:
            # Unknown model, default to exponential
            return self._fit_exponential(times_arr, sgs_arr, og_guess, fg_guess, fg_lower, expected_fg)

    def _failure_result(self, reason: str) -> dict:
        """Return a standard failure result dictionary."""
        return {
            "fitted": False,
            "model_type": None,
            "predicted_og": None,
            "predicted_fg": None,
            "decay_rate": None,
            "r_squared": None,
            "hours_to_completion": None,
            "hours_to_target_linear": None,
            "blended_hours_to_completion": None,
            "confidence": None,
            "reason": reason,
        }

    def _calculate_linear_eta(
        self,
        times: np.ndarray,
        sgs: np.ndarray,
        target_fg: float,
    ) -> Optional[float]:
        """Calculate hours to target FG using linear extrapolation.

        Args:
            times: Time points in hours
            sgs: Specific gravity readings
            target_fg: Target final gravity from recipe

        Returns:
            Hours until target FG reached, or None if slope is positive/zero
        """
        n = len(times)
        if n < 2:
            return None

        # Simple linear regression
        sum_x = np.sum(times)
        sum_y = np.sum(sgs)
        sum_xy = np.sum(times * sgs)
        sum_x2 = np.sum(times ** 2)

        denom = n * sum_x2 - sum_x ** 2
        if abs(denom) < 1e-10:
            return None

        slope = (n * sum_xy - sum_x * sum_y) / denom
        intercept = (sum_y - slope * sum_x) / n

        # Only meaningful if gravity is dropping
        if slope >= 0:
            return None

        # Calculate when we'll hit target FG
        # target_fg = slope * t + intercept
        # t = (target_fg - intercept) / slope
        t_target = (target_fg - intercept) / slope
        current_time = times[-1]

        if t_target <= current_time:
            return 0  # Already past target

        hours_remaining = t_target - current_time

        # Cap at 60 days (1440 hours) for sanity
        if hours_remaining > 1440:
            return 1440

        return float(hours_remaining)

    def _calculate_confidence(
        self,
        r_squared: float,
        predicted_fg: float,
        target_fg: Optional[float],
        current_sg: float,
        og: float,
    ) -> float:
        """Calculate confidence score for curve-based prediction.

        Confidence is reduced when:
        - R² is low (poor curve fit)
        - Predicted FG deviates significantly from recipe target
        - Progress toward target is low (too early to predict plateau)

        Args:
            r_squared: Curve fit quality (0-1)
            predicted_fg: FG predicted by curve fit
            target_fg: Recipe target FG (if available)
            current_sg: Current specific gravity
            og: Original gravity

        Returns:
            Confidence score (0-1) for curve-based prediction
        """
        # Start with R² as base confidence
        confidence = r_squared

        # If no target FG provided, use moderate confidence
        if target_fg is None:
            return confidence * 0.7

        # Factor 1: FG deviation penalty
        # If predicted FG differs significantly from target, reduce confidence
        fg_deviation = abs(predicted_fg - target_fg)
        if fg_deviation > 0.003:
            # Scale: 0.003 deviation = no penalty, 0.020+ = 80% penalty
            deviation_factor = max(0.2, 1.0 - (fg_deviation - 0.003) / 0.017)
            confidence *= deviation_factor

        # Factor 2: Progress penalty
        # If we're early in fermentation, curve plateau prediction is unreliable
        total_expected_drop = og - target_fg
        if total_expected_drop > 0.005:
            current_drop = og - current_sg
            progress = current_drop / total_expected_drop

            if progress < 0.6:
                # Scale: 0% progress = 0 confidence, 60%+ = full confidence
                progress_factor = progress / 0.6
                confidence *= progress_factor

        return max(0.0, min(1.0, confidence))

    def _blend_predictions(
        self,
        curve_hours: Optional[float],
        linear_hours: Optional[float],
        confidence: float,
    ) -> Optional[float]:
        """Blend curve and linear predictions based on confidence.

        Args:
            curve_hours: Hours to completion from curve fit (to predicted FG)
            linear_hours: Hours to target FG from linear extrapolation
            confidence: Confidence in curve prediction (0-1)

        Returns:
            Blended hours estimate, or best available single estimate
        """
        # If both are available, blend them
        if curve_hours is not None and linear_hours is not None:
            # High confidence = favor curve, low confidence = favor linear
            blended = confidence * curve_hours + (1 - confidence) * linear_hours
            return float(blended)

        # Fall back to whichever is available
        if linear_hours is not None:
            return linear_hours
        if curve_hours is not None:
            return curve_hours

        return None

    def _calculate_r_squared(self, y_actual: np.ndarray, y_predicted: np.ndarray) -> float:
        """Calculate R² (coefficient of determination)."""
        residuals = y_actual - y_predicted
        ss_res = np.sum(residuals ** 2)
        ss_tot = np.sum((y_actual - np.mean(y_actual)) ** 2)
        return 1 - (ss_res / ss_tot) if ss_tot > 0 else 0

    def _fit_auto(
        self,
        times_arr: np.ndarray,
        sgs_arr: np.ndarray,
        og_guess: float,
        fg_guess: float,
        fg_lower: float,
        target_fg: Optional[float] = None,
    ) -> dict:
        """Try all models and return the one with best R²."""
        results = []

        # Try each model
        for model_name, fit_func in [
            ("exponential", self._fit_exponential),
            ("gompertz", self._fit_gompertz),
            ("logistic", self._fit_logistic),
        ]:
            result = fit_func(times_arr, sgs_arr, og_guess, fg_guess, fg_lower, target_fg)
            if result["fitted"] and result["r_squared"] is not None:
                results.append(result)

        if not results:
            # All models failed, return exponential failure for consistent error
            return self._fit_exponential(times_arr, sgs_arr, og_guess, fg_guess, fg_lower, target_fg)

        # Return result with highest R²
        best = max(results, key=lambda r: r["r_squared"])
        return best

    def _fit_exponential(
        self,
        times_arr: np.ndarray,
        sgs_arr: np.ndarray,
        og_guess: float,
        fg_guess: float,
        fg_lower: float,
        target_fg: Optional[float] = None,
    ) -> dict:
        """Fit exponential decay model."""
        k_guess = 0.02  # Typical fermentation rate

        try:
            popt, _ = curve_fit(
                self._exp_decay,
                times_arr,
                sgs_arr,
                p0=[og_guess, fg_guess, k_guess],
                bounds=([1.000, fg_lower, 0.001], [1.200, 1.100, 0.5]),
                maxfev=10000
            )

            og_fit, fg_fit, k_fit = popt
            r_squared = self._calculate_r_squared(
                sgs_arr, self._exp_decay(times_arr, *popt)
            )

            # Check if FG hit the lower bound - prediction may be unreliable
            fg_hit_bound = fg_fit <= fg_lower + 0.001
            if fg_hit_bound and r_squared < 0.85:
                return self._failure_result("insufficient_curve_data")

            # Store fitted parameters
            self.og = float(og_fit)
            self.fg = float(fg_fit)
            self.k = float(k_fit)
            self.r_squared = float(r_squared)
            self.model_type = "exponential"

            hours_to_completion = self._calculate_completion_time(
                times_arr[-1], sgs_arr[-1]
            )

            # Calculate linear ETA to recipe target
            linear_target = target_fg if target_fg is not None else fg_fit
            hours_to_target_linear = self._calculate_linear_eta(
                times_arr, sgs_arr, linear_target
            )

            # Calculate confidence score
            confidence = self._calculate_confidence(
                r_squared, fg_fit, target_fg, sgs_arr[-1], og_fit
            )

            # Calculate blended prediction
            blended_hours = self._blend_predictions(
                hours_to_completion, hours_to_target_linear, confidence
            )

            return {
                "fitted": True,
                "model_type": "exponential",
                "predicted_og": self.og,
                "predicted_fg": self.fg,
                "decay_rate": self.k,
                "r_squared": self.r_squared,
                "hours_to_completion": hours_to_completion,
                "hours_to_target_linear": hours_to_target_linear,
                "blended_hours_to_completion": blended_hours,
                "confidence": confidence,
                "reason": None,
            }

        except (RuntimeError, ValueError) as e:
            return self._failure_result(f"fit_failed: {str(e)}")

    def _fit_gompertz(
        self,
        times_arr: np.ndarray,
        sgs_arr: np.ndarray,
        og_guess: float,
        fg_guess: float,
        fg_lower: float,
        target_fg: Optional[float] = None,
    ) -> dict:
        """Fit Gompertz S-curve model."""
        # Initial guesses for Gompertz: mu (max rate), lag (lag time)
        mu_guess = 0.01  # Max rate
        lag_guess = times_arr[-1] * 0.1  # 10% of elapsed time as lag estimate

        try:
            popt, _ = curve_fit(
                self._gompertz,
                times_arr,
                sgs_arr,
                p0=[og_guess, fg_guess, mu_guess, lag_guess],
                bounds=(
                    [1.000, fg_lower, 0.0001, 0],  # lower bounds
                    [1.200, 1.100, 0.5, times_arr[-1]]  # upper bounds
                ),
                maxfev=10000
            )

            og_fit, fg_fit, mu_fit, lag_fit = popt
            r_squared = self._calculate_r_squared(
                sgs_arr, self._gompertz(times_arr, *popt)
            )

            # Check if FG hit the lower bound
            fg_hit_bound = fg_fit <= fg_lower + 0.001
            if fg_hit_bound and r_squared < 0.85:
                return self._failure_result("insufficient_curve_data")

            # Store fitted parameters
            self.og = float(og_fit)
            self.fg = float(fg_fit)
            self.k = float(mu_fit)  # Store mu as k for consistency
            self.r_squared = float(r_squared)
            self.model_type = "gompertz"

            hours_to_completion = self._calculate_completion_time_gompertz(
                times_arr[-1], sgs_arr[-1], og_fit, fg_fit, mu_fit, lag_fit
            )

            # Calculate linear ETA to recipe target
            linear_target = target_fg if target_fg is not None else fg_fit
            hours_to_target_linear = self._calculate_linear_eta(
                times_arr, sgs_arr, linear_target
            )

            # Calculate confidence score
            confidence = self._calculate_confidence(
                r_squared, fg_fit, target_fg, sgs_arr[-1], og_fit
            )

            # Calculate blended prediction
            blended_hours = self._blend_predictions(
                hours_to_completion, hours_to_target_linear, confidence
            )

            return {
                "fitted": True,
                "model_type": "gompertz",
                "predicted_og": self.og,
                "predicted_fg": self.fg,
                "decay_rate": self.k,
                "r_squared": self.r_squared,
                "hours_to_completion": hours_to_completion,
                "hours_to_target_linear": hours_to_target_linear,
                "blended_hours_to_completion": blended_hours,
                "confidence": confidence,
                "reason": None,
            }

        except (RuntimeError, ValueError) as e:
            return self._failure_result(f"fit_failed: {str(e)}")

    def _fit_logistic(
        self,
        times_arr: np.ndarray,
        sgs_arr: np.ndarray,
        og_guess: float,
        fg_guess: float,
        fg_lower: float,
        target_fg: Optional[float] = None,
    ) -> dict:
        """Fit Logistic S-curve model."""
        # Initial guesses: k (rate), t_half (midpoint time)
        k_guess = 0.05
        t_half_guess = times_arr[-1] * 0.5  # Halfway point estimate

        try:
            popt, _ = curve_fit(
                self._logistic,
                times_arr,
                sgs_arr,
                p0=[og_guess, fg_guess, k_guess, t_half_guess],
                bounds=(
                    [1.000, fg_lower, 0.001, 0],  # lower bounds
                    [1.200, 1.100, 1.0, times_arr[-1] * 2]  # upper bounds
                ),
                maxfev=10000
            )

            og_fit, fg_fit, k_fit, t_half_fit = popt
            r_squared = self._calculate_r_squared(
                sgs_arr, self._logistic(times_arr, *popt)
            )

            # Check if FG hit the lower bound
            fg_hit_bound = fg_fit <= fg_lower + 0.001
            if fg_hit_bound and r_squared < 0.85:
                return self._failure_result("insufficient_curve_data")

            # Store fitted parameters
            self.og = float(og_fit)
            self.fg = float(fg_fit)
            self.k = float(k_fit)
            self.r_squared = float(r_squared)
            self.model_type = "logistic"

            hours_to_completion = self._calculate_completion_time_logistic(
                times_arr[-1], sgs_arr[-1], og_fit, fg_fit, k_fit, t_half_fit
            )

            # Calculate linear ETA to recipe target
            linear_target = target_fg if target_fg is not None else fg_fit
            hours_to_target_linear = self._calculate_linear_eta(
                times_arr, sgs_arr, linear_target
            )

            # Calculate confidence score
            confidence = self._calculate_confidence(
                r_squared, fg_fit, target_fg, sgs_arr[-1], og_fit
            )

            # Calculate blended prediction
            blended_hours = self._blend_predictions(
                hours_to_completion, hours_to_target_linear, confidence
            )

            return {
                "fitted": True,
                "model_type": "logistic",
                "predicted_og": self.og,
                "predicted_fg": self.fg,
                "decay_rate": self.k,
                "r_squared": self.r_squared,
                "hours_to_completion": hours_to_completion,
                "hours_to_target_linear": hours_to_target_linear,
                "blended_hours_to_completion": blended_hours,
                "confidence": confidence,
                "reason": None,
            }

        except (RuntimeError, ValueError) as e:
            return self._failure_result(f"fit_failed: {str(e)}")

    def _calculate_completion_time(
        self,
        current_time: float,
        current_sg: float
    ) -> float:
        """Calculate hours until fermentation completes.

        Args:
            current_time: Current time in hours
            current_sg: Current specific gravity

        Returns:
            Hours until completion (0 if already complete)
        """
        if self.fg is None or self.k is None or self.og is None:
            return 0

        # Check if current SG is already at or below predicted FG
        # Allow small tolerance for measurement noise
        if current_sg <= self.fg + 0.001:
            return 0  # Already at FG

        # Check if already complete (rate below threshold)
        # Completion threshold is in SG/day, convert to SG/hour
        threshold_hourly = self.completion_threshold / 24

        # Current rate: dSG/dt = -(OG - FG) * k * exp(-k * t)
        current_rate = abs((self.og - self.fg) * self.k * np.exp(-self.k * current_time))

        if current_rate < threshold_hourly:
            return 0  # Already complete

        # Solve for time when rate equals threshold
        # rate_threshold = (OG - FG) * k * exp(-k * t_complete)
        # exp(-k * t_complete) = rate_threshold / ((OG - FG) * k)
        # -k * t_complete = ln(rate_threshold / ((OG - FG) * k))
        # t_complete = -ln(rate_threshold / ((OG - FG) * k)) / k

        try:
            t_complete = -np.log(threshold_hourly / ((self.og - self.fg) * self.k)) / self.k
            hours_remaining = t_complete - current_time
            return float(max(0, hours_remaining))
        except (ValueError, ZeroDivisionError):
            return 0

    def _calculate_completion_time_gompertz(
        self,
        current_time: float,
        current_sg: float,
        og: float,
        fg: float,
        mu: float,
        lag: float,
    ) -> float:
        """Calculate hours until fermentation completes for Gompertz model.

        Uses numerical search to find when SG drops below threshold.
        """
        # Check if current SG is already at or below predicted FG
        if current_sg <= fg + 0.001:
            return 0  # Already at FG

        # Calculate SG at completion (FG + small margin)
        target_sg = fg + 0.002

        # Search forward in time to find when we hit target
        # Start from current time, step by 1 hour, max 30 days
        for hours_ahead in range(1, 720):
            t = current_time + hours_ahead
            predicted_sg = self._gompertz(t, og, fg, mu, lag)
            if predicted_sg <= target_sg:
                return float(hours_ahead)

        # If not found within 30 days, return large estimate
        return 720.0

    def _calculate_completion_time_logistic(
        self,
        current_time: float,
        current_sg: float,
        og: float,
        fg: float,
        k: float,
        t_half: float,
    ) -> float:
        """Calculate hours until fermentation completes for Logistic model.

        Uses numerical search to find when SG drops below threshold.
        """
        # Check if current SG is already at or below predicted FG
        if current_sg <= fg + 0.001:
            return 0  # Already at FG

        # Calculate SG at completion (FG + small margin)
        target_sg = fg + 0.002

        # Search forward in time to find when we hit target
        for hours_ahead in range(1, 720):
            t = current_time + hours_ahead
            predicted_sg = self._logistic(t, og, fg, k, t_half)
            if predicted_sg <= target_sg:
                return float(hours_ahead)

        # If not found within 30 days, return large estimate
        return 720.0

    def predict(self, future_times: list[float]) -> list[float]:
        """Predict SG at future time points.

        Args:
            future_times: List of time points (hours) to predict SG

        Returns:
            List of predicted SG values
        """
        if self.og is None or self.fg is None or self.k is None:
            msg = "Must call fit() before predict()"
            raise ValueError(msg)

        predictions = []
        for t in future_times:
            sg = self.fg + (self.og - self.fg) * np.exp(-self.k * t)
            predictions.append(float(sg))

        return predictions
