"""ML pipeline orchestrator.

Coordinates the ML components (Kalman filtering, anomaly detection,
predictions) to provide a unified interface for processing fermentation
readings. Temperature control is the hysteresis controller in
backend/temp_controller.py; the MPC experiment was removed (tilt_ui-29im).

The pipeline:
1. Filters raw readings through Kalman filter
2. Checks for anomalies
3. Fits fermentation curve and predicts completion (if enough history)
"""

from typing import Optional
from backend.ml.config import MLConfig
from backend.ml.sensor_fusion.kalman import TiltKalmanFilter
from backend.ml.anomaly.detector import FermentationAnomalyDetector
from backend.ml.predictions.curve_fitter import FermentationCurveFitter


class MLPipeline:
    """Orchestrates all ML components for fermentation monitoring.

    The pipeline maintains state across readings and coordinates:
    - Sensor fusion (Kalman filtering)
    - Anomaly detection
    - Fermentation predictions (curve fitting)

    Each component can be individually enabled/disabled via MLConfig.
    """

    def __init__(self, config: Optional[MLConfig] = None):
        """Initialize the ML pipeline.

        Args:
            config: ML configuration (uses defaults if not provided)
        """
        self.config = config or MLConfig()

        # Initialize components based on config
        if self.config.enable_kalman_filter:
            self.kalman_filter = TiltKalmanFilter(
                process_noise_sg=self.config.kalman_process_noise_sg,
                process_noise_temp=self.config.kalman_process_noise_temp,
                measurement_noise_sg=self.config.kalman_measurement_noise_sg,
                measurement_noise_temp=self.config.kalman_measurement_noise_temp,
            )
        else:
            self.kalman_filter = None

        if self.config.enable_anomaly_detection:
            self.anomaly_detector = FermentationAnomalyDetector()
        else:
            self.anomaly_detector = None

        if self.config.enable_predictions:
            self.curve_fitter = FermentationCurveFitter(
                min_readings=self.config.prediction_min_readings,
                completion_threshold=self.config.prediction_completion_threshold,
            )
        else:
            self.curve_fitter = None

        # History for predictions
        self.sg_history: list[float] = []
        self.temp_history: list[float] = []
        self.time_history: list[float] = []

    def process_reading(
        self,
        sg: float,
        temp: float,
        rssi: float,
        time_hours: float,
    ) -> dict:
        """Process a fermentation reading through the ML pipeline.

        Args:
            sg: Raw specific gravity reading
            temp: Raw temperature reading (°C)
            rssi: Bluetooth signal strength (dBm)
            time_hours: Time since fermentation start (hours)

        Returns:
            Dictionary with results from each component:
            - kalman: Filtered readings and rates
            - anomaly: Anomaly detection results
            - predictions: Fermentation predictions (if enough history)
        """
        result = {}

        # Calculate time delta for Kalman filter
        if self.time_history:
            dt_hours = time_hours - self.time_history[-1]
            dt_hours = max(dt_hours, 1 / 60)  # At least 1 minute
        else:
            dt_hours = 1 / 60  # Default: 1 minute

        # Stage 1: Kalman filtering
        if self.kalman_filter:
            kalman_result = self.kalman_filter.update(
                sg=sg,
                temp=temp,
                rssi=rssi,
                dt_hours=dt_hours,
            )
            result["kalman"] = kalman_result

            # Use filtered values for downstream components
            filtered_sg = kalman_result["sg_filtered"]
            filtered_temp = kalman_result["temp_filtered"]
        else:
            # No filtering, use raw values
            filtered_sg = sg
            filtered_temp = temp
            result["kalman"] = None

        # Stage 2: Anomaly detection
        if self.anomaly_detector:
            anomaly_result = self.anomaly_detector.check_reading(
                sg=filtered_sg,
                time_hours=time_hours,
                raw_sg=sg,
            )
            result["anomaly"] = anomaly_result
        else:
            result["anomaly"] = None

        # History for curve fitting holds the measurement (calibrated), not the
        # Kalman output: the same values reload_from_database loads, so a fit
        # does not change after a restart (tilt_ui-3kbr).
        self.sg_history.append(sg)
        self.temp_history.append(temp)
        self.time_history.append(time_hours)

        # Stage 3: Predictions (curve fitting)
        if self.curve_fitter and len(self.sg_history) >= self.config.prediction_min_readings:
            prediction_result = self.curve_fitter.fit(
                times=self.time_history,
                sgs=self.sg_history,
            )
            result["predictions"] = prediction_result
        else:
            result["predictions"] = None

        return result

    def reset(self, initial_sg: float = 1.050, initial_temp: float = 20.0) -> None:
        """Reset pipeline state for a new fermentation batch.

        Args:
            initial_sg: Starting specific gravity
            initial_temp: Starting temperature (°C)
        """
        # Reset Kalman filter
        if self.kalman_filter:
            self.kalman_filter.reset(sg=initial_sg, temp=initial_temp)

        # Reset anomaly detector
        if self.anomaly_detector:
            self.anomaly_detector.reset()

        # Clear history
        self.sg_history = []
        self.temp_history = []
        self.time_history = []

        # Note: curve_fitter doesn't maintain state, so no reset needed

    def load_history(
        self,
        sgs: list[float],
        temps: list[float],
        times: list[float],
    ) -> None:
        """Load historical data into the pipeline for predictions.

        This is useful for initializing the pipeline from database history
        or for recalculating predictions after data corrections.

        Args:
            sgs: Specific gravity readings (filtered/calibrated)
            temps: Temperature readings (filtered/calibrated, °C)
            times: Time points (hours since fermentation start)
        """
        if len(sgs) != len(temps) or len(sgs) != len(times):
            raise ValueError("sgs, temps, and times must have same length")

        # Store history
        self.sg_history = list(sgs)
        self.temp_history = list(temps)
        self.time_history = list(times)

        # Reset Kalman filter to last reading state
        if self.kalman_filter and len(sgs) > 0:
            self.kalman_filter.reset(sg=sgs[-1], temp=temps[-1])

        # Refill the anomaly detector's trailing window from history, so the
        # 12 h stall slope survives restarts instead of going blind for 12 h
        # (tilt_ui-zbhm). Only the window is replayed; flags are discarded.
        if self.anomaly_detector:
            self.anomaly_detector.reset()
            if times:
                since = times[-1] - self.anomaly_detector.slope_window_hours - 1.0
                for t, s in zip(times, sgs):
                    if t >= since:
                        self.anomaly_detector.check_reading(sg=s, time_hours=t)
