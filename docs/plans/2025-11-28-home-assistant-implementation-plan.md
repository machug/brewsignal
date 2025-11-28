# Home Assistant Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Integrate TiltUI with Home Assistant to display ambient temperature, control heating, show weather forecasts, and import BeerXML recipes.

**Architecture:** TiltUI-controlled approach - TiltUI handles all control logic; Home Assistant acts as the device bridge via REST API. Ambient temp, weather, and control events are stored locally and displayed on charts.

**Tech Stack:** FastAPI, SQLAlchemy async, httpx (HTTP client), Svelte 5 runes, uPlot charts, BeerXML parsing

---

## Phase 10a: HA Connection + Ambient Temperature

### Task 1: Add HA Configuration Schema

**Files:**
- Modify: `backend/models.py:132-187` (ConfigUpdate and ConfigResponse)
- Modify: `backend/routers/config.py:18-27` (DEFAULT_CONFIG)

**Step 1: Add HA config fields to ConfigUpdate model**

In `backend/models.py`, add these fields to `ConfigUpdate` class after line 140:

```python
class ConfigUpdate(BaseModel):
    temp_units: Optional[str] = None
    sg_units: Optional[str] = None
    local_logging_enabled: Optional[bool] = None
    local_interval_minutes: Optional[int] = None
    min_rssi: Optional[int] = None
    smoothing_enabled: Optional[bool] = None
    smoothing_samples: Optional[int] = None
    id_by_mac: Optional[bool] = None
    # Home Assistant settings
    ha_enabled: Optional[bool] = None
    ha_url: Optional[str] = None
    ha_token: Optional[str] = None
    ha_ambient_temp_entity_id: Optional[str] = None
    ha_ambient_humidity_entity_id: Optional[str] = None
    # Temperature control
    temp_control_enabled: Optional[bool] = None
    temp_target: Optional[float] = None
    temp_hysteresis: Optional[float] = None
    ha_heater_entity_id: Optional[str] = None
    # Weather
    ha_weather_entity_id: Optional[str] = None

    # ... existing validators ...

    @field_validator("ha_url")
    @classmethod
    def validate_ha_url(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v and not v.startswith(("http://", "https://")):
            raise ValueError("ha_url must start with http:// or https://")
        return v.rstrip("/") if v else v

    @field_validator("temp_target")
    @classmethod
    def validate_temp_target(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and (v < 32 or v > 100):
            raise ValueError("temp_target must be between 32 and 100 (Fahrenheit)")
        return v

    @field_validator("temp_hysteresis")
    @classmethod
    def validate_temp_hysteresis(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and (v < 0.5 or v > 10):
            raise ValueError("temp_hysteresis must be between 0.5 and 10")
        return v
```

**Step 2: Add HA config fields to ConfigResponse model**

In `backend/models.py`, update `ConfigResponse` class:

```python
class ConfigResponse(BaseModel):
    temp_units: str = "C"
    sg_units: str = "sg"
    local_logging_enabled: bool = True
    local_interval_minutes: int = 15
    min_rssi: int = -100
    smoothing_enabled: bool = False
    smoothing_samples: int = 5
    id_by_mac: bool = False
    # Home Assistant settings
    ha_enabled: bool = False
    ha_url: str = ""
    ha_token: str = ""
    ha_ambient_temp_entity_id: str = ""
    ha_ambient_humidity_entity_id: str = ""
    # Temperature control
    temp_control_enabled: bool = False
    temp_target: float = 68.0
    temp_hysteresis: float = 1.0
    ha_heater_entity_id: str = ""
    # Weather
    ha_weather_entity_id: str = ""
```

**Step 3: Update DEFAULT_CONFIG in routers/config.py**

```python
DEFAULT_CONFIG: dict[str, Any] = {
    "temp_units": "C",
    "sg_units": "sg",
    "local_logging_enabled": True,
    "local_interval_minutes": 15,
    "min_rssi": -100,
    "smoothing_enabled": False,
    "smoothing_samples": 5,
    "id_by_mac": False,
    # Home Assistant settings
    "ha_enabled": False,
    "ha_url": "",
    "ha_token": "",
    "ha_ambient_temp_entity_id": "",
    "ha_ambient_humidity_entity_id": "",
    # Temperature control
    "temp_control_enabled": False,
    "temp_target": 68.0,
    "temp_hysteresis": 1.0,
    "ha_heater_entity_id": "",
    # Weather
    "ha_weather_entity_id": "",
}
```

**Step 4: Verify changes compile**

Run: `cd /home/ladmin/Projects/tilt_ui && python -c "from backend.models import ConfigUpdate, ConfigResponse; print('OK')"`
Expected: `OK`

**Step 5: Commit**

```bash
git add backend/models.py backend/routers/config.py
git commit -m "feat: add Home Assistant config schema"
```

---

### Task 2: Create HA Client Service

**Files:**
- Create: `backend/services/ha_client.py`

**Step 1: Create the HA client module**

Create `backend/services/ha_client.py`:

