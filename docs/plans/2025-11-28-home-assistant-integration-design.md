# Home Assistant Integration Design

**Date:** 2025-11-28
**Status:** Approved
**Related Issue:** #1 (Phase 10: Home Assistant Integration - Temperature Control)

## Overview

Integrate TiltUI with Home Assistant to:
1. Display ambient room temperature from Tapo T315 sensor
2. Overlay ambient temp on fermentation charts
3. Control a Tapo smart plug (heat mat) based on wort temperature
4. Display weather forecasts for predictive alerts
5. Import BeerXML recipes for fermentation tracking

## Architecture Decision

**Approach A: TiltUI-Controlled** (Selected)

TiltUI handles all control logic; Home Assistant acts as the device bridge.

```
[Tapo T315] → [Home Assistant] ←→ [TiltUI Backend] → [HA API] → [Tapo Smart Plug]
                    ↓                    ↓
              [Weather Entity]    [TiltUI Frontend]
```

**Rationale:**
- All control logic and history in one place (TiltUI)
- Single UI for monitoring + control settings
- HA just acts as the device bridge (what it does best)
- Matches existing TiltUI-centric workflow

## Implementation Phases

### Phase 10a: HA Connection + Ambient Temperature
- HA client service for REST API communication
- Ambient temperature polling and storage
- Display ambient temp on dashboard
- Overlay ambient temp on chart (third line)

### Phase 10b: Temperature Control
- Temperature controller background task
- Hysteresis-based heater control logic
- Control event logging
- UI for target temp and control settings

### Phase 10c: Weather Forecast + Alerts
- Weather forecast fetching from HA
- Predictive alerts engine
- "Tomorrow's forecast" display
- Alert notifications for temperature changes

### Phase 10d: BeerXML Import + Fermentation Tracking
- BeerXML parser
- Recipe storage and association with Tilt
- Fermentation progress tracking (current SG vs target FG)
- Yeast temp range suggestions

---

## Phase 10a: HA Connection + Ambient Temperature

### Configuration Schema

New fields in `config.json`:

```python
# Home Assistant connection
ha_enabled: bool = False
ha_url: str = ""                      # e.g., "http://192.168.1.100:8123"
ha_token: str = ""                    # Long-lived access token (sensitive)

# Ambient sensor
ha_ambient_temp_entity_id: str = ""   # e.g., "sensor.fermenter_room_temperature"
ha_ambient_humidity_entity_id: str = "" # e.g., "sensor.fermenter_room_humidity"
```

### Backend Components

#### 1. HA Client Service (`backend/ha_client.py`)

```python
class HAClient:
    """Async HTTP client for Home Assistant REST API."""

    async def test_connection() -> bool:
        """Validate HA URL and token."""

    async def get_state(entity_id: str) -> dict:
        """GET /api/states/{entity_id} - returns state + attributes."""

    async def call_service(domain: str, service: str, entity_id: str) -> bool:
        """POST /api/services/{domain}/{service} - e.g., switch/turn_on."""

    async def get_weather_forecast(entity_id: str) -> list[dict]:
        """Get weather forecast data."""
```

**API Endpoints Used:**
- `GET /api/states/<entity_id>` - Get sensor current state
- `POST /api/services/<domain>/<service>` - Control switches

**Authentication:**
- Header: `Authorization: Bearer <token>`
- Token obtained from HA: Settings → Profile → Long-Lived Access Tokens

#### 2. Ambient Poller (Background Task)

```python
async def ambient_poller():
    """Poll HA for ambient readings every 30 seconds."""
    while True:
        if config.ha_enabled and config.ha_ambient_temp_entity_id:
            temp = await ha_client.get_state(config.ha_ambient_temp_entity_id)
            humidity = await ha_client.get_state(config.ha_ambient_humidity_entity_id)

            # Store in database
            await db.add_ambient_reading(temp, humidity)

            # Broadcast via WebSocket
            await ws_manager.broadcast_ambient(temp, humidity)

        await asyncio.sleep(30)
```

