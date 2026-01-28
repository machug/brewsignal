"""Ingest Manager for processing hydrometer readings.

This is the central pipeline for ingesting readings from any device type:
1. Parse payload via AdapterRouter
2. Get or create Device record
3. Convert units to standard (SG, Fahrenheit)
4. Apply device calibration
5. Link to active batch (fermenting or conditioning)
6. Store Reading in database (only if device paired AND batch active)
7. Broadcast via WebSocket (for all paired devices)

Storage behavior matches Tilt BLE scanner in main.py:
- Planning status: Readings visible on dashboard but NOT stored
- Fermenting/Conditioning: Readings stored AND linked to batch
"""

import json
import logging
import time
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..ingest import AdapterRouter, HydrometerReading, ReadingStatus
from ..models import Batch, Device, Reading, Recipe, serialize_datetime_to_utc
from ..state import update_reading
from ..websocket import manager as ws_manager
from .calibration import calibration_service
from .batch_linker import link_reading_to_batch
from .alert_service import detect_and_persist_alerts
from ..routers.config import get_config_value
from sqlalchemy.orm import selectinload
from ..mqtt_manager import publish_batch_reading

logger = logging.getLogger(__name__)

# Valid ranges for outlier filtering
SG_MIN, SG_MAX = 0.500, 1.200
TEMP_MIN_F, TEMP_MAX_F = 32.0, 212.0  # Fahrenheit (freezing to boiling)

# Config cache TTL in seconds (refresh every 30s to pick up changes reasonably quickly)
CONFIG_CACHE_TTL = 30