```python
"""Home Assistant REST API client."""

import logging
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)


class HAClientError(Exception):
    """Home Assistant client error."""
    pass


class HAClient:
    """Async HTTP client for Home Assistant REST API."""

    def __init__(self, url: str, token: str):
        self.url = url.rstrip("/")
        self.token = token
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=10.0)
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def test_connection(self) -> bool:
        """Test if HA is reachable and token is valid."""
        try:
            client = await self._get_client()
            response = await client.get(f"{self.url}/api/", headers=self.headers)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"HA connection test failed: {e}")
            return False

    async def get_state(self, entity_id: str) -> Optional[dict[str, Any]]:
        """Get current state of an entity.

        Returns dict with 'state', 'attributes', 'last_changed', etc.
        Returns None if entity not found or error.
        """
        try:
            client = await self._get_client()
            response = await client.get(
                f"{self.url}/api/states/{entity_id}",
                headers=self.headers
            )
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                logger.warning(f"Entity not found: {entity_id}")
                return None
            else:
                logger.error(f"HA get_state failed: {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"HA get_state error: {e}")
            return None

    async def call_service(
        self, domain: str, service: str, entity_id: str, data: Optional[dict] = None
    ) -> bool:
        """Call a Home Assistant service.

        Example: call_service("switch", "turn_on", "switch.heat_mat")
        """
        try:
            client = await self._get_client()
            payload = {"entity_id": entity_id}
            if data:
                payload.update(data)

            response = await client.post(
                f"{self.url}/api/services/{domain}/{service}",
                headers=self.headers,
                json=payload
            )
            if response.status_code == 200:
                logger.info(f"HA service called: {domain}/{service} on {entity_id}")
                return True
            else:
                logger.error(f"HA call_service failed: {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"HA call_service error: {e}")
            return False

    async def get_weather_forecast(self, entity_id: str) -> Optional[list[dict]]:
        """Get weather forecast from HA weather entity."""
        try:
            client = await self._get_client()
            response = await client.post(
                f"{self.url}/api/services/weather/get_forecasts?return_response",
                headers=self.headers,
                json={"entity_id": entity_id, "type": "daily"}
            )
            if response.status_code == 200:
                data = response.json()
                # Extract forecast from service response
                service_response = data.get("service_response", {})
                entity_data = service_response.get(entity_id, {})
                return entity_data.get("forecast", [])
            else:
                logger.error(f"HA get_forecast failed: {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"HA get_forecast error: {e}")
            return None


# Singleton instance (initialized when config is loaded)
_ha_client: Optional[HAClient] = None


def get_ha_client() -> Optional[HAClient]:
    """Get the current HA client instance."""
    return _ha_client


def init_ha_client(url: str, token: str) -> HAClient:
    """Initialize or reinitialize the HA client."""
    global _ha_client
    if _ha_client:
        # Close existing client asynchronously would need event loop
        pass
    _ha_client = HAClient(url, token)
    return _ha_client


async def close_ha_client() -> None:
    """Close the HA client."""
    global _ha_client
    if _ha_client:
        await _ha_client.close()
        _ha_client = None
```

**Step 2: Verify module imports**

Run: `cd /home/ladmin/Projects/tilt_ui && python -c "from backend.services.ha_client import HAClient, HAClientError; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add backend/services/ha_client.py
git commit -m "feat: add Home Assistant REST API client"
```

---

### Task 3: Add Ambient Readings Database Model

**Files:**
- Modify: `backend/models.py` (add AmbientReading model)

**Step 1: Add AmbientReading SQLAlchemy model**

In `backend/models.py`, add after the `CalibrationPoint` class (around line 58):

```python
class AmbientReading(Base):
    """Ambient temperature/humidity readings from Home Assistant sensors."""
    __tablename__ = "ambient_readings"
    __table_args__ = (
        Index("ix_ambient_timestamp", "timestamp"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(default=datetime.utcnow, index=True)
    temperature: Mapped[Optional[float]] = mapped_column()
    humidity: Mapped[Optional[float]] = mapped_column()
    entity_id: Mapped[Optional[str]] = mapped_column(String(100))
```

**Step 2: Add Pydantic response schema**

In `backend/models.py`, add after `ReadingResponse`:

```python
class AmbientReadingResponse(BaseModel):
    id: int
    timestamp: datetime
    temperature: Optional[float]
    humidity: Optional[float]

    class Config:
        from_attributes = True
```

**Step 3: Verify model**

Run: `cd /home/ladmin/Projects/tilt_ui && python -c "from backend.models import AmbientReading, AmbientReadingResponse; print('OK')"`
Expected: `OK`

**Step 4: Commit**

```bash
git add backend/models.py
git commit -m "feat: add AmbientReading database model"
```

---

### Task 4: Create Ambient API Router

**Files:**
- Create: `backend/routers/ambient.py`
- Modify: `backend/main.py` (register router)

**Step 1: Create ambient router**

Create `backend/routers/ambient.py`:

