import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Configure logging to show INFO level
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Imports after logging configuration
from fastapi import FastAPI, WebSocket, WebSocketDisconnect  # noqa: E402
from fastapi.responses import FileResponse, StreamingResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from sqlalchemy import select, desc  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402

from . import models  # noqa: E402, F401 - Import models so SQLAlchemy sees them
from .database import async_session_factory, init_db  # noqa: E402
from .models import Device, Reading, serialize_datetime_to_utc  # noqa: E402
from .routers import ag_ui, alerts, ambient, assistant, batches, chamber, config, control, devices, fermentables, ha, hop_varieties, ingest, inventory_equipment, inventory_hops, inventory_yeast, maintenance, mqtt, recipes, system, yeast_strains  # noqa: E402
from .routers.config import get_config_value  # noqa: E402
from .ambient_poller import start_ambient_poller, stop_ambient_poller  # noqa: E402
from .chamber_poller import start_chamber_poller, stop_chamber_poller  # noqa: E402
from .temp_controller import start_temp_controller, stop_temp_controller  # noqa: E402
from .mqtt_manager import start_mqtt_manager, stop_mqtt_manager, publish_batch_reading  # noqa: E402
from .cleanup import CleanupService  # noqa: E402
from .scanner import TiltReading, TiltScanner  # noqa: E402
from .services.calibration import calibration_service  # noqa: E402
from .services.batch_linker import link_reading_to_batch  # noqa: E402
from .services.alert_service import detect_and_persist_alerts  # noqa: E402
from .state import latest_readings, update_reading, load_readings_cache  # noqa: E402
from .websocket import manager  # noqa: E402
from .ml.pipeline_manager import MLPipelineManager  # noqa: E402
from .config import Settings  # noqa: E402
import time  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402

# Global scanner instance
scanner: Optional[TiltScanner] = None
scanner_task: Optional[asyncio.Task] = None
cleanup_service: Optional[CleanupService] = None

# Global ML pipeline manager
ml_pipeline_manager: Optional[MLPipelineManager] = None


def get_ml_manager() -> Optional[MLPipelineManager]:
    """Get the global ML pipeline manager instance."""
    return ml_pipeline_manager


# Cache for first reading timestamps (device_id -> datetime)
# Prevents N+1 query on every reading when using wall-clock fallback
_first_reading_cache: dict[str, datetime] = {}

# Cache for last stored reading time per Tilt device (rate limiting)
# Tilts broadcast constantly via BLE but we only want to store at configured interval
_last_tilt_storage: dict[str, datetime] = {}


async def calculate_time_since_batch_start(
    session,
    batch_id: Optional[int],
    device_id: str
) -> float:
    """Calculate hours since batch start, with wall-clock fallback.

    Args:
        session: Database session
        batch_id: Batch ID (may be None for unlinked readings)
        device_id: Device ID for wall-clock fallback

    Returns:
        Hours since batch start_time, or hours since first reading if no batch
    """
    if batch_id:
        batch = await session.get(models.Batch, batch_id)
        if batch and batch.start_time:
            now = datetime.now(timezone.utc)
            start_time = batch.start_time

            # Handle naive datetime (database stores in UTC but without timezone info)
            if start_time.tzinfo is None:
                start_time = start_time.replace(tzinfo=timezone.utc)

            delta = now - start_time
            return delta.total_seconds() / 3600.0

    # Fallback: Use wall-clock time since first reading for this device
    # This prevents ML pipeline from being stuck at time_hours=0

    # Check cache first to avoid N+1 query
    if device_id in _first_reading_cache:
        first_time = _first_reading_cache[device_id]
        now = datetime.now(timezone.utc)
        delta = now - first_time
        return delta.total_seconds() / 3600.0

    # Cache miss - query database for first reading
    first_reading = await session.execute(
        select(models.Reading)
        .where(models.Reading.device_id == device_id)
        .order_by(models.Reading.timestamp.asc())
        .limit(1)
    )
    first = first_reading.scalar_one_or_none()

    if first:
        now = datetime.now(timezone.utc)
        first_time = first.timestamp

        # Handle naive datetime
        if first_time.tzinfo is None:
            first_time = first_time.replace(tzinfo=timezone.utc)

        # Cache for future calls
        _first_reading_cache[device_id] = first_time

        delta = now - first_time
        return delta.total_seconds() / 3600.0

    # Absolute fallback: return 0.0 for very first reading
    return 0.0


