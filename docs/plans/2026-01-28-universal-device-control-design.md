# Universal Device Control Layer

**Created**: 2026-01-28
**Beads Issue**: tilt_ui-xg4
**Status**: Design

## Problem Statement

BrewSignal currently only supports device control (heaters, coolers) through Home Assistant. This creates gaps:

| Deployment | Data Acquisition | Device Control |
|------------|-----------------|----------------|
| Local RPi + HA | BLE + HA polling | HA → Shelly |
| Local RPi (no HA) | BLE | **No mechanism** |
| Cloud + Gateway | **Not wired yet** | **No mechanism** |

**Goal**: Abstract device control so any deployment can control Shelly devices (and potentially others) regardless of whether Home Assistant is present.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    Temperature Controller                        │
│                   (backend/temp_controller.py)                   │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                   DeviceControlAdapter (ABC)                     │
│                                                                  │
│  + get_state(entity_id) → "on" | "off" | None                   │
│  + set_state(entity_id, state) → bool                           │
│  + discover_devices() → list[Device]                            │
│  + get_power_usage(entity_id) → float | None                    │
│  + test_connection() → bool                                      │
└────────────────────────────┬────────────────────────────────────┘
                             │
           ┌─────────────────┼─────────────────┐
           │                 │                 │
           ▼                 ▼                 ▼
    ┌────────────┐    ┌────────────┐    ┌────────────┐
    │ HAAdapter  │    │ShellyDirect│    │  Gateway   │
    │            │    │  Adapter   │    │  Adapter   │
    └────────────┘    └────────────┘    └────────────┘
           │                 │                 │
           ▼                 ▼                 ▼
    ┌────────────┐    ┌────────────┐    ┌────────────┐
    │    Home    │    │   Shelly   │    │   ESP32    │
    │ Assistant  │    │  (HTTP)    │    │  Gateway   │
    └────────────┘    └────────────┘    └────────────┘
                                               │
                                               ▼
                                        ┌────────────┐
                                        │   Shelly   │
                                        │  (local)   │
                                        └────────────┘
```

## Control Adapters

### 1. HAAdapter (Existing - Refactor)

The current `HAClient` wrapped in the adapter interface. Used when `ha_enabled=True`.

```python
class HAAdapter(DeviceControlAdapter):
    """Control devices via Home Assistant REST API."""

    def __init__(self, url: str, token: str):
        self._client = HAClient(url, token)

    async def get_state(self, entity_id: str) -> str | None:
        state = await self._client.get_state(entity_id)
        return state.get("state") if state else None

    async def set_state(self, entity_id: str, state: str) -> bool:
        service = "turn_on" if state == "on" else "turn_off"
        return await self._client.call_service("switch", service, entity_id)
```

### 2. ShellyDirectAdapter (New)

Direct HTTP control of Shelly devices without intermediary.

**Shelly Gen2 RPC API** (Gen2/Gen3 devices - Shelly Plus, Pro, etc):
```
GET  http://<ip>/rpc/Switch.GetStatus?id=0
POST http://<ip>/rpc/Switch.Set?id=0&on=true
POST http://<ip>/rpc/Switch.Set?id=0&on=false
GET  http://<ip>/rpc/Shelly.GetDeviceInfo
```

**Shelly Gen1 API** (Original Shelly 1, Plug, etc):
```
GET  http://<ip>/relay/0
POST http://<ip>/relay/0?turn=on
POST http://<ip>/relay/0?turn=off
GET  http://<ip>/shelly
```

```python
class ShellyDirectAdapter(DeviceControlAdapter):
    """Direct HTTP control of Shelly devices."""

    async def get_state(self, entity_id: str) -> str | None:
        """entity_id format: shelly://<ip>[:<port>][/channel]"""
        ip, channel = self._parse_entity_id(entity_id)

        # Try Gen2 API first
        try:
            resp = await self._client.get(f"http://{ip}/rpc/Switch.GetStatus?id={channel}")
            if resp.status_code == 200:
                return "on" if resp.json().get("output") else "off"
        except:
            pass

        # Fall back to Gen1 API
        resp = await self._client.get(f"http://{ip}/relay/{channel}")
        if resp.status_code == 200:
            return "on" if resp.json().get("ison") else "off"

        return None

    async def set_state(self, entity_id: str, state: str) -> bool:
        ip, channel = self._parse_entity_id(entity_id)
        on = state == "on"

        # Try Gen2 API
        try:
            resp = await self._client.post(
                f"http://{ip}/rpc/Switch.Set?id={channel}&on={str(on).lower()}"
            )
            if resp.status_code == 200:
                return True
        except:
            pass

        # Fall back to Gen1
        resp = await self._client.post(
            f"http://{ip}/relay/{channel}?turn={'on' if on else 'off'}"
        )
        return resp.status_code == 200

    async def discover_devices(self) -> list[dict]:
        """mDNS discovery for Shelly devices on local network."""
        # Use zeroconf to find _shelly._tcp.local services
        ...

    async def get_power_usage(self, entity_id: str) -> float | None:
        """Get power consumption in watts (Shelly Plug, PM models)."""
        ip, channel = self._parse_entity_id(entity_id)
        try:
            resp = await self._client.get(f"http://{ip}/rpc/Switch.GetStatus?id={channel}")
            return resp.json().get("apower")
        except:
            return None