```python
"""Ambient temperature/humidity API endpoints."""

import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import AmbientReading, AmbientReadingResponse
from ..services.ha_client import get_ha_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ambient", tags=["ambient"])


@router.get("/current")
async def get_current_ambient():
    """Get current ambient temperature and humidity from HA."""
    from ..routers.config import get_config_value, get_db as get_db_config
    from ..database import async_session

    async with async_session() as db:
        ha_enabled = await get_config_value(db, "ha_enabled")
        if not ha_enabled:
            return {"error": "Home Assistant not enabled", "temperature": None, "humidity": None}

        ha_client = get_ha_client()
        if not ha_client:
            return {"error": "Home Assistant client not initialized", "temperature": None, "humidity": None}

        temp_entity = await get_config_value(db, "ha_ambient_temp_entity_id")
        humidity_entity = await get_config_value(db, "ha_ambient_humidity_entity_id")

        temperature = None
        humidity = None

        if temp_entity:
            state = await ha_client.get_state(temp_entity)
            if state and state.get("state") not in ("unavailable", "unknown"):
                try:
                    temperature = float(state["state"])
                except (ValueError, TypeError):
                    pass

        if humidity_entity:
            state = await ha_client.get_state(humidity_entity)
            if state and state.get("state") not in ("unavailable", "unknown"):
                try:
                    humidity = float(state["state"])
                except (ValueError, TypeError):
                    pass

        return {
            "temperature": temperature,
            "humidity": humidity,
            "timestamp": datetime.utcnow().isoformat()
        }


@router.get("/history", response_model=list[AmbientReadingResponse])
async def get_ambient_history(
    hours: int = Query(default=24, ge=1, le=720),
    db: AsyncSession = Depends(get_db)
):
    """Get historical ambient readings."""
    since = datetime.utcnow() - timedelta(hours=hours)

    result = await db.execute(
        select(AmbientReading)
        .where(AmbientReading.timestamp >= since)
        .order_by(desc(AmbientReading.timestamp))
        .limit(2000)
    )

    return result.scalars().all()
```

**Step 2: Register router in main.py**

In `backend/main.py`, add the import and include:

```python
from .routers import ambient
# ... after other router includes ...
app.include_router(ambient.router)
```

**Step 3: Verify router**

Run: `cd /home/ladmin/Projects/tilt_ui && python -c "from backend.routers.ambient import router; print('OK')"`
Expected: `OK`

**Step 4: Commit**

```bash
git add backend/routers/ambient.py backend/main.py
git commit -m "feat: add ambient temperature API endpoints"
```

---

### Task 5: Create HA API Router (connection test)

**Files:**
- Create: `backend/routers/ha.py`
- Modify: `backend/main.py` (register router)

**Step 1: Create HA router**

Create `backend/routers/ha.py`:

```python
"""Home Assistant integration API endpoints."""

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..services.ha_client import HAClient, init_ha_client, get_ha_client
from .config import get_config_value

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ha", tags=["homeassistant"])


class HAStatusResponse(BaseModel):
    enabled: bool
    connected: bool
    url: str
    error: str | None = None


class HATestRequest(BaseModel):
    url: str
    token: str


class HATestResponse(BaseModel):
    success: bool
    message: str


@router.get("/status", response_model=HAStatusResponse)
async def get_ha_status(db: AsyncSession = Depends(get_db)):
    """Get Home Assistant connection status."""
    ha_enabled = await get_config_value(db, "ha_enabled")
    ha_url = await get_config_value(db, "ha_url") or ""

    if not ha_enabled:
        return HAStatusResponse(enabled=False, connected=False, url=ha_url)

    ha_client = get_ha_client()
    if not ha_client:
        return HAStatusResponse(
            enabled=True,
            connected=False,
            url=ha_url,
            error="Client not initialized"
        )

    connected = await ha_client.test_connection()
    return HAStatusResponse(enabled=True, connected=connected, url=ha_url)


@router.post("/test", response_model=HATestResponse)
async def test_ha_connection(request: HATestRequest):
    """Test Home Assistant connection with provided credentials."""
    if not request.url or not request.token:
        return HATestResponse(success=False, message="URL and token are required")

    client = HAClient(request.url, request.token)
    try:
        connected = await client.test_connection()
        if connected:
            return HATestResponse(success=True, message="Connection successful")
        else:
            return HATestResponse(success=False, message="Connection failed - check URL and token")
    except Exception as e:
        return HATestResponse(success=False, message=f"Error: {str(e)}")
    finally:
        await client.close()


@router.get("/weather")
async def get_weather_forecast(db: AsyncSession = Depends(get_db)):
    """Get weather forecast from Home Assistant."""
    ha_enabled = await get_config_value(db, "ha_enabled")
    if not ha_enabled:
        return {"error": "Home Assistant not enabled", "forecast": []}

    weather_entity = await get_config_value(db, "ha_weather_entity_id")
    if not weather_entity:
        return {"error": "Weather entity not configured", "forecast": []}

    ha_client = get_ha_client()
    if not ha_client:
        return {"error": "HA client not initialized", "forecast": []}

    forecast = await ha_client.get_weather_forecast(weather_entity)
    return {"forecast": forecast or []}
```