async def get_alert_context(
    session,
    batch_id: int,
    current_sg: Optional[float],
) -> dict:
    """Get context needed for alert detection (yeast temp range, progress)."""
    from sqlalchemy.orm import selectinload

    context = {
        "yeast_temp_min": None,
        "yeast_temp_max": None,
        "progress_percent": None,
    }

    # Fetch batch with recipe and yeast eagerly loaded
    stmt = (
        select(models.Batch)
        .where(models.Batch.id == batch_id)
        .options(
            selectinload(models.Batch.recipe).selectinload(models.Recipe.yeast),
            selectinload(models.Batch.yeast_strain),
        )
    )
    result = await session.execute(stmt)
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


async def handle_tilt_reading(reading: TiltReading):
    """Process Tilt BLE reading and store if paired.

    Simplified: Only manages Device table (no dual-table sync).
    """
    async with async_session_factory() as session:
        # Get or create Device record (single source of truth)
        device = await session.get(Device, reading.id)
        if not device:
            # Create new Tilt device (temps converted from F to C on ingestion)
            device = Device(
                id=reading.id,
                device_type='tilt',
                name=reading.color,
                native_temp_unit='c',  # Stored in Celsius (converted from F at BLE boundary)
                native_gravity_unit='sg',
                calibration_type='linear',
                paired=False,  # New devices start unpaired
            )
            session.add(device)

        # Update device metadata from reading
        timestamp = datetime.now(timezone.utc)
        device.last_seen = timestamp
        device.color = reading.color
        device.mac = reading.mac

        # Always commit device metadata (so unpaired devices show updated last_seen)
        await session.commit()

        # Convert Tilt's Fahrenheit to Celsius immediately
        temp_raw_c = (reading.temp_f - 32) * 5.0 / 9.0

        # Apply calibration in Celsius
        sg_calibrated, temp_calibrated_c = await calibration_service.calibrate_reading(
            session, reading.id, reading.sg, temp_raw_c
        )

        # Validate reading for outliers (physical impossibility check)
        # Valid SG range: 0.500-1.200 (beer is typically 1.000-1.120)
        # Valid temp range: 0-100°C (freezing to boiling)
        status = "valid"
        if not (0.500 <= sg_calibrated <= 1.200) or not (0.0 <= temp_calibrated_c <= 100.0):
            status = "invalid"

        # Link reading to active batch (if any)
        batch_id = await link_reading_to_batch(session, reading.id)

        # Rate limit Tilt storage using configured interval
        # Tilts broadcast constantly via BLE, but we only store at the configured interval
        interval_minutes = await get_config_value(session, "local_interval_minutes") or 15
        last_stored = _last_tilt_storage.get(reading.id)
        should_store = (
            last_stored is None or
            (timestamp - last_stored).total_seconds() >= interval_minutes * 60
        )

        # ML outputs - only populated when we store a reading
        ml_outputs = {}

        # Only store readings if ALL conditions met:
        # 1. Device is paired (prevents pollution from nearby unpaired Tilts)
        # 2. Reading linked to active batch (fermenting or conditioning status)
        # 3. Enough time has passed since last storage (rate limiting)
        if device.paired and batch_id is not None and should_store:
            # Calculate time since batch start for ML pipeline (with wall-clock fallback)
            time_hours = await calculate_time_since_batch_start(session, batch_id, reading.id)

            # Process through ML pipeline if available
            if ml_pipeline_manager:
                try:
                    # Call synchronous process_reading (no await)
                    ml_outputs = ml_pipeline_manager.process_reading(
                        device_id=reading.id,
                        sg=sg_calibrated,
                        temp=temp_calibrated_c,
                        rssi=reading.rssi,
                        time_hours=time_hours,
                        # TODO: Add ambient_temp, heater_on, cooler_on, target_temp when available
                    )
                except Exception as e:
                    logging.error(f"ML pipeline failed for {reading.id}: {e}")
                    # ML failure is non-fatal - continue with empty outputs

            # Create reading record
            db_reading = Reading(
                device_id=reading.id,
                batch_id=batch_id,
                timestamp=timestamp,
                sg_raw=reading.sg,
                sg_calibrated=sg_calibrated,
                temp_raw=temp_raw_c,
                temp_calibrated=temp_calibrated_c,
                rssi=reading.rssi,
                status=status,
                # ML outputs
                sg_filtered=ml_outputs.get("sg_filtered"),
                temp_filtered=ml_outputs.get("temp_filtered"),
                confidence=ml_outputs.get("confidence"),
                sg_rate=ml_outputs.get("sg_rate"),
                temp_rate=ml_outputs.get("temp_rate"),
                is_anomaly=ml_outputs.get("is_anomaly", False),
                anomaly_score=ml_outputs.get("anomaly_score"),
                anomaly_reasons=json.dumps(ml_outputs.get("anomaly_reasons", [])) if ml_outputs.get("anomaly_reasons") else None,
            )
            session.add(db_reading)
            await session.flush()  # Flush to get reading ID for alerts

            # Detect and persist alerts
            try:
                # Build live_reading dict for alert detection
                live_reading = {
                    "temp": temp_calibrated_c,
                    "sg": sg_calibrated,
                    "sg_rate": ml_outputs.get("sg_rate"),
                    "is_anomaly": ml_outputs.get("is_anomaly", False),
                    "anomaly_score": ml_outputs.get("anomaly_score"),
                    "anomaly_reasons": ml_outputs.get("anomaly_reasons"),
                }

                # Get alert context (yeast temp range, progress)
                alert_context = await get_alert_context(
                    session, batch_id, sg_calibrated
                )

                # Detect and persist alerts
                await detect_and_persist_alerts(
                    db=session,
                    batch_id=batch_id,
                    device_id=reading.id,
                    reading=db_reading,
                    live_reading=live_reading,
                    yeast_temp_min=alert_context.get("yeast_temp_min"),
                    yeast_temp_max=alert_context.get("yeast_temp_max"),
                    progress_percent=alert_context.get("progress_percent"),
                )
            except Exception as e:
                logging.warning("Alert detection failed: %s", e)
                # Alert detection failure is non-fatal

            await session.commit()

            # Publish reading to MQTT for Home Assistant (fire-and-forget)
            # Get batch info for MQTT context
            batch = await session.get(models.Batch, batch_id)
            if batch:
                await publish_batch_reading(
                    batch_id=batch_id,
                    gravity=sg_calibrated,
                    temperature=temp_calibrated_c,
                    og=batch.measured_og,  # Use measured OG only to avoid lazy load issues
                    start_time=batch.start_time,
                    status=batch.status,
                )

            # Update rate limit cache after successful storage
            _last_tilt_storage[reading.id] = timestamp

        # Always broadcast detected devices (so unpaired ones show on dashboard)
        # But only store readings for paired devices linked to active batches (handled above)
        payload = {
            "id": reading.id,  # Frontend expects this field
            "device_id": reading.id,
            "device_type": "tilt",
            "color": reading.color,
            "beer_name": device.beer_name or "Untitled",
            "original_gravity": device.original_gravity,
            "sg": sg_calibrated,
            "sg_raw": reading.sg,
            "temp": temp_calibrated_c,
            "temp_raw": temp_raw_c,
            "rssi": reading.rssi,
            "timestamp": serialize_datetime_to_utc(timestamp),
            "last_seen": serialize_datetime_to_utc(timestamp),
            "paired": device.paired,
            "mac": reading.mac,
            # ML outputs (only populated for paired devices with active batches)
            "sg_filtered": ml_outputs.get("sg_filtered"),
            "temp_filtered": ml_outputs.get("temp_filtered"),
            "confidence": ml_outputs.get("confidence"),
            "sg_rate": ml_outputs.get("sg_rate"),
            "temp_rate": ml_outputs.get("temp_rate"),
            "is_anomaly": ml_outputs.get("is_anomaly", False),
            "anomaly_score": ml_outputs.get("anomaly_score"),
            "anomaly_reasons": ml_outputs.get("anomaly_reasons", []),
        }

        # Update cache (persists to disk) and broadcast to WebSocket clients
        update_reading(reading.id, payload)
        await manager.broadcast(payload)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global scanner, scanner_task, cleanup_service, ml_pipeline_manager

    settings = Settings()
    is_cloud = settings.is_cloud

    # Startup
    mode_str = "CLOUD" if is_cloud else "LOCAL"
    print(f"Starting BrewSignal ({mode_str} mode)...")
    await init_db()
    print("Database initialized")

    # Load cached readings from disk (survives restarts) - only for local mode
    if not is_cloud:
        load_readings_cache()
        print(f"Loaded {len(latest_readings)} cached device readings")

    # Initialize ML pipeline manager
    ml_pipeline_manager = MLPipelineManager()
    logging.info("ML Pipeline Manager initialized")

    # Start scanner - in cloud mode, auto-enable mock if no relay configured
    if is_cloud and not os.environ.get("SCANNER_RELAY_HOST"):
        os.environ["SCANNER_MOCK"] = "true"
        print("Cloud mode: Scanner set to MOCK (no BLE hardware)")

    scanner = TiltScanner(on_reading=handle_tilt_reading)
    scanner_task = asyncio.create_task(scanner.start())
    print("Scanner started")

    # Start cleanup service (30-day retention, hourly check)
    cleanup_service = CleanupService(retention_days=30, interval_hours=1)
    await cleanup_service.start()

    # Local-only services (require Home Assistant access)
    if not is_cloud:
        # Start ambient poller for Home Assistant integration
        start_ambient_poller()
        print("Ambient poller started")

        # Start chamber poller for fermentation chamber environment
        await start_chamber_poller()
        print("Chamber poller started")

        # Start temperature controller for HA-based temperature control
        start_temp_controller()
        print("Temperature controller started")

        # Start MQTT manager for Home Assistant batch data publishing
        start_mqtt_manager()
        print("MQTT manager started")
    else:
        print("Cloud mode: Skipping Home Assistant services (ambient, chamber, temp control, MQTT)")

    yield

    # Shutdown
    print("Shutting down BrewSignal...")
    if not is_cloud:
        stop_mqtt_manager()
        stop_temp_controller()
        stop_chamber_poller()
        stop_ambient_poller()
    if cleanup_service:
        await cleanup_service.stop()
    if scanner:
        await scanner.stop()
    if scanner_task:
        scanner_task.cancel()
        try:
            await scanner_task
        except asyncio.CancelledError:
            pass
    ml_pipeline_manager = None
    print("Scanner stopped")