### Database Schema

New table `ambient_readings`:

```sql
CREATE TABLE ambient_readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    temperature REAL,
    humidity REAL,
    entity_id TEXT
);

CREATE INDEX idx_ambient_timestamp ON ambient_readings(timestamp);
```

### API Endpoints

```
GET  /api/ha/status          - HA connection status
POST /api/ha/test            - Test HA connection with current config
GET  /api/ambient/current    - Current ambient temp/humidity
GET  /api/ambient/history    - Historical ambient readings (for chart)
     ?hours=24               - Time range filter
```

### WebSocket Messages

New message type for ambient updates:

```json
{
  "type": "ambient",
  "temperature": 19.5,
  "humidity": 65.2,
  "timestamp": "2025-11-28T12:00:00Z"
}
```

### Frontend Changes

#### Dashboard Card
- Add ambient temp display below Tilt readings
- Show humidity if available
- Visual indicator for HA connection status

#### Chart Enhancement
- Third line: ambient temperature (different color, e.g., cyan dashed)
- Legend update: "SG | Wort Temp | Ambient Temp"
- Shared temperature axis (right side)

#### System Page - Home Assistant Section
- Enable/disable toggle
- HA URL input
- Token input (password field)
- Test Connection button
- Entity ID inputs for ambient sensors
- Connection status indicator

---

## Phase 10b: Temperature Control

### Configuration Schema

```python
# Temperature control
temp_control_enabled: bool = False
temp_target: float = 68.0             # Target fermentation temp (in user's units)
temp_hysteresis: float = 1.0          # ± tolerance before triggering
ha_heater_entity_id: str = ""         # e.g., "switch.heat_mat_plug"
ha_cooler_entity_id: str = ""         # Optional for cooling setups
temp_control_mode: str = "heat"       # "heat", "cool", or "both"
```

### Temperature Controller Logic

```python
async def temperature_controller():
    """Control heater/cooler based on wort temperature."""
    while True:
        if not config.temp_control_enabled:
            await asyncio.sleep(60)
            continue

        # Get latest wort temp from active Tilt
        wort_temp = get_latest_tilt_temp()
        target = config.temp_target
        hysteresis = config.temp_hysteresis

        if wort_temp < (target - hysteresis):
            # Too cold - turn on heater
            if heater_state != "on":
                await ha_client.call_service("switch", "turn_on", config.ha_heater_entity_id)
                await log_control_event("heat_on", wort_temp)

        elif wort_temp > (target + hysteresis):
            # Too warm - turn off heater (or turn on cooler)
            if heater_state != "off":
                await ha_client.call_service("switch", "turn_off", config.ha_heater_entity_id)
                await log_control_event("heat_off", wort_temp)

        await asyncio.sleep(60)
```

### Control Events Table

```sql
CREATE TABLE control_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    tilt_id TEXT,
    action TEXT NOT NULL,  -- heat_on, heat_off, cool_on, cool_off
    wort_temp REAL,
    ambient_temp REAL,
    target_temp REAL
);
```

### API Endpoints

```
GET  /api/control/status     - Current control state (target, heater on/off)
GET  /api/control/events     - Control event history
POST /api/control/override   - Manual heater on/off (temporary override)
```

### Frontend - Temperature Control UI

New section on System page or dedicated page:
- Target temperature slider/input
- Hysteresis setting
- Heater entity ID
- Current state: "Heater: ON" / "Heater: OFF"
- Manual override buttons
- Control event log/timeline

---

## Phase 10c: Weather Forecast + Alerts

### Configuration Schema

```python
# Weather
ha_weather_entity_id: str = ""        # e.g., "weather.home"
weather_alerts_enabled: bool = False
alert_temp_threshold: float = 5.0     # Alert if forecast differs by this much
```

### Weather Service