**Step 2: Register router in main.py**

In `backend/main.py`, add:

```python
from .routers import ha
# ... after other router includes ...
app.include_router(ha.router)
```

**Step 3: Verify router**

Run: `cd /home/ladmin/Projects/tilt_ui && python -c "from backend.routers.ha import router; print('OK')"`
Expected: `OK`

**Step 4: Commit**

```bash
git add backend/routers/ha.py backend/main.py
git commit -m "feat: add Home Assistant API endpoints"
```

---

### Task 6: Create Ambient Poller Background Task

**Files:**
- Create: `backend/ambient_poller.py`
- Modify: `backend/main.py` (start poller on startup)

**Step 1: Create ambient poller module**

Create `backend/ambient_poller.py`:

```python
"""Background task to poll Home Assistant for ambient readings."""

import asyncio
import logging
from datetime import datetime

from .database import async_session
from .models import AmbientReading
from .routers.config import get_config_value
from .services.ha_client import get_ha_client, init_ha_client
from .websocket import manager as ws_manager

logger = logging.getLogger(__name__)

_polling_task: asyncio.Task | None = None
POLL_INTERVAL_SECONDS = 30


async def poll_ambient() -> None:
    """Poll HA for ambient temperature and humidity, store and broadcast."""
    while True:
        try:
            async with async_session() as db:
                ha_enabled = await get_config_value(db, "ha_enabled")

                if not ha_enabled:
                    await asyncio.sleep(POLL_INTERVAL_SECONDS)
                    continue

                # Ensure HA client is initialized
                ha_url = await get_config_value(db, "ha_url")
                ha_token = await get_config_value(db, "ha_token")

                if not ha_url or not ha_token:
                    await asyncio.sleep(POLL_INTERVAL_SECONDS)
                    continue

                ha_client = get_ha_client()
                if not ha_client:
                    init_ha_client(ha_url, ha_token)
                    ha_client = get_ha_client()

                if not ha_client:
                    await asyncio.sleep(POLL_INTERVAL_SECONDS)
                    continue

                # Get entity IDs
                temp_entity = await get_config_value(db, "ha_ambient_temp_entity_id")
                humidity_entity = await get_config_value(db, "ha_ambient_humidity_entity_id")

                if not temp_entity and not humidity_entity:
                    await asyncio.sleep(POLL_INTERVAL_SECONDS)
                    continue

                # Fetch values
                temperature = None
                humidity = None

                if temp_entity:
                    state = await ha_client.get_state(temp_entity)
                    if state and state.get("state") not in ("unavailable", "unknown"):
                        try:
                            temperature = float(state["state"])
                        except (ValueError, TypeError):
                            logger.warning(f"Invalid temp state: {state.get('state')}")

                if humidity_entity:
                    state = await ha_client.get_state(humidity_entity)
                    if state and state.get("state") not in ("unavailable", "unknown"):
                        try:
                            humidity = float(state["state"])
                        except (ValueError, TypeError):
                            logger.warning(f"Invalid humidity state: {state.get('state')}")

                # Store reading if we got any data
                if temperature is not None or humidity is not None:
                    reading = AmbientReading(
                        temperature=temperature,
                        humidity=humidity,
                        entity_id=temp_entity or humidity_entity
                    )
                    db.add(reading)
                    await db.commit()

                    # Broadcast via WebSocket
                    await ws_manager.broadcast_json({
                        "type": "ambient",
                        "temperature": temperature,
                        "humidity": humidity,
                        "timestamp": datetime.utcnow().isoformat()
                    })

                    logger.debug(f"Ambient: temp={temperature}, humidity={humidity}")

        except Exception as e:
            logger.error(f"Ambient polling error: {e}")

        await asyncio.sleep(POLL_INTERVAL_SECONDS)


def start_ambient_poller() -> None:
    """Start the ambient polling background task."""
    global _polling_task
    if _polling_task is None or _polling_task.done():
        _polling_task = asyncio.create_task(poll_ambient())
        logger.info("Ambient poller started")


def stop_ambient_poller() -> None:
    """Stop the ambient polling background task."""
    global _polling_task
    if _polling_task and not _polling_task.done():
        _polling_task.cancel()
        logger.info("Ambient poller stopped")
```

**Step 2: Update websocket.py to support broadcast_json**

In `backend/websocket.py`, add this method to the WebSocketManager class if not present:

```python
async def broadcast_json(self, data: dict) -> None:
    """Broadcast JSON data to all connected clients."""
    import json
    message = json.dumps(data)
    for connection in self.active_connections:
        try:
            await connection.send_text(message)
        except Exception:
            pass
```

**Step 3: Start poller on app startup in main.py**

In `backend/main.py`, add to the `lifespan` function:

```python
from .ambient_poller import start_ambient_poller, stop_ambient_poller

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    start_scanner()
    start_ambient_poller()  # Add this line
    yield
    # Shutdown
    stop_scanner()
    stop_ambient_poller()  # Add this line
```

**Step 4: Verify module**