```

### 3. GatewayRelayAdapter (New)

For cloud deployments, control commands are relayed through the ESP32 gateway.

```python
class GatewayRelayAdapter(DeviceControlAdapter):
    """Relay device control commands through ESP32 gateway."""

    def __init__(self, gateway_id: str, websocket_manager):
        self.gateway_id = gateway_id
        self.ws = websocket_manager

    async def set_state(self, entity_id: str, state: str) -> bool:
        """Send control command to gateway via WebSocket."""
        await self.ws.send_to_gateway(self.gateway_id, {
            "type": "device_control",
            "entity_id": entity_id,
            "action": "turn_on" if state == "on" else "turn_off"
        })

        # Wait for acknowledgment (with timeout)
        response = await self.ws.wait_for_ack(self.gateway_id, timeout=5.0)
        return response.get("success", False)
```

## Entity ID Format

Unified entity ID format to identify devices across different backends:

| Backend | Format | Example |
|---------|--------|---------|
| Home Assistant | `ha://switch.heat_mat` | `ha://switch.fermentation_heater` |
| Shelly Direct | `shelly://<ip>[/<channel>]` | `shelly://192.168.1.50/0` |
| Gateway Relay | `gateway://<gateway_id>/<shelly_ip>/<channel>` | `gateway://BSG-ABC123/192.168.1.50/0` |

The adapter router parses the prefix and dispatches to the correct adapter.

## Adapter Router

```python
class DeviceControlRouter:
    """Routes control commands to the appropriate adapter."""

    def __init__(self, config: AppConfig):
        self._adapters: dict[str, DeviceControlAdapter] = {}
        self._init_adapters(config)

    def _init_adapters(self, config: AppConfig):
        # HA adapter if configured
        if config.ha_enabled and config.ha_url and config.ha_token:
            self._adapters["ha"] = HAAdapter(config.ha_url, config.ha_token)

        # Shelly direct always available for local deployments
        if config.deployment_mode == "local":
            self._adapters["shelly"] = ShellyDirectAdapter()

        # Gateway adapter for cloud mode
        if config.deployment_mode == "cloud":
            self._adapters["gateway"] = GatewayRelayAdapter(ws_manager)

    def _get_adapter(self, entity_id: str) -> DeviceControlAdapter:
        prefix = entity_id.split("://")[0]
        if prefix not in self._adapters:
            raise ValueError(f"No adapter for {prefix}")
        return self._adapters[prefix]

    async def get_state(self, entity_id: str) -> str | None:
        adapter = self._get_adapter(entity_id)
        return await adapter.get_state(entity_id)

    async def set_state(self, entity_id: str, state: str) -> bool:
        adapter = self._get_adapter(entity_id)
        return await adapter.set_state(entity_id, state)
```

## Gateway WebSocket Protocol

### Connection Handshake

```
Gateway → Cloud: {"type": "hello", "gateway_id": "BSG-ABC123", "firmware": "1.0.0"}
Cloud → Gateway: {"type": "welcome", "session_id": "xxx", "interval_ms": 10000}
```

### Reading Upstream (Gateway → Cloud)