from .routers.system import VERSION  # noqa: E402
app = FastAPI(title="BrewSignal", version=VERSION, lifespan=lifespan)

# Register routers
app.include_router(devices.router)
app.include_router(config.router)
app.include_router(system.router)
app.include_router(ambient.router)
app.include_router(chamber.router)
app.include_router(ha.router)
app.include_router(mqtt.router)
app.include_router(control.router)
app.include_router(alerts.router)
app.include_router(ingest.router)
app.include_router(recipes.router)
app.include_router(batches.router)
app.include_router(maintenance.router)
app.include_router(yeast_strains.router)
app.include_router(hop_varieties.router)
app.include_router(fermentables.router)
app.include_router(assistant.router)
app.include_router(ag_ui.router)
app.include_router(inventory_equipment.router)
app.include_router(inventory_hops.router)
app.include_router(inventory_yeast.router)


@app.get("/api/health")
async def health_check():
    return {
        "status": "ok",
        "websocket_connections": manager.connection_count,
        "active_tilts": len(latest_readings),
    }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)

    # Send current state of all Tilts on connect
    for reading in latest_readings.values():
        await websocket.send_json(reading)

    try:
        while True:
            # Keep connection alive, ignore any messages from client
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@app.get("/log.csv")
async def download_log():
    """Download all readings as CSV file."""
    import csv
    import io

    async def generate_csv():
        output = io.StringIO()
        writer = csv.writer(output)

        # Write header
        writer.writerow([
            "timestamp", "tilt_id", "color", "beer_name",
            "sg_raw", "sg_calibrated", "temp_raw", "temp_calibrated", "rssi"
        ])
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)

        # Stream readings in batches
        async with async_session_factory() as session:
            # Get all tilts for beer_name lookup
            tilts_result = await session.execute(select(Tilt))
            tilts_map = {t.id: t for t in tilts_result.scalars()}

            # Get readings ordered by timestamp
            result = await session.execute(
                select(Reading).order_by(Reading.timestamp)
            )
            for reading in result.scalars():
                tilt = tilts_map.get(reading.tilt_id)
                writer.writerow([
                    serialize_datetime_to_utc(reading.timestamp) if reading.timestamp else "",
                    reading.tilt_id,
                    tilt.color if tilt else "",
                    tilt.beer_name if tilt else "",
                    reading.sg_raw,
                    reading.sg_calibrated,
                    reading.temp_raw,
                    reading.temp_calibrated,
                    reading.rssi
                ])
                yield output.getvalue()
                output.seek(0)
                output.truncate(0)

    return StreamingResponse(
        generate_csv(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=tilt_readings.csv"}
    )


@app.get("/api/stats")
async def get_stats():
    """Get database statistics for the logging page."""
    async with async_session_factory() as session:
        # Count total readings
        from sqlalchemy import func
        readings_count = await session.execute(
            select(func.count()).select_from(Reading)
        )
        total_readings = int(readings_count.scalar() or 0)

        # Get oldest and newest reading timestamps
        oldest = await session.execute(
            select(Reading.timestamp).order_by(Reading.timestamp).limit(1)
        )
        oldest_time = oldest.scalar()

        newest = await session.execute(
            select(Reading.timestamp).order_by(desc(Reading.timestamp)).limit(1)
        )
        newest_time = newest.scalar()

        # Estimate size (rough: ~100 bytes per reading)
        estimated_size_bytes = total_readings * 100

        return {
            "total_readings": total_readings,
            "oldest_reading": serialize_datetime_to_utc(oldest_time) if oldest_time else None,
            "newest_reading": serialize_datetime_to_utc(newest_time) if newest_time else None,
            "estimated_size_bytes": estimated_size_bytes,
        }


# SPA page routes - serve pre-rendered HTML files
# Only in local mode; cloud mode uses Vercel for frontend
static_dir = Path(__file__).parent / "static"
_settings = Settings()
_serve_frontend = not _settings.is_cloud and static_dir.exists()

if _serve_frontend:
    @app.get("/", response_class=FileResponse)
    async def serve_index():
        """Serve the main dashboard page."""
        return FileResponse(static_dir / "index.html")


    @app.get("/logging", response_class=FileResponse)
    async def serve_logging():
        """Serve the logging page."""
        return FileResponse(static_dir / "logging.html")

    @app.get("/calibration", response_class=FileResponse)
    async def serve_calibration():
        """Serve the calibration page."""
        return FileResponse(static_dir / "calibration.html")

    @app.get("/system", response_class=FileResponse)
    async def serve_system():
        """Serve the system page."""
        return FileResponse(static_dir / "system.html")

    @app.get("/system/{path:path}", response_class=FileResponse)
    async def serve_system_subpages(path: str):
        """Serve system subpages (maintenance, etc.) - SPA handles routing."""
        html_path = static_dir / "system" / f"{path}.html"
        if html_path.exists():
            return FileResponse(html_path)
        index_path = static_dir / "system" / path / "index.html"
        if index_path.exists():
            return FileResponse(index_path)
        return FileResponse(static_dir / "index.html")

    @app.get("/devices", response_class=FileResponse)
    async def serve_devices():
        """Serve the devices page."""
        return FileResponse(static_dir / "devices.html")

    @app.get("/yeast", response_class=FileResponse)
    async def serve_yeast():
        """Serve the yeast library page (legacy)."""
        return FileResponse(static_dir / "yeast.html")

    @app.get("/library", response_class=FileResponse)
    async def serve_library():
        """Serve unified ingredient library page."""
        return FileResponse(static_dir / "library.html")

    @app.get("/batches", response_class=FileResponse)
    async def serve_batches():
        """Serve the batches page."""
        return FileResponse(static_dir / "batches.html")

    @app.get("/recipes", response_class=FileResponse)
    async def serve_recipes():
        """Serve the recipes page."""
        return FileResponse(static_dir / "recipes.html")

    @app.get("/batches/{path:path}", response_class=FileResponse)
    async def serve_batches_subpages(path: str):
        """Serve batches subpages - SPA handles routing."""
        html_path = static_dir / "batches" / f"{path}.html"
        if html_path.exists():
            return FileResponse(html_path)
        index_path = static_dir / "batches" / path / "index.html"
        if index_path.exists():
            return FileResponse(index_path)
        return FileResponse(static_dir / "index.html")

    @app.get("/recipes/{path:path}", response_class=FileResponse)
    async def serve_recipes_subpages(path: str):
        """Serve recipes subpages - SPA handles routing."""
        html_path = static_dir / "recipes" / f"{path}.html"
        if html_path.exists():
            return FileResponse(html_path)
        index_path = static_dir / "recipes" / path / "index.html"
        if index_path.exists():
            return FileResponse(index_path)
        return FileResponse(static_dir / "index.html")

    @app.get("/assistant", response_class=FileResponse)
    async def serve_assistant():
        """Serve the AI assistant page."""
        return FileResponse(static_dir / "assistant.html")

    @app.get("/inventory", response_class=FileResponse)
    async def serve_inventory():
        """Serve the inventory page."""
        return FileResponse(static_dir / "inventory.html")

    @app.get("/favicon.png", response_class=FileResponse)
    async def serve_favicon():
        """Serve the favicon."""
        return FileResponse(static_dir / "favicon.png")

    @app.get("/logo.svg", response_class=FileResponse)
    async def serve_logo():
        """Serve the logo SVG."""
        return FileResponse(static_dir / "logo.svg", media_type="image/svg+xml")

    @app.get("/icon.svg", response_class=FileResponse)
    async def serve_icon():
        """Serve the icon SVG."""
        return FileResponse(static_dir / "icon.svg", media_type="image/svg+xml")

    @app.get("/logo-preview.html", response_class=FileResponse)
    async def serve_logo_preview():
        """Serve the logo preview page."""
        return FileResponse(static_dir / "logo-preview.html")

    # Mount static files (Svelte build output)
    app_assets = static_dir / "_app"
    if app_assets.exists():
        app.mount("/_app", StaticFiles(directory=app_assets), name="app_assets")
else:
    # Cloud mode: minimal root endpoint
    @app.get("/")
    async def api_root():
        """API root - frontend served by Vercel."""
        return {"message": "BrewSignal API", "docs": "/docs", "health": "/api/health"}