```python
async def get_forecast() -> list[WeatherForecast]:
    """Fetch weather forecast from HA."""
    # Use HA service: weather.get_forecasts
    response = await ha_client.call_service(
        "weather", "get_forecasts",
        entity_id=config.ha_weather_entity_id,
        data={"type": "daily"}
    )
    return parse_forecast(response)

@dataclass
class WeatherForecast:
    datetime: datetime
    condition: str      # sunny, cloudy, rainy, etc.
    temperature: float  # High temp
    templow: float      # Low temp
```

### Predictive Alerts Engine

```python
def generate_alerts(forecast: list[WeatherForecast], target_temp: float) -> list[Alert]:
    """Generate predictive alerts based on forecast."""
    alerts = []

    for day in forecast[:3]:  # Next 3 days
        if day.templow < target_temp - 10:
            alerts.append(Alert(
                level="warning",
                message=f"{day.datetime.strftime('%A')}: Low of {day.templow}°, "
                        f"heater will likely run frequently"
            ))
        if day.temperature > target_temp + 10:
            alerts.append(Alert(
                level="warning",
                message=f"{day.datetime.strftime('%A')}: High of {day.temperature}°, "
                        f"consider cooling or moving fermenter"
            ))

    return alerts
```

### Frontend - Weather Display

- 3-day forecast cards on dashboard
- Alert banner when predictive alerts exist
- Weather icon + high/low temps

---

## Phase 10d: BeerXML Import + Fermentation Tracking

### BeerXML Parser

BeerXML 1.0 is an XML standard for beer recipes. Key fields:

```xml
<RECIPE>
  <NAME>My IPA</NAME>
  <STYLE><NAME>American IPA</NAME></STYLE>
  <OG>1.065</OG>
  <FG>1.012</FG>
  <YEASTS>
    <YEAST>
      <NAME>US-05</NAME>
      <MIN_TEMPERATURE>15.0</MIN_TEMPERATURE>
      <MAX_TEMPERATURE>22.0</MAX_TEMPERATURE>
    </YEAST>
  </YEASTS>
</RECIPE>
```

### Recipe Storage

```sql
CREATE TABLE recipes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    style TEXT,
    og REAL,
    fg REAL,
    yeast_name TEXT,
    yeast_temp_min REAL,
    yeast_temp_max REAL,
    beerxml_content TEXT,  -- Store original XML
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Link recipe to a Tilt/batch
ALTER TABLE tilts ADD COLUMN recipe_id INTEGER REFERENCES recipes(id);
```

### Fermentation Tracking

- Compare current SG to recipe OG/FG
- Calculate apparent attenuation: `(OG - SG) / (OG - 1) * 100`
- Estimate days remaining based on SG trend
- Suggest target temp from yeast temp range

### API Endpoints

```
POST /api/recipes/import     - Upload BeerXML file
GET  /api/recipes            - List recipes
GET  /api/recipes/{id}       - Get recipe details
POST /api/tilts/{id}/recipe  - Assign recipe to Tilt
GET  /api/tilts/{id}/progress - Fermentation progress vs recipe
```

### Frontend

- Recipe import on Calibration or new Recipes page
- Recipe selector dropdown on Tilt card
- Progress indicator: "65% attenuated, ~3 days to target FG"
- Suggested temp range from yeast profile

---

## Security Considerations

1. **HA Token Storage:** Token stored in `config.json` which should have restricted file permissions (600)
2. **Network:** HA API typically on local network; no external exposure needed
3. **Validation:** Validate entity IDs exist before using them
4. **Rate Limiting:** Poll intervals prevent API abuse (30s ambient, 60s weather)

## Testing Strategy

1. **Mock HA Server:** Create a mock HA API for development/testing
2. **Unit Tests:** HA client, temperature controller logic, BeerXML parser
3. **Integration Tests:** Full flow with mock HA responses
4. **Manual Testing:** Real HA instance with actual Tapo devices

## References

- [Home Assistant REST API](https://developers.home-assistant.io/docs/api/rest/)
- [TP-Link Smart Home Integration](https://www.home-assistant.io/integrations/tplink/)
- [BeerXML 1.0 Standard](http://www.beerxml.com/)