```json
{
  "type": "reading",
  "gateway_id": "BSG-ABC123",
  "device": {
    "type": "tilt",
    "color": "blue",
    "uuid": "A495BB60-C5B1-4B44-B512-1370F02D74DE"
  },
  "temp_c": 18.5,
  "gravity": 1.042,
  "rssi": -65,
  "timestamp": "2026-01-28T10:30:00Z"
}
```

### Commands Downstream (Cloud → Gateway)

**Device Control**:
```json
{
  "type": "device_control",
  "request_id": "req-123",
  "target": "shelly://192.168.1.50/0",
  "action": "turn_on"
}
```

**Response**:
```json
{
  "type": "device_control_ack",
  "request_id": "req-123",
  "success": true,
  "current_state": "on",
  "power_w": 45.2
}
```

**Target Temperature**:
```json
{
  "type": "set_target",
  "batch_id": 42,
  "temp_c": 18.0,
  "hysteresis": 0.5
}
```

### Heartbeat

```
Gateway → Cloud: {"type": "ping", "uptime_s": 3600}
Cloud → Gateway: {"type": "pong"}
```

## ESP32 Gateway Implementation

New modules to add to `brewsignal-gateway`:

### 1. WebSocket Client (ArduinoWebSockets)

```cpp
#include <WebSocketsClient.h>

WebSocketsClient webSocket;

void setupWebSocket() {
    webSocket.begin("api.brewsignal.io", 443, "/ws/gateway");
    webSocket.setReconnectInterval(5000);
    webSocket.onEvent(webSocketEvent);
}

void webSocketEvent(WStype_t type, uint8_t* payload, size_t length) {
    switch(type) {
        case WStype_CONNECTED:
            sendHello();
            break;
        case WStype_TEXT:
            handleCommand((char*)payload);
            break;
        case WStype_DISCONNECTED:
            // Will auto-reconnect
            break;
    }
}

void sendReading(const TiltReading& reading) {
    StaticJsonDocument<256> doc;
    doc["type"] = "reading";
    doc["gateway_id"] = gatewayId;
    doc["device"]["type"] = "tilt";
    doc["device"]["color"] = reading.color;
    doc["temp_c"] = reading.tempC;
    doc["gravity"] = reading.gravity;

    String json;
    serializeJson(doc, json);
    webSocket.sendTXT(json);
}
```

### 2. Shelly HTTP Control

```cpp
#include <HTTPClient.h>

bool controlShelly(const char* ip, int channel, bool turnOn) {
    HTTPClient http;

    // Try Gen2 API first
    String url = String("http://") + ip + "/rpc/Switch.Set?id=" + channel +
                 "&on=" + (turnOn ? "true" : "false");

    http.begin(url);
    int code = http.POST("");
    http.end();

    if (code == 200) return true;

    // Fall back to Gen1 API
    url = String("http://") + ip + "/relay/" + channel +
          "?turn=" + (turnOn ? "on" : "off");

    http.begin(url);
    code = http.POST("");
    http.end();

    return code == 200;
}

void handleCommand(const char* json) {
    StaticJsonDocument<512> doc;
    deserializeJson(doc, json);

    const char* type = doc["type"];

    if (strcmp(type, "device_control") == 0) {
        const char* target = doc["target"];
        const char* action = doc["action"];
        const char* requestId = doc["request_id"];

        // Parse shelly://192.168.1.50/0
        String targetStr = String(target);
        int ipStart = targetStr.indexOf("://") + 3;
        int channelStart = targetStr.lastIndexOf("/") + 1;
        String ip = targetStr.substring(ipStart, channelStart - 1);
        int channel = targetStr.substring(channelStart).toInt();

        bool on = strcmp(action, "turn_on") == 0;
        bool success = controlShelly(ip.c_str(), channel, on);

        // Send ack
        sendControlAck(requestId, success);
    }
}
```

## Configuration Model

### Batch Model Update

```python
class Batch(Base):
    # Existing fields...

    # Device control - unified entity IDs
    heater_entity_id: str | None  # e.g., "shelly://192.168.1.50/0"
    cooler_entity_id: str | None  # e.g., "ha://switch.fermentation_cooler"

    # For cloud deployments, link to gateway
    gateway_id: str | None  # e.g., "BSG-ABC123"
```

### System Config

