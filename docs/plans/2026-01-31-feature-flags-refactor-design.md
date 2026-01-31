# Feature Flags Refactor Design

**Date:** 2026-01-31
**Status:** Approved
**Goal:** Clean separation between local and cloud deployments using feature flags

## Problem

The current codebase has scattered `if is_cloud` / `if not is_cloud` conditionals throughout `main.py`, auth, and other files. This makes the code harder to understand and maintain.

## Solution

Replace deployment-mode conditionals with explicit feature flags controlled by deployment presets.

### Key Principles

1. **Feature flags, not plugins** - Simple if/else checks, no abstraction overhead
2. **Deployment presets** - `DEPLOYMENT=local` or `DEPLOYMENT=cloud` sets sensible defaults
3. **Optional overrides** - Individual flags can override preset defaults via env vars
4. **Minimal changes** - Same functionality, clearer structure (~90 lines changed)

## Design

### Settings & Feature Flags

**File:** `backend/config.py`

```python
DEPLOYMENT_PRESETS = {
    "local": {
        "scanner": True,
        "ha": True,
        "mqtt": True,
        "control": True,
        "pollers": True,
        "gateway": False,
        "cloud_sync": False,
        "require_auth": False,
        "cleanup": True,
        "serve_frontend": True,
    },
    "cloud": {
        "scanner": False,
        "ha": False,
        "mqtt": False,
        "control": False,
        "pollers": False,
        "gateway": True,
        "cloud_sync": True,
        "require_auth": True,
        "cleanup": False,
        "serve_frontend": False,
    },
}

class Settings(BaseSettings):
    deployment: str = "local"

    # Existing settings
    database_url: str = "sqlite+aiosqlite:///./data/fermentation.db"
    supabase_url: Optional[str] = None
    supabase_jwt_secret: Optional[str] = None
    # ... etc

    # Feature flag overrides (None = use preset default)
    scanner_enabled: Optional[bool] = None
    ha_enabled: Optional[bool] = None
    mqtt_enabled: Optional[bool] = None
    control_enabled: Optional[bool] = None
    pollers_enabled: Optional[bool] = None
    gateway_enabled: Optional[bool] = None
    cloud_sync_enabled: Optional[bool] = None
    require_auth_enabled: Optional[bool] = None
    cleanup_enabled: Optional[bool] = None
    serve_frontend_enabled: Optional[bool] = None

    def is_enabled(self, feature: str) -> bool:
        """Check if feature is enabled (explicit override or preset default)."""
        override = getattr(self, f"{feature}_enabled", None)
        if override is not None:
            return override
        return DEPLOYMENT_PRESETS.get(self.deployment, {}).get(feature, False)

    @property
    def require_auth(self) -> bool:
        return self.is_enabled("require_auth")
```

### Main.py Lifespan Refactor

**File:** `backend/main.py`

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    global scanner, scanner_task, cleanup_service, ml_pipeline_manager

    settings = Settings()
    print(f"Starting BrewSignal ({settings.deployment.upper()} mode)...")

    # Core initialization (always runs)
    await init_db()
    ml_pipeline_manager = MLPipelineManager()

    # Feature-flagged services
    if settings.is_enabled("scanner"):
        load_readings_cache()
        scanner = TiltScanner(on_reading=handle_tilt_reading)
        scanner_task = asyncio.create_task(scanner.start())
        print("Scanner started")

    if settings.is_enabled("ha"):
        start_ambient_poller()
        await start_chamber_poller()
        print("HA integration started")

    if settings.is_enabled("control"):
        start_temp_controller()
        print("Temp controller started")

    if settings.is_enabled("mqtt"):
        start_mqtt_manager()
        print("MQTT started")

    if settings.is_enabled("cleanup"):
        cleanup_service = CleanupService(retention_days=30, interval_hours=1)
        await cleanup_service.start()
        print("Cleanup service started")

    if settings.is_enabled("gateway"):
        print("Gateway WebSocket enabled")

    yield

    # Shutdown (reverse order)
    print("Shutting down BrewSignal...")
    if settings.is_enabled("mqtt"):
        stop_mqtt_manager()
    if settings.is_enabled("control"):
        stop_temp_controller()
    if settings.is_enabled("ha"):
        stop_chamber_poller()
        stop_ambient_poller()
    if cleanup_service:
        await cleanup_service.stop()
    if scanner:
        await scanner.stop()
    if scanner_task:
        scanner_task.cancel()