Run: `cd /home/ladmin/Projects/tilt_ui && python -c "from backend.ambient_poller import start_ambient_poller; print('OK')"`
Expected: `OK`

**Step 5: Commit**

```bash
git add backend/ambient_poller.py backend/websocket.py backend/main.py
git commit -m "feat: add ambient temperature polling background task"
```

---

### Task 7: Update Frontend Config Store

**Files:**
- Modify: `frontend/src/lib/stores/config.svelte.ts`

**Step 1: Add HA config fields to frontend store**

Update the `ConfigState` interface and default values in `frontend/src/lib/stores/config.svelte.ts`:

```typescript
interface ConfigState {
  temp_units: 'C' | 'F';
  sg_units: 'sg' | 'plato' | 'brix';
  local_logging_enabled: boolean;
  local_interval_minutes: number;
  min_rssi: number;
  smoothing_enabled: boolean;
  smoothing_samples: number;
  id_by_mac: boolean;
  // Home Assistant settings
  ha_enabled: boolean;
  ha_url: string;
  ha_token: string;
  ha_ambient_temp_entity_id: string;
  ha_ambient_humidity_entity_id: string;
  // Temperature control
  temp_control_enabled: boolean;
  temp_target: number;
  temp_hysteresis: number;
  ha_heater_entity_id: string;
  // Weather
  ha_weather_entity_id: string;
}

const DEFAULT_CONFIG: ConfigState = {
  temp_units: 'C',
  sg_units: 'sg',
  local_logging_enabled: true,
  local_interval_minutes: 15,
  min_rssi: -100,
  smoothing_enabled: false,
  smoothing_samples: 5,
  id_by_mac: false,
  // Home Assistant
  ha_enabled: false,
  ha_url: '',
  ha_token: '',
  ha_ambient_temp_entity_id: '',
  ha_ambient_humidity_entity_id: '',
  // Temperature control
  temp_control_enabled: false,
  temp_target: 68.0,
  temp_hysteresis: 1.0,
  ha_heater_entity_id: '',
  // Weather
  ha_weather_entity_id: '',
};
```

**Step 2: Commit**

```bash
git add frontend/src/lib/stores/config.svelte.ts
git commit -m "feat: add HA config fields to frontend store"
```

---

### Task 8: Add Home Assistant Settings Section to System Page

**Files:**
- Modify: `frontend/src/routes/system/+page.svelte`

**Step 1: Add HA state variables**

Add these state variables after the existing config state (around line 34):

```typescript
// Home Assistant state
let haEnabled = $state(false);
let haUrl = $state('');
let haToken = $state('');
let haAmbientTempEntityId = $state('');
let haAmbientHumidityEntityId = $state('');
let haWeatherEntityId = $state('');
let haTesting = $state(false);
let haTestResult = $state<{success: boolean; message: string} | null>(null);
let haStatus = $state<{enabled: boolean; connected: boolean; url: string} | null>(null);
```

**Step 2: Add sync function for HA settings**

Update `syncConfigFromStore()` to include HA fields:

```typescript
function syncConfigFromStore() {
  tempUnits = configState.config.temp_units;
  minRssi = configState.config.min_rssi;
  smoothingEnabled = configState.config.smoothing_enabled;
  smoothingSamples = configState.config.smoothing_samples;
  idByMac = configState.config.id_by_mac;
  // Home Assistant
  haEnabled = configState.config.ha_enabled;
  haUrl = configState.config.ha_url;
  haToken = configState.config.ha_token;
  haAmbientTempEntityId = configState.config.ha_ambient_temp_entity_id;
  haAmbientHumidityEntityId = configState.config.ha_ambient_humidity_entity_id;
  haWeatherEntityId = configState.config.ha_weather_entity_id;
}
```

**Step 3: Add HA test and status functions**

```typescript
async function testHAConnection() {
  haTesting = true;
  haTestResult = null;
  try {
    const response = await fetch('/api/ha/test', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: haUrl, token: haToken })
    });
    if (response.ok) {
      haTestResult = await response.json();
    } else {
      haTestResult = { success: false, message: 'Request failed' };
    }
  } catch (e) {
    haTestResult = { success: false, message: 'Network error' };
  } finally {
    haTesting = false;
  }
}

async function loadHAStatus() {
  try {
    const response = await fetch('/api/ha/status');
    if (response.ok) {
      haStatus = await response.json();
    }
  } catch (e) {
    console.error('Failed to load HA status:', e);
  }
}
```

**Step 4: Update saveConfig to include HA settings**

```typescript
async function saveConfig() {
  configSaving = true;
  configError = null;
  configSuccess = false;
  try {
    const result = await updateConfig({
      temp_units: tempUnits,
      min_rssi: minRssi,
      smoothing_enabled: smoothingEnabled,
      smoothing_samples: smoothingSamples,
      id_by_mac: idByMac,
      // Home Assistant
      ha_enabled: haEnabled,
      ha_url: haUrl,
      ha_token: haToken,
      ha_ambient_temp_entity_id: haAmbientTempEntityId,
      ha_ambient_humidity_entity_id: haAmbientHumidityEntityId,
      ha_weather_entity_id: haWeatherEntityId,
    });
    if (result.success) {
      configSuccess = true;
      setTimeout(() => configSuccess = false, 3000);
      // Reload HA status after saving
      await loadHAStatus();
    } else {
      configError = result.error || 'Failed to save settings';
    }
  } finally {
    configSaving = false;
  }
}
```

