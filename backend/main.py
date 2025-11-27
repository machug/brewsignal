import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from . import models  # noqa: F401 - Import models so SQLAlchemy sees them
from .database import async_session_factory, init_db
from .models import Reading, Tilt
from .scanner import TiltReading, TiltScanner
from .websocket import manager

# Global scanner instance
scanner: Optional[TiltScanner] = None
scanner_task: Optional[asyncio.Task] = None

# In-memory cache of latest readings per Tilt
latest_readings: dict[str, dict] = {}


async def handle_tilt_reading(reading: TiltReading):
    """Process a new Tilt reading: update DB and broadcast to WebSocket clients."""
    async with async_session_factory() as session:
        # Upsert Tilt record
        tilt = await session.get(Tilt, reading.id)
        if not tilt:
            tilt = Tilt(
                id=reading.id,
                color=reading.color,
                mac=reading.mac,
                beer_name="Untitled",
            )
            session.add(tilt)

        tilt.last_seen = datetime.utcnow()
        tilt.mac = reading.mac

        # Store reading in DB
        db_reading = Reading(
            tilt_id=reading.id,
            sg_raw=reading.sg,
            sg_calibrated=reading.sg,  # TODO: apply calibration
            temp_raw=reading.temp_f,
            temp_calibrated=reading.temp_f,  # TODO: apply calibration
            rssi=reading.rssi,
        )
        session.add(db_reading)
        await session.commit()

        # Build reading data for WebSocket broadcast
        reading_data = {
            "id": reading.id,
            "color": reading.color,
            "beer_name": tilt.beer_name,
            "sg": reading.sg,
            "sg_raw": reading.sg,
            "temp": reading.temp_f,
            "temp_raw": reading.temp_f,
            "rssi": reading.rssi,
            "last_seen": datetime.utcnow().isoformat(),
        }

        # Update in-memory cache
        latest_readings[reading.id] = reading_data

        # Broadcast to all WebSocket clients
        await manager.broadcast(reading_data)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global scanner, scanner_task

    # Startup
    print("Starting Tilt UI...")
    await init_db()
    print("Database initialized")

    # Start scanner
    scanner = TiltScanner(on_reading=handle_tilt_reading)
    scanner_task = asyncio.create_task(scanner.start())
    print("Scanner started")

    yield

    # Shutdown
    print("Shutting down Tilt UI...")
    if scanner:
        await scanner.stop()
    if scanner_task:
        scanner_task.cancel()
        try:
            await scanner_task
        except asyncio.CancelledError:
            pass
    print("Scanner stopped")


app = FastAPI(title="Tilt UI", version="0.1.0", lifespan=lifespan)


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


# Mount static files (Svelte build output) - MUST be last
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