```

### Auth Refactor

**File:** `backend/auth.py`

Minimal change - swap `is_cloud` for `require_auth`:

```python
# Line 85-89:
if settings.require_auth:
    raise HTTPException(status_code=401, detail="Authentication required")

# Line 184-185:
if not settings.require_auth:
    return AuthUser(user_id="local", email=None, role="local")
```

### Frontend Static Serving

**File:** `backend/main.py`

```python
_settings = Settings()
_serve_frontend = _settings.is_enabled("serve_frontend") and static_dir.exists()
```

## Feature Flag Reference

| Flag | Description | Local | Cloud |
|------|-------------|-------|-------|
| `scanner` | BLE Tilt scanning | Yes | No |
| `ha` | Home Assistant integration (pollers) | Yes | No |
| `mqtt` | MQTT publishing | Yes | No |
| `control` | Temperature controller | Yes | No |
| `pollers` | Ambient/chamber polling | Yes | No |
| `cleanup` | Reading cleanup service | Yes | No |
| `gateway` | Gateway WebSocket for ESP32 | No | Yes |
| `cloud_sync` | Premium cloud sync feature | No | Yes |
| `require_auth` | Require JWT authentication | No | Yes |
| `serve_frontend` | Serve static SvelteKit build | Yes | No |

## Configuration Examples

```bash
# Raspberry Pi (default local)
DEPLOYMENT=local

# Railway cloud
DEPLOYMENT=cloud

# Local dev without BLE hardware
DEPLOYMENT=local
SCANNER_ENABLED=false

# Local Pi that also accepts gateway connections
DEPLOYMENT=local
GATEWAY_ENABLED=true
```

## Auth Model

| State | Auth | user_id | Sync |
|-------|------|---------|------|
| Local anonymous | None | "local" | No |
| Local onboarded | Supabase JWT | Real UUID | No |
| Local + Cloud Sync (premium) | Supabase JWT | Real UUID | Yes |
| Cloud-only | Supabase JWT (required) | Real UUID | N/A |

## Migration Steps

| Step | Files Changed | Risk |
|------|---------------|------|
| 1. Add Settings with presets | `config.py` | None - additive |
| 2. Add `is_enabled()` method | `config.py` | None - not used yet |
| 3. Refactor auth | `auth.py` | Low - same behavior |
| 4. Refactor lifespan | `main.py` | Low - same behavior |
| 5. Refactor static serving | `main.py` | Low - same behavior |
| 6. Update `.env.example` | `.env.example` | None - docs only |
| 7. Delete old `is_cloud` | `config.py` | None - cleanup |

Each step is deployable and has instant rollback via `git checkout HEAD~1`.

## Files Changed

| File | Change Type | Lines (est.) |
|------|-------------|--------------|
| `backend/config.py` | Modify | +40 |
| `backend/auth.py` | Modify | ~4 |
| `backend/main.py` | Modify | ~30 |
| `.env.example` | Modify | +15 |

## What Stays Untouched

- All routers
- All models
- All services (scanner, mqtt, ha, etc.)
- Frontend
- Database
- Deployment scripts

## Rejected Alternatives

### Separate Packages/Apps (Original Plan)

The original plan proposed:
- `packages/core`, `packages/local`, `packages/cloud`, `packages/ui`
- `apps/api-local`, `apps/api-cloud`, `web-local`, `web-cloud`

**Rejected because:**
- Over-engineering for ~6 capabilities
- More files to maintain
- Cloud differences are mostly subtractions, not additions
- Feature flags achieve the same goal with less complexity

### Plugin Architecture

Formal plugin interface with Protocol classes and dynamic loading.

**Rejected because:**
- Over-engineering for a stable, small set of capabilities
- Adds indirection that complicates debugging
- Feature flags are simpler and sufficient