**Step 5: Add HA section to template**

Add this card after the "Application Settings" card (around line 423):

```svelte
<!-- Home Assistant Integration -->
<div class="card">
  <div class="card-header">
    <h2 class="card-title">Home Assistant</h2>
  </div>
  <div class="card-body">
    <!-- Enable/Disable -->
    <div class="setting-row">
      <div class="setting-info">
        <span class="setting-label">Enable Integration</span>
        <span class="setting-description">Connect to Home Assistant for ambient temp and control</span>
      </div>
      <button
        type="button"
        class="toggle"
        class:active={haEnabled}
        onclick={() => (haEnabled = !haEnabled)}
        aria-pressed={haEnabled}
      >
        <span class="toggle-slider"></span>
      </button>
    </div>

    {#if haEnabled}
      <!-- Connection Status -->
      {#if haStatus}
        <div class="setting-row">
          <div class="setting-info">
            <span class="setting-label">Connection Status</span>
          </div>
          <span class="status-badge" class:connected={haStatus.connected}>
            {haStatus.connected ? 'Connected' : 'Disconnected'}
          </span>
        </div>
      {/if}

      <!-- HA URL -->
      <div class="setting-row">
        <div class="setting-info">
          <span class="setting-label">Home Assistant URL</span>
          <span class="setting-description">e.g., http://192.168.1.100:8123</span>
        </div>
        <input
          type="url"
          bind:value={haUrl}
          placeholder="http://homeassistant.local:8123"
          class="input-field"
        />
      </div>

      <!-- HA Token -->
      <div class="setting-row">
        <div class="setting-info">
          <span class="setting-label">Access Token</span>
          <span class="setting-description">Long-lived access token from HA profile</span>
        </div>
        <input
          type="password"
          bind:value={haToken}
          placeholder="Enter token..."
          class="input-field"
        />
      </div>

      <!-- Test Connection -->
      <div class="setting-row">
        <div class="setting-info">
          <span class="setting-label">Test Connection</span>
        </div>
        <div class="test-connection">
          <button
            type="button"
            class="btn-secondary-sm"
            onclick={testHAConnection}
            disabled={haTesting || !haUrl || !haToken}
          >
            {haTesting ? 'Testing...' : 'Test'}
          </button>
          {#if haTestResult}
            <span class="test-result" class:success={haTestResult.success}>
              {haTestResult.message}
            </span>
          {/if}
        </div>
      </div>

      <!-- Ambient Temp Entity -->
      <div class="setting-row">
        <div class="setting-info">
          <span class="setting-label">Ambient Temp Entity</span>
          <span class="setting-description">e.g., sensor.fermenter_room_temperature</span>
        </div>
        <input
          type="text"
          bind:value={haAmbientTempEntityId}
          placeholder="sensor.xxx_temperature"
          class="input-field"
        />
      </div>

      <!-- Ambient Humidity Entity -->
      <div class="setting-row">
        <div class="setting-info">
          <span class="setting-label">Ambient Humidity Entity</span>
          <span class="setting-description">Optional humidity sensor</span>
        </div>
        <input
          type="text"
          bind:value={haAmbientHumidityEntityId}
          placeholder="sensor.xxx_humidity"
          class="input-field"
        />
      </div>

      <!-- Weather Entity -->
      <div class="setting-row">
        <div class="setting-info">
          <span class="setting-label">Weather Entity</span>
          <span class="setting-description">For forecast display, e.g., weather.home</span>
        </div>
        <input
          type="text"
          bind:value={haWeatherEntityId}
          placeholder="weather.home"
          class="input-field"
        />
      </div>
    {/if}
  </div>
</div>
```

**Step 6: Add styles for HA section**

Add to the `<style>` section:

```css
.input-field {
  width: 16rem;
  padding: 0.5rem 0.75rem;
  font-size: 0.8125rem;
  color: var(--text-primary);
  background: var(--bg-elevated);
  border: 1px solid var(--bg-hover);
  border-radius: 0.375rem;
}

.input-field:focus {
  outline: none;
  border-color: var(--amber-400);
}

.input-field::placeholder {
  color: var(--text-muted);
}

.status-badge {
  padding: 0.25rem 0.75rem;
  font-size: 0.75rem;
  font-weight: 500;
  border-radius: 9999px;
  background: rgba(244, 63, 94, 0.1);
  color: var(--tilt-red);
}

.status-badge.connected {
  background: rgba(16, 185, 129, 0.1);
  color: var(--tilt-green);
}

.test-connection {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.test-result {
  font-size: 0.75rem;
  color: var(--tilt-red);
}

.test-result.success {
  color: var(--tilt-green);
}
```

