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
        # Which batch each device pipeline belongs to. A reading for another
        # batch gets a fresh pipeline so no state leaks across batches (tilt_ui-89af).
        self.pipeline_batch: dict[str, Optional[int]] = {}
        self.config = config or MLConfig()
        logger.info(f"MLPipelineManager initialized with config: {self.config}")

    def get_or_create_pipeline(self, device_id: str, batch_id: Optional[int] = None) -> MLPipeline:
        """Get the device's pipeline, or a fresh one if it belongs to another batch.

        Args:
            device_id: Unique device identifier
            batch_id: Batch the reading/reload is for (None = don't check)

        Returns:
            MLPipeline instance for this device
        """
        stale = (
            batch_id is not None
            and device_id in self.pipelines
            and self.pipeline_batch.get(device_id) != batch_id
        )
        if device_id not in self.pipelines or stale:
            logger.info(f"Creating new ML pipeline for device {device_id} (batch {batch_id})")
            self.pipelines[device_id] = MLPipeline(self.config)
        if batch_id is not None:
            self.pipeline_batch[device_id] = batch_id
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
            self.pipeline_batch.pop(device_id, None)

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
        batch_id: Optional[int] = None,
    ) -> dict:
        """Process a reading through the device's ML pipeline.

        Args:
            device_id: Unique device identifier
            sg: Specific gravity reading
            temp: Temperature reading (°C)
            rssi: Bluetooth signal strength (dBm)
            time_hours: Time since fermentation start (hours)
            batch_id: Batch the reading belongs to (fresh pipeline on change)

        Returns:
            Flattened dictionary with ML outputs for database storage:
            - sg_filtered, temp_filtered: Kalman filtered values
            - confidence: Reading quality (0.0-1.0)
            - sg_rate, temp_rate: Derivatives
            - is_anomaly, anomaly_score, anomaly_reasons: Anomaly detection
        """
        pipeline = self.get_or_create_pipeline(device_id, batch_id)
        nested_result = pipeline.process_reading(
            sg=sg,
            temp=temp,
            rssi=rssi,
            time_hours=time_hours,
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
            reason = anomaly.get("reason")
            flat_result["anomaly_reasons"] = [reason] if reason and reason not in ("normal", "insufficient_history") else []
            flat_result["sg_slope_12h"] = anomaly.get("sg_slope_12h")
        else:
            flat_result["is_anomaly"] = False
            flat_result["anomaly_reasons"] = []

        return flat_result

    def get_device_state(
        self,
        device_id: str,
        expected_fg: Optional[float] = None,
        model: str = "auto",
        batch_id: Optional[int] = None,
    ) -> Optional[dict]:
        """Get current ML state and predictions for a device.

        Args:
            device_id: Unique device identifier
            expected_fg: Expected final gravity from recipe (constrains predictions)
            model: Prediction model to use: "exponential", "gompertz", "logistic", or "auto"

        Returns:
            Dictionary with device ML state including predictions, or None if no pipeline exists
        """
        if device_id not in self.pipelines:
            return None
        if batch_id is not None and self.pipeline_batch.get(device_id) != batch_id:
            return None  # pipeline holds another batch's state

        pipeline = self.pipelines[device_id]

        # If we have enough history for predictions, get latest prediction
        if pipeline.curve_fitter and len(pipeline.sg_history) >= self.config.prediction_min_readings:
            prediction_result = pipeline.curve_fitter.fit(
                times=pipeline.time_history,
                sgs=pipeline.sg_history,
                expected_fg=expected_fg,
                model=model,
            )

            return {
                "predictions": prediction_result,
                "history_count": len(pipeline.sg_history)
            }

        return {
            "predictions": None,
            "history_count": len(pipeline.sg_history)
        }

    async def predict_batch(self, db_session, batch, model: str = "auto") -> dict:
        """The one prediction for a batch: API, assistant and chart all use it (tilt_ui-3kbr).

        ``batch`` needs ``recipe`` loaded. ``hours_to_completion`` is the
        blended estimate (curve + linear, weighted by confidence); the
        curve-only value runs 35-70 h short early on, so it is never the headline.
        """
        from datetime import datetime, timedelta, timezone

        device_id = batch.device_id
        if batch.status in ("completed", "archived"):
            # Historical batches never share the device's live pipeline, which now
            # belongs to whatever batch the device is fermenting (tilt_ui-89af).
            device_id = f"batch-{batch.id}"
        elif not device_id:
            return {"available": False, "error": "No device linked"}

        expected_fg = batch.recipe.fg if batch.recipe else None
        state = self.get_device_state(device_id, expected_fg=expected_fg, model=model, batch_id=batch.id)
        # Reload from the database if the pipeline is empty or short on history
        if not state or state.get("history_count", 0) < 10:
            await self.reload_from_database(device_id, batch.id, db_session)
            state = self.get_device_state(device_id, expected_fg=expected_fg, model=model, batch_id=batch.id)

        if not state or not state.get("predictions"):
            return {"available": False}
        predictions = state["predictions"]
        # A dict with fitted=False means the fit failed or was refused
        if not predictions.get("fitted"):
            return {"available": False, "reason": predictions.get("reason", "unknown")}

        curve_hours = predictions.get("hours_to_completion")
        blended_hours = predictions.get("blended_hours_to_completion")
        hours = blended_hours if blended_hours is not None else curve_hours
        # Hours are from NOW, not from batch start
        completion = None
        if hours is not None and hours > 0:
            completion = datetime.now(timezone.utc) + timedelta(hours=hours)

        return {
            "available": True,
            "predicted_fg": predictions.get("predicted_fg"),
            "predicted_og": predictions.get("predicted_og"),
            "estimated_completion": completion.isoformat() if completion else None,
            "hours_to_completion": hours,
            "hours_to_target_linear": predictions.get("hours_to_target_linear"),
            "curve_hours_to_completion": curve_hours,
            "confidence": predictions.get("confidence"),
            "model_type": predictions.get("model_type"),
            "r_squared": predictions.get("r_squared"),
            "num_readings": state.get("history_count", 0),
        }

    async def warm_active_batches(self, session_factory) -> int:
        """Reload history for every active batch with a device (startup).

        Without this the in-memory windows (12 h stall slope, Kalman) start
        empty after each restart (tilt_ui-zbhm). Returns batches warmed.
        """
        from sqlalchemy import select
        from backend.models import Batch

        async with session_factory() as db:
            rows = (await db.execute(
                select(Batch.id, Batch.device_id).where(
                    Batch.status.in_(("fermenting", "conditioning")),
                    Batch.deleted_at.is_(None),
                    Batch.device_id.is_not(None),
                )
            )).all()
            warmed = 0
            for batch_id, device_id in rows:
                result = await self.reload_from_database(device_id, batch_id, db)
                warmed += bool(result.get("success"))
        logger.info(f"Warmed ML pipelines for {warmed}/{len(rows)} active batches")
        return warmed

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
            pipeline = self.get_or_create_pipeline(device_id, batch_id)

            # Query ALL readings for this batch (from any device)
            # This allows ML predictions to continue when switching devices mid-ferment
            # Readings are calibrated at ingestion, so mixing devices is fine for ML
            query = (
                select(Reading)
                .where(Reading.batch_id == batch_id)
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

            # Same time origin as live ingestion (batch.start_time), else the
            # replayed window and the next live reading disagree (tilt_ui-zbhm).
            from backend.models import Batch
            batch_start = (await db_session.execute(
                select(Batch.start_time).where(Batch.id == batch_id)
            )).scalar_one_or_none() or readings[0].timestamp
            for reading in readings:
                # Curve fitting must use calibrated (real measurement)
                # values, not Kalman-filtered ones. The filter can take
                # several readings to converge — until it does, the
                # filtered SG can sit far below the actual measurement
                # (observed: filtered ~1.005 while calibrated ~1.045).
                # That bogus head-of-history then makes sg_drop negative
                # and the curve fitter refuses with "insufficient
                # fermentation progress" even though the recipe is 96%
                # attenuated. Calibrated falls back to filtered only when
                # missing.
                sg = reading.sg_calibrated if reading.sg_calibrated is not None else reading.sg_filtered
                temp = reading.temp_calibrated if reading.temp_calibrated is not None else reading.temp_filtered

                if sg is None or temp is None:
                    continue  # Skip readings with missing data

                # Calculate hours since batch start
                ts, start = reading.timestamp, batch_start
                if (ts.tzinfo is None) != (start.tzinfo is None):
                    ts, start = ts.replace(tzinfo=None), start.replace(tzinfo=None)
                time_delta = ts - start
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