class IngestManager:
    """Manages the full ingest pipeline for all hydrometer types."""

    def __init__(self):
        self.adapter_router = AdapterRouter()
        # Cache for config values to avoid DB query on every reading
        self._min_rssi_cache: Optional[int] = None
        self._min_rssi_cache_time: float = 0
        # Cache for batch start times (batch_id -> datetime)
        self._batch_start_cache: dict[int, datetime] = {}

    def _get_ml_manager(self):
        """Get the ML pipeline manager from main module."""
        from ..main import get_ml_manager
        return get_ml_manager()

    async def _get_batch_start_time(self, db: AsyncSession, batch_id: int) -> Optional[datetime]:
        """Get the start time for a batch (cached for performance)."""
        if batch_id in self._batch_start_cache:
            return self._batch_start_cache[batch_id]

        query = select(Batch.start_time).where(Batch.id == batch_id)
        result = await db.execute(query)
        start_date = result.scalar_one_or_none()

        if start_date:
            self._batch_start_cache[batch_id] = start_date
        return start_date

    def _calculate_time_hours(
        self,
        reading_time: datetime,
        batch_start: Optional[datetime],
    ) -> float:
        """Calculate hours since batch start for ML pipeline.

        Falls back to 0.0 if batch start time is not available.
        """
        if not batch_start:
            return 0.0

        # Ensure both times are timezone-aware
        if batch_start.tzinfo is None:
            batch_start = batch_start.replace(tzinfo=timezone.utc)
        if reading_time.tzinfo is None:
            reading_time = reading_time.replace(tzinfo=timezone.utc)

        delta = reading_time - batch_start
        return max(0.0, delta.total_seconds() / 3600)

    async def _get_min_rssi(self, db: AsyncSession) -> Optional[int]:
        """Get min_rssi config with caching to reduce DB queries."""
        now = time.monotonic()
        if now - self._min_rssi_cache_time > CONFIG_CACHE_TTL:
            self._min_rssi_cache = await get_config_value(db, "min_rssi")
            self._min_rssi_cache_time = now
        return self._min_rssi_cache

    async def _get_alert_context(
        self,
        db: AsyncSession,
        batch_id: int,
        current_sg: Optional[float],
    ) -> dict:
        """Get context needed for alert detection (yeast temp range, progress)."""
        context = {
            "yeast_temp_min": None,
            "yeast_temp_max": None,
            "progress_percent": None,
        }

        # Fetch batch with recipe and yeast eagerly loaded
        stmt = (
            select(Batch)
            .where(Batch.id == batch_id)
            .options(
                selectinload(Batch.recipe).selectinload(Recipe.yeast),
                selectinload(Batch.yeast_strain),
            )
        )
        result = await db.execute(stmt)
        batch = result.scalar_one_or_none()

        if not batch:
            return context

        # Get yeast temperature range (prefer batch override, then recipe yeast)
        yeast = batch.yeast_strain or (batch.recipe.yeast if batch.recipe else None)
        if yeast:
            context["yeast_temp_min"] = yeast.temp_low
            context["yeast_temp_max"] = yeast.temp_high

        # Calculate progress if we have OG and current SG
        og = batch.og or (batch.recipe.og if batch.recipe else None)
        fg = batch.fg or (batch.recipe.fg if batch.recipe else None)

        if og and fg and current_sg:
            expected_drop = og - fg
            if expected_drop > 0:
                actual_drop = og - current_sg
                progress = (actual_drop / expected_drop) * 100
                context["progress_percent"] = min(max(progress, 0), 100)

        return context

    async def ingest(
        self,
        db: AsyncSession,
        payload: dict,
        source_protocol: str = "http",
        auth_token: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> Optional[Reading]:
        """Process a hydrometer payload through the full pipeline.

        Args:
            db: Database session
            payload: Raw payload from device
            source_protocol: Protocol used (http, mqtt, ble)
            auth_token: Optional auth token from request header
            user_id: Optional user ID for cloud mode (from ingest token)

        Returns:
            Reading model if successful, None if parsing failed
        """
        # Step 1: Parse payload
        reading = self.adapter_router.route(payload, source_protocol=source_protocol)
        if not reading:
            logger.warning("Failed to parse payload: %s", payload)
            return None

        # Step 2: Get or create device
        device = await self._get_or_create_device(db, reading, auth_token, user_id)

        # Step 3: Validate auth token if device has one configured
        if not self._validate_auth(device, auth_token):
            logger.warning(
                "Auth token mismatch for device %s",
                reading.device_id,
            )
            return None

        # Step 4: Convert units to standard (SG, Fahrenheit)
        reading = calibration_service.convert_units(reading)

        # Step 5: Check RSSI threshold (filter weak signals)
        min_rssi = await self._get_min_rssi(db)
        if reading.rssi is not None and min_rssi is not None and reading.rssi < min_rssi:
            logger.debug(
                "Filtered reading: RSSI %d < threshold %d (device %s)",
                reading.rssi,
                min_rssi,
                reading.device_id,
            )
            return None

        # Step 6: Apply device calibration
        reading = await calibration_service.calibrate_device_reading(db, device, reading)

        # Step 7: Link reading to active batch (if any)
        # Returns batch_id only if batch is fermenting or conditioning
        batch_id = await link_reading_to_batch(db, device.id)

        # Step 8: Process through ML pipeline if available
        ml_outputs = {}
        if device.paired and batch_id is not None:
            ml_manager = self._get_ml_manager()
            if ml_manager:
                try:
                    # Get batch start time for time_hours calculation
                    batch_start = await self._get_batch_start_time(db, batch_id)
                    reading_time = reading.timestamp or datetime.now(timezone.utc)
                    time_hours = self._calculate_time_hours(reading_time, batch_start)

                    # Process through ML pipeline (synchronous call)
                    ml_outputs = ml_manager.process_reading(
                        device_id=device.id,
                        sg=reading.gravity,
                        temp=reading.temperature,
                        rssi=reading.rssi or -70,  # Default RSSI for HTTP devices
                        time_hours=time_hours,
                    )
                    logger.debug(
                        "ML pipeline processed reading for %s: filtered_sg=%.4f",
                        device.id,
                        ml_outputs.get("sg_filtered", 0),
                    )
                except Exception as e:
                    logger.error("ML pipeline failed for %s: %s", device.id, e)
                    # ML failure is non-fatal - continue with empty outputs

        # Step 9: Update device last_seen (always, regardless of storage)
        device.last_seen = reading.timestamp
        if reading.battery_voltage is not None:
            device.battery_voltage = reading.battery_voltage

        # Step 10: Store reading in database ONLY if:
        # - Device is paired (prevents pollution from unknown devices)
        # - Batch is active (fermenting or conditioning)
        # This matches the Tilt BLE behavior in main.py
        db_reading = None
        if device.paired and batch_id is not None:
            db_reading = await self._store_reading(db, device, reading, batch_id, ml_outputs)

            # Step 10a: Detect and persist alerts
            try:
                # Build live_reading dict for alert detection
                live_reading = {
                    "temp": reading.temperature,
                    "sg": reading.gravity,
                    "sg_rate": ml_outputs.get("sg_rate"),
                    "is_anomaly": ml_outputs.get("is_anomaly", False),
                    "anomaly_score": ml_outputs.get("anomaly_score"),
                    "anomaly_reasons": ml_outputs.get("anomaly_reasons"),
                }

                # Get alert context (yeast temp range, progress)
                alert_context = await self._get_alert_context(
                    db, batch_id, reading.gravity
                )

                # Detect and persist alerts
                await detect_and_persist_alerts(
                    db=db,
                    batch_id=batch_id,
                    device_id=device.id,
                    reading=db_reading,
                    live_reading=live_reading,
                    yeast_temp_min=alert_context.get("yeast_temp_min"),
                    yeast_temp_max=alert_context.get("yeast_temp_max"),
                    progress_percent=alert_context.get("progress_percent"),
                )
            except Exception as e:
                logger.warning("Alert detection failed: %s", e)
                # Alert detection failure is non-fatal

            # Step 10b: Publish to MQTT for Home Assistant (fire-and-forget)
            try:
                # Get batch info for MQTT context
                batch = await db.get(Batch, batch_id)
                if batch:
                    await publish_batch_reading(
                        batch_id=batch_id,
                        gravity=reading.gravity,
                        temperature=reading.temperature,
                        og=batch.measured_og,
                        start_time=batch.start_time,
                        status=batch.status,
                    )
            except Exception as e:
                logger.warning("MQTT publish failed: %s", e)
                # MQTT failure is non-fatal

        await db.commit()

        # Step 11: Broadcast via WebSocket for paired devices
        # (live readings visible regardless of batch status)
        if device.paired:
            await self._broadcast_reading(device, reading, ml_outputs)

        logger.info(
            "Ingested %s reading: device=%s, sg=%.4f, temp=%.1f, stored=%s",
            reading.device_type,
            reading.device_id,
            reading.gravity or 0,
            reading.temperature or 0,
            "yes" if db_reading else "no (not fermenting)",
        )

        return db_reading

    async def _get_or_create_device(
        self,
        db: AsyncSession,
        reading: HydrometerReading,
        auth_token: Optional[str],
        user_id: Optional[str] = None,
    ) -> Device:
        """Get existing device or create a new one from reading data."""
        # Build kwargs based on device type
        kwargs = {}

        if reading.device_type == "tilt":
            # Tilt-specific: extract color from device_id
            kwargs["color"] = reading.device_id
            kwargs["native_gravity_unit"] = "sg"
            kwargs["native_temp_unit"] = "f"

        elif reading.device_type in ("ispindel", "gravitymon"):
            kwargs["native_gravity_unit"] = str(reading.gravity_unit.value)
            kwargs["native_temp_unit"] = str(reading.temperature_unit.value)

        # Pass user_id for cloud mode multi-tenant support
        if user_id:
            kwargs["user_id"] = user_id

        device = await calibration_service.get_or_create_device(
            db=db,
            device_id=reading.device_id,
            device_type=reading.device_type,
            name=reading.device_id,
            **kwargs,
        )

        return device

    def _validate_auth(self, device: Device, provided_token: Optional[str]) -> bool:
        """Validate auth token against device configuration.

        Returns True if:
        - Device has no auth_token configured (open)
        - Provided token matches device auth_token
        """
        if not device.auth_token:
            return True  # No auth required

        return device.auth_token == provided_token

    def _validate_reading(self, reading: HydrometerReading) -> str:
        """Validate reading values and return appropriate status.

        Returns 'invalid' if SG or temperature are outside valid ranges,
        otherwise returns the reading's original status.

        Note: Temperature validation assumes Fahrenheit. The convert_units() method
        (called earlier in the pipeline) converts Celsius to Fahrenheit, so by the
        time we reach validation, all temperatures are in Fahrenheit.
        """
        # Check SG (use calibrated if available, else raw)
        sg = reading.gravity if reading.gravity is not None else reading.gravity_raw
        if sg is not None and not (SG_MIN <= sg <= SG_MAX):
            logger.warning(
                "Outlier SG detected: %.4f (valid: %.3f-%.3f) for device %s",
                sg, SG_MIN, SG_MAX, reading.device_id
            )
            return ReadingStatus.INVALID.value

        # Check temperature (use calibrated if available, else raw)
        # Temperature is in Fahrenheit after convert_units() call
        temp = reading.temperature if reading.temperature is not None else reading.temperature_raw
        if temp is not None and not (TEMP_MIN_F <= temp <= TEMP_MAX_F):
            logger.warning(
                "Outlier temperature detected: %.1f°F (valid: %.0f-%.0f) for device %s",
                temp, TEMP_MIN_F, TEMP_MAX_F, reading.device_id
            )
            return ReadingStatus.INVALID.value

        return reading.status.value

    async def _store_reading(
        self,
        db: AsyncSession,
        device: Device,
        reading: HydrometerReading,
        batch_id: Optional[int] = None,
        ml_outputs: Optional[dict] = None,
    ) -> Reading:
        """Store reading in database with optional batch linkage and ML outputs."""
        # Validate reading and get status (may be 'invalid' for outliers)
        status = self._validate_reading(reading)
        ml_outputs = ml_outputs or {}

        # Serialize anomaly_reasons if present
        anomaly_reasons = ml_outputs.get("anomaly_reasons")
        anomaly_reasons_json = None
        if anomaly_reasons:
            anomaly_reasons_json = json.dumps(anomaly_reasons)

        db_reading = Reading(
            device_id=device.id,
            batch_id=batch_id,
            device_type=reading.device_type,
            timestamp=reading.timestamp or datetime.now(timezone.utc),
            sg_raw=reading.gravity_raw,
            sg_calibrated=reading.gravity,
            temp_raw=reading.temperature_raw,
            temp_calibrated=reading.temperature,
            rssi=reading.rssi,
            battery_voltage=reading.battery_voltage,
            battery_percent=reading.battery_percent,
            angle=reading.angle,
            source_protocol=reading.source_protocol,
            status=status,
            is_pre_filtered=reading.is_pre_filtered,
            # ML outputs
            sg_filtered=ml_outputs.get("sg_filtered"),
            temp_filtered=ml_outputs.get("temp_filtered"),
            confidence=ml_outputs.get("confidence"),
            sg_rate=ml_outputs.get("sg_rate"),
            temp_rate=ml_outputs.get("temp_rate"),
            is_anomaly=ml_outputs.get("is_anomaly", False),
            anomaly_score=ml_outputs.get("anomaly_score"),
            anomaly_reasons=anomaly_reasons_json,
        )

        db.add(db_reading)
        await db.flush()

        return db_reading

    def _build_reading_payload(
        self,
        device: Device,
        reading: HydrometerReading,
        ml_outputs: Optional[dict] = None,
    ) -> dict:
        """Build WebSocket payload in legacy-compatible format.

        The payload format is compatible with existing UI consumers:
        - id: device identifier (required)
        - color: Tilt color or device name for non-Tilt
        - beer_name: current beer assignment
        - original_gravity: OG if set
        - sg/sg_raw: calibrated and raw gravity
        - temp/temp_raw: calibrated and raw temperature
        - rssi: signal strength
        - last_seen: ISO timestamp

        Additional fields for non-Tilt devices:
        - device_type: type of device
        - angle: tilt angle (iSpindel)
        - battery_voltage/battery_percent: battery status

        ML pipeline outputs (when available):
        - sg_filtered, temp_filtered: Kalman filtered values
        - confidence: Reading quality (0.0-1.0)
        - sg_rate, temp_rate: Derivatives
        - is_anomaly, anomaly_score, anomaly_reasons: Anomaly detection
        """
        timestamp = reading.timestamp or datetime.now(timezone.utc)
        ml_outputs = ml_outputs or {}

        payload = {
            # Core fields (legacy format)
            "id": device.id,
            "color": device.color or device.name,  # Use color for Tilt, name for others
            "beer_name": device.beer_name or "Untitled",
            "original_gravity": device.original_gravity,
            "sg": reading.gravity,
            "sg_raw": reading.gravity_raw,
            "temp": reading.temperature,
            "temp_raw": reading.temperature_raw,
            "rssi": reading.rssi,
            "last_seen": serialize_datetime_to_utc(timestamp),
            # Extended fields for multi-hydrometer support
            "device_type": reading.device_type,
            "angle": reading.angle,
            "battery_voltage": reading.battery_voltage,
            "battery_percent": reading.battery_percent,
            # ML outputs
            "sg_filtered": ml_outputs.get("sg_filtered"),
            "temp_filtered": ml_outputs.get("temp_filtered"),
            "confidence": ml_outputs.get("confidence"),
            "sg_rate": ml_outputs.get("sg_rate"),
            "temp_rate": ml_outputs.get("temp_rate"),
            "is_anomaly": ml_outputs.get("is_anomaly", False),
            "anomaly_score": ml_outputs.get("anomaly_score"),
            "anomaly_reasons": ml_outputs.get("anomaly_reasons", []),
        }

        return payload

    async def _broadcast_reading(
        self,
        device: Device,
        reading: HydrometerReading,
        ml_outputs: Optional[dict] = None,
    ) -> None:
        """Broadcast reading update via WebSocket and update latest_readings cache."""
        try:
            payload = self._build_reading_payload(device, reading, ml_outputs)

            # Update the latest_readings cache (persists to disk)
            # This ensures readings survive service restarts
            update_reading(device.id, payload)

            # Broadcast to all connected WebSocket clients
            await ws_manager.broadcast(payload)
        except Exception as e:
            logger.warning("Failed to broadcast reading: %s", e)


# Global ingest manager instance
ingest_manager = IngestManager()