**Step 7: Load HA status on mount**

Update `onMount`:

```typescript
onMount(async () => {
  await Promise.all([
    loadSystemInfo(),
    loadStorageStats(),
    loadTimezones(),
    loadHAStatus()  // Add this
  ]);
  syncConfigFromStore();
  loading = false;
});
```

**Step 8: Commit**

```bash
git add frontend/src/routes/system/+page.svelte
git commit -m "feat: add Home Assistant settings UI on System page"
```

---

### Task 9: Add Ambient Temperature to Dashboard

**Files:**
- Modify: `frontend/src/lib/stores/tilts.svelte.ts` (handle ambient WS messages)
- Modify: `frontend/src/routes/+page.svelte` (display ambient)

**Step 1: Add ambient state to tilts store**

In `frontend/src/lib/stores/tilts.svelte.ts`, add ambient state:

```typescript
export interface AmbientReading {
  temperature: number | null;
  humidity: number | null;
  timestamp: string;
}

export const tiltsState = $state<{
  tilts: Map<string, TiltReading>;
  connected: boolean;
  ambient: AmbientReading | null;
}>({
  tilts: new Map(),
  connected: false,
  ambient: null
});
```

**Step 2: Handle ambient messages in WebSocket handler**

Update the `ws.onmessage` handler:

```typescript
ws.onmessage = (event) => {
  try {
    const data = JSON.parse(event.data);

    // Handle ambient readings
    if (data.type === 'ambient') {
      tiltsState.ambient = {
        temperature: data.temperature,
        humidity: data.humidity,
        timestamp: data.timestamp
      };
      return;
    }

    // Handle tilt readings (existing code)
    const reading: TiltReading = data;
    tiltsState.tilts.set(reading.id, reading);
    tiltsState.tilts = new Map(tiltsState.tilts);
  } catch (e) {
    console.error('Failed to parse WebSocket message:', e);
  }
};
```

**Step 3: Display ambient on dashboard**

In `frontend/src/routes/+page.svelte`, add ambient display after the Tilt cards grid:

```svelte
<!-- Ambient Temperature -->
{#if tiltsState.ambient && (tiltsState.ambient.temperature !== null || tiltsState.ambient.humidity !== null)}
  <div class="ambient-card">
    <div class="ambient-header">
      <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
        <path stroke-linecap="round" stroke-linejoin="round" d="M3 15a4 4 0 004 4h9a5 5 0 10-.1-9.999 5.002 5.002 0 10-9.78 2.096A4.001 4.001 0 003 15z" />
      </svg>
      <span>Room Ambient</span>
    </div>
    <div class="ambient-values">
      {#if tiltsState.ambient.temperature !== null}
        <div class="ambient-value">
          <span class="value">{formatTemp(tiltsState.ambient.temperature)}</span>
          <span class="unit">{getTempUnit()}</span>
          <span class="label">Temp</span>
        </div>
      {/if}
      {#if tiltsState.ambient.humidity !== null}
        <div class="ambient-value">
          <span class="value">{tiltsState.ambient.humidity.toFixed(0)}</span>
          <span class="unit">%</span>
          <span class="label">Humidity</span>
        </div>
      {/if}
    </div>
  </div>
{/if}
```

Add styles:

```css
.ambient-card {
  background: var(--bg-card);
  border: 1px solid var(--bg-hover);
  border-radius: 0.75rem;
  padding: 1rem 1.25rem;
  margin-top: 1rem;
}

.ambient-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.75rem;
  font-weight: 500;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 0.75rem;
}

.ambient-values {
  display: flex;
  gap: 2rem;
}

.ambient-value {
  display: flex;
  align-items: baseline;
  gap: 0.25rem;
}

.ambient-value .value {
  font-size: 1.5rem;
  font-weight: 600;
  font-family: 'JetBrains Mono', monospace;
  color: var(--text-primary);
}

.ambient-value .unit {
  font-size: 0.875rem;
  color: var(--text-secondary);
}

.ambient-value .label {
  font-size: 0.625rem;
  color: var(--text-muted);
  text-transform: uppercase;
  margin-left: 0.5rem;
}
```

**Step 4: Commit**

```bash
git add frontend/src/lib/stores/tilts.svelte.ts frontend/src/routes/+page.svelte
git commit -m "feat: display ambient temperature on dashboard"
```

---

### Task 10: Add Ambient Line to Chart

**Files:**
- Modify: `frontend/src/lib/api.ts` (add fetchAmbientHistory)
- Modify: `frontend/src/lib/components/TiltChart.svelte` (add third line)

**Step 1: Add API function for ambient history**

In `frontend/src/lib/api.ts`, add:

```typescript
export interface AmbientHistoricalReading {
  id: number;
  timestamp: string;
  temperature: number | null;
  humidity: number | null;
}

export async function fetchAmbientHistory(hours: number = 24): Promise<AmbientHistoricalReading[]> {
  const response = await fetch(`/api/ambient/history?hours=${hours}`);
  if (!response.ok) {
    throw new Error('Failed to fetch ambient history');
  }
  return response.json();
}
```