```python
# New config keys
control_backend: str = "auto"  # "auto" | "ha" | "shelly_direct" | "gateway"

# Shelly direct config (when not using HA)
shelly_devices: list[dict] = [
    {"ip": "192.168.1.50", "name": "Fermentation Heater", "channel": 0},
    {"ip": "192.168.1.51", "name": "Fermentation Cooler", "channel": 0},
]
```

## UI Changes

### Device Configuration (non-HA)

New "Device Control" settings section when HA is disabled:

```
┌─────────────────────────────────────────────────────────┐
│ Device Control                                           │
├─────────────────────────────────────────────────────────┤
│ Control Backend: [Auto ▼]                                │
│                                                          │
│ ┌─ Shelly Devices ───────────────────────────────────┐  │
│ │ Name              IP              Status   Power   │  │
│ │ ─────────────────────────────────────────────────  │  │
│ │ Fermentation Heat 192.168.1.50   ● Online  42W    │  │
│ │ Fermentation Cool 192.168.1.51   ● Online  --     │  │
│ │                                                    │  │
│ │ [+ Add Device]  [Discover on Network]             │  │
│ └────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

### Batch Assignment

```
┌─────────────────────────────────────────────────────────┐
│ Temperature Control                                      │
├─────────────────────────────────────────────────────────┤
│ Target Temperature: [18.0] °C                            │
│ Hysteresis:         [0.5] °C                             │
│                                                          │
│ Heater: [Fermentation Heater (192.168.1.50) ▼]          │
│ Cooler: [Fermentation Cooler (192.168.1.51) ▼]          │
│                                                          │
│ Control Status: ● Auto (heater off, cooler off)         │
└─────────────────────────────────────────────────────────┘
```

## Implementation Plan

### Phase 1: Abstraction Layer (tilt_ui-xg4) ✅ COMPLETE
1. ✅ Create `DeviceControlAdapter` ABC - `backend/services/device_control/base.py`
2. ✅ Create `HAAdapter` wrapping existing `HAClient` - `backend/services/device_control/ha_adapter.py`
3. ✅ Create `DeviceControlRouter` - `backend/services/device_control/router.py`
4. ✅ Refactor `temp_controller.py` to use router

### Phase 2: Direct Shelly Support (tilt_ui-amh)
1. Implement `ShellyDirectAdapter` with Gen1/Gen2 API support
2. Add mDNS discovery using `zeroconf`
3. Add Shelly device configuration to system settings
4. Update entity ID parsing

### Phase 3: Gateway WebSocket (tilt_ui-123)
1. Add WebSocket client to ESP32 firmware
2. Implement reading upstream protocol
3. Add WebSocket endpoint to cloud backend
4. Gateway authentication (API key or JWT)

### Phase 4: Gateway Device Control (tilt_ui-a3d)
1. Add Shelly HTTP control to ESP32
2. Implement command downstream protocol
3. Create `GatewayRelayAdapter`
4. Add request/ack correlation

### Phase 5: UI (tilt_ui-vam)
1. Device discovery and configuration UI
2. Per-batch device assignment (non-HA mode)
3. Control status display

## Security Considerations

### Gateway Authentication
- Gateway registers with cloud using device ID + setup token
- Cloud issues JWT for WebSocket auth
- All communication over WSS (TLS)

### Local Network Security
- Shelly devices typically unauthed on local network
- Optional: Shelly auth support for Pro models
- Consider network segmentation recommendations

## Testing Strategy

1. **Unit tests**: Each adapter in isolation with mocked HTTP
2. **Integration tests**: Router with multiple adapters
3. **Hardware tests**:
   - Real Shelly device on local network
   - ESP32 gateway with test cloud endpoint
4. **E2E tests**: Cloud → Gateway → Shelly control loop

## Migration Path

Existing installations using HA continue to work unchanged. The router defaults to HA adapter when `ha_enabled=True`.

New config option `control_backend` allows override:
- `auto` (default): Use HA if enabled, else Shelly direct
- `ha`: Force HA only
- `shelly_direct`: Force direct Shelly (local RPi)
- `gateway`: Force gateway relay (cloud)

## Open Questions

1. **Ambient sensors**: Should we support Shelly H&T directly? Or only via gateway?
2. **Power monitoring**: How to surface energy usage in UI?
3. **Offline gateway**: Should gateway buffer control commands during cloud disconnect?
4. **Multi-gateway**: Can a user have multiple gateways (e.g., multiple fermentation locations)?
