"""ML Pipeline Manager for per-device pipeline instances."""

import logging
from typing import Optional
from .pipeline import MLPipeline
from .config import MLConfig

logger = logging.getLogger(__name__)


class MLPipelineManager:
    """Manages per-device ML pipeline instances.

    Each device (Tilt, iSpindel, etc.) gets its own MLPipeline instance
    to maintain independent state for Kalman filtering, anomaly detection,
    and fermentation predictions.
    """

    def __init__(self, config: Optional[MLConfig] = None):
        """Initialize manager with optional ML configuration.

        Args:
            config: ML configuration (uses defaults if not provided)
        """
        self.pipelines: dict[str, MLPipeline] = {}
        self.config = config or MLConfig()
        logger.info(f"MLPipelineManager initialized with config: {self.config}")

    def get_or_create_pipeline(self, device_id: str) -> MLPipeline:
        """Get existing pipeline or create new one for device.

        Args:
            device_id: Unique device identifier

        Returns:
            MLPipeline instance for this device
        """
        if device_id not in self.pipelines:
            logger.info(f"Creating new ML pipeline for device: {device_id}")
            self.pipelines[device_id] = MLPipeline(self.config)
        return self.pipelines[device_id]

    def reset_pipeline(
        self,
        device_id: str,
        initial_sg: float = 1.050,
        initial_temp: float = 20.0
    ):
        """Reset pipeline state for new batch.

        Args:
            device_id: Unique device identifier
            initial_sg: Starting specific gravity
            initial_temp: Starting temperature (°C)
        """
        if device_id in self.pipelines:
            logger.info(f"Resetting ML pipeline for device: {device_id}")
            self.pipelines[device_id].reset(initial_sg, initial_temp)

    def remove_pipeline(self, device_id: str):
        """Remove pipeline for device (cleanup).

        Args:
            device_id: Unique device identifier
        """
        if device_id in self.pipelines:
            logger.info(f"Removing ML pipeline for device: {device_id}")
            del self.pipelines[device_id]

    def get_pipeline_count(self) -> int:
        """Get count of active pipelines."""
        return len(self.pipelines)

    def process_reading(
        self,
        device_id: str,
        sg: float,
        temp: float,
        rssi: float,
        time_hours: float,
        ambient_temp: Optional[float] = None,
        heater_on: Optional[bool] = None,
        cooler_on: Optional[bool] = None,
        target_temp: Optional[float] = None,
    ) -> dict:
        """Process a reading through the device's ML pipeline.

        Args:
            device_id: Unique device identifier
            sg: Specific gravity reading
            temp: Temperature reading (°C)
            rssi: Bluetooth signal strength (dBm)
            time_hours: Time since fermentation start (hours)
            ambient_temp: Ambient/room temperature (°C)
            heater_on: Current heater state (for MPC learning)
            cooler_on: Current cooler state (for MPC learning)
            target_temp: Target temperature (°C)

        Returns:
            Flattened dictionary with ML outputs for database storage:
            - sg_filtered, temp_filtered: Kalman filtered values
            - confidence: Reading quality (0.0-1.0)
            - sg_rate, temp_rate: Derivatives
            - is_anomaly, anomaly_score, anomaly_reasons: Anomaly detection
        """
        pipeline = self.get_or_create_pipeline(device_id)
        nested_result = pipeline.process_reading(
            sg=sg,
            temp=temp,
            rssi=rssi,
            time_hours=time_hours,
            ambient_temp=ambient_temp,
            heater_on=heater_on,
            cooler_on=cooler_on,
            target_temp=target_temp,
        )

        # Flatten nested structure for database storage
        flat_result = {}

        # Extract Kalman filter outputs
        if nested_result.get("kalman"):
            kalman = nested_result["kalman"]
            flat_result["sg_filtered"] = kalman.get("sg_filtered")
            flat_result["temp_filtered"] = kalman.get("temp_filtered")
            flat_result["confidence"] = kalman.get("confidence")
            flat_result["sg_rate"] = kalman.get("sg_rate")
            flat_result["temp_rate"] = kalman.get("temp_rate")

        # Extract anomaly detection outputs
        if nested_result.get("anomaly"):
            anomaly = nested_result["anomaly"]
            flat_result["is_anomaly"] = anomaly.get("is_anomaly", False)
            flat_result["anomaly_score"] = anomaly.get("score")
            flat_result["anomaly_reasons"] = anomaly.get("reasons", [])
        else:
            flat_result["is_anomaly"] = False
            flat_result["anomaly_reasons"] = []

        return flat_result

    def get_device_state(self, device_id: str) -> Optional[dict]:
        """Get current ML state and predictions for a device.

        Args:
            device_id: Unique device identifier

        Returns:
            Dictionary with device ML state including predictions, or None if no pipeline exists
        """
        if device_id not in self.pipelines:
            return None

        pipeline = self.pipelines[device_id]

        # If we have enough history for predictions, get latest prediction
        if pipeline.curve_fitter and len(pipeline.sg_history) >= self.config.prediction_min_readings:
            prediction_result = pipeline.curve_fitter.fit(
                times=pipeline.time_history,
                sgs=pipeline.sg_history,
            )

            return {
                "predictions": prediction_result,
                "history_count": len(pipeline.sg_history)
            }

        return {
            "predictions": None,
            "history_count": len(pipeline.sg_history)
        }

    async def reload_from_database(
        self,
        device_id: str,
        batch_id: int,
        db_session
    ) -> dict:
        """Reload ML pipeline history from database readings.

        This forces the ML model to recalculate predictions based on
        current database state. Useful after data corrections or
        calibration changes.

        Args:
            device_id: Device identifier
            batch_id: Batch to load readings from
            db_session: Database session

        Returns:
            Dictionary with reload results:
            - success: Whether reload succeeded
            - readings_loaded: Number of readings loaded
            - error: Error message if failed
        """
        from sqlalchemy import select
        from backend.models import Reading

        try:
            # Get or create pipeline
            pipeline = self.get_or_create_pipeline(device_id)

            # Query readings from database
            # Use filtered values and order by timestamp
            query = (
                select(Reading)
                .where(Reading.batch_id == batch_id)
                .where(Reading.device_id == device_id)
                .order_by(Reading.timestamp)
            )

            result = await db_session.execute(query)
            readings = result.scalars().all()

            if not readings:
                return {
                    "success": False,
                    "readings_loaded": 0,
                    "error": "No readings found for batch"
                }

            # Extract data for pipeline
            sgs = []
            temps = []
            times = []

            batch_start = readings[0].timestamp
            for reading in readings:
                # Use filtered values if available, otherwise calibrated
                sg = reading.sg_filtered if reading.sg_filtered is not None else reading.sg_calibrated
                temp = reading.temp_filtered if reading.temp_filtered is not None else reading.temp_calibrated

                if sg is None or temp is None:
                    continue  # Skip readings with missing data

                # Calculate hours since batch start
                time_delta = reading.timestamp - batch_start
                hours = time_delta.total_seconds() / 3600

                sgs.append(float(sg))
                temps.append(float(temp))
                times.append(float(hours))

            if len(sgs) < self.config.prediction_min_readings:
                return {
                    "success": False,
                    "readings_loaded": len(sgs),
                    "error": f"Insufficient readings (need {self.config.prediction_min_readings}, got {len(sgs)})"
                }

            # Load history into pipeline
            pipeline.load_history(sgs=sgs, temps=temps, times=times)

            logger.info(
                f"Reloaded {len(sgs)} readings from database for device {device_id}, batch {batch_id}"
            )

            return {
                "success": True,
                "readings_loaded": len(sgs),
                "error": None
            }

        except Exception as e:
            logger.error(f"Failed to reload from database: {e}")
            return {
                "success": False,
                "readings_loaded": 0,
                "error": str(e)
            }