**Step 2: Update TiltChart to include ambient line**

In `frontend/src/lib/components/TiltChart.svelte`:

Add import and state:
```typescript
import { fetchReadings, fetchAmbientHistory, TIME_RANGES, type HistoricalReading, type AmbientHistoricalReading } from '$lib/api';

let ambientReadings = $state<AmbientHistoricalReading[]>([]);
```

Update `loadData()`:
```typescript
async function loadData() {
  loading = true;
  error = null;

  try {
    // Fetch both tilt and ambient readings in parallel
    const [tiltData, ambientData] = await Promise.all([
      fetchReadings(tiltId, selectedRange),
      fetchAmbientHistory(selectedRange).catch(() => [])  // Don't fail if ambient not available
    ]);
    readings = tiltData;
    ambientReadings = ambientData;
    updateChart();
  } catch (e) {
    error = e instanceof Error ? e.message : 'Failed to load data';
  } finally {
    loading = false;
  }
}
```

Update chart options to add 4th series (ambient temp):
```typescript
// In getChartOptions, add to series array:
{
  // Ambient Temp series
  label: 'Ambient',
  scale: 'temp',
  stroke: '#22d3ee',  // Cyan color for ambient
  width: 1,
  dash: [2, 2],
  points: { show: false },
  paths: uPlot.paths.spline?.()
}
```

Update `processData` to include ambient:
```typescript
function processData(readings: HistoricalReading[], ambientReadings: AmbientHistoricalReading[], celsius: boolean): uPlot.AlignedData {
  // ... existing code for timestamps, sgValues, tempValues ...

  // Create ambient temp array aligned to tilt timestamps
  const ambientMap = new Map(
    ambientReadings.map(r => [new Date(r.timestamp).getTime(), r.temperature])
  );

  let ambientValues: (number | null)[] = [];
  for (const r of sorted) {
    const ts = new Date(r.timestamp).getTime();
    // Find closest ambient reading within 5 minutes
    let closest: number | null = null;
    let closestDiff = Infinity;
    for (const [ambientTs, temp] of ambientMap) {
      const diff = Math.abs(ts - ambientTs);
      if (diff < 5 * 60 * 1000 && diff < closestDiff) {
        closest = temp;
        closestDiff = diff;
      }
    }
    if (closest !== null && celsius) {
      ambientValues.push(fahrenheitToCelsius(closest));
    } else {
      ambientValues.push(closest);
    }
  }

  // Apply smoothing and downsampling to all arrays...

  return [timestamps, sgValues, tempValues, ambientValues];
}
```

Update legend in template:
```svelte
<span class="legend-item">
  <span class="legend-line" style="background: #22d3ee;"></span>
  <span>Ambient</span>
</span>
```

**Step 3: Commit**

```bash
git add frontend/src/lib/api.ts frontend/src/lib/components/TiltChart.svelte
git commit -m "feat: add ambient temperature line to chart"
```

---

### Task 11: Build and Deploy Phase 10a

**Step 1: Build frontend**

Run: `cd /home/ladmin/Projects/tilt_ui/frontend && npm run build`

**Step 2: Commit built assets**

```bash
git add -A
git commit -m "build: Phase 10a - HA ambient temperature integration"
```

**Step 3: Push and deploy**

```bash
git push origin master
```

Deploy to Pi:
```bash
sshpass -p 'tilt' ssh pi@192.168.4.117 "cd /opt/tiltui && git pull && sudo systemctl restart tiltui"
```

**Step 4: Verify deployment**

1. Open http://192.168.4.117:8080/system
2. Scroll to "Home Assistant" section
3. Enable integration, enter HA URL and token
4. Test connection
5. Enter ambient sensor entity ID
6. Save settings
7. Go to Dashboard - should see ambient temp after ~30 seconds
8. Expand chart - should see ambient line

---

## Phase 10b: Temperature Control

(Tasks 12-17 for heater control logic - similar structure)

## Phase 10c: Weather Forecast + Alerts

(Tasks 18-22 for weather display and alerts)

## Phase 10d: BeerXML Import

(Tasks 23-28 for recipe parsing and tracking)

---

## Summary

This plan covers Phase 10a (11 tasks) to add Home Assistant connectivity and ambient temperature display. Subsequent phases build on this foundation.

**Key files created:**
- `backend/services/ha_client.py` - HA REST API client
- `backend/routers/ha.py` - HA API endpoints
- `backend/routers/ambient.py` - Ambient readings API
- `backend/ambient_poller.py` - Background polling task

**Key files modified:**
- `backend/models.py` - Config schema, AmbientReading model
- `backend/main.py` - Router registration, poller startup
- `frontend/src/lib/stores/config.svelte.ts` - HA config fields
- `frontend/src/lib/stores/tilts.svelte.ts` - Ambient state
- `frontend/src/routes/system/+page.svelte` - HA settings UI
- `frontend/src/routes/+page.svelte` - Ambient display
- `frontend/src/lib/components/TiltChart.svelte` - Ambient chart line
