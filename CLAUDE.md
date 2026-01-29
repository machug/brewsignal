# CLAUDE.md

## Project Overview

BrewSignal: Fermentation monitoring dashboard for Raspberry Pi. Supports Tilt BLE, iSpindel, GravityMon hydrometers with real-time monitoring, batch tracking, and per-batch temperature control via Home Assistant.

**Stack:** FastAPI + SQLAlchemy (backend), SvelteKit + TailwindCSS v4 (frontend), SQLite, uPlot charts

## Beads Workflow Tracking

**IMPORTANT:** Track all non-trivial work in beads. Issues are tracked at the parent level (`/brewsignal/.beads/`).

```bash
# Before starting work - check for existing issues or create one
bd ready                    # Show issues ready to work
bd create --title="..." --type=bug|task|feature --priority=2

# While working
bd update <id> --status=in_progress

# After completing work
bd close <id> --reason="Fixed in commit abc123"
bd sync
```

When fixing bugs, implementing features, or making significant changes:
1. Create or find the relevant beads issue
2. Update status to in_progress when starting
3. Close with commit reference when done
4. Run `bd sync` at session end

## Quick Reference

```bash
# Backend dev
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8080

# Frontend dev
cd frontend && npm run dev

# Build + Deploy to Pi (one-liner)
cd frontend && npm run build && cd .. && git add . && git commit -m "deploy" && git push && \
sshpass -p 'tilt' ssh pi@192.168.4.218 "cd /opt/brewsignal && git fetch origin && git reset --hard origin/master && sudo systemctl restart brewsignal"

# Pi SSH: pi@192.168.4.218 (password: tilt)
# Pi logs: sudo journalctl -u brewsignal -f
```

## Critical Rules

### Git Workflow: NEVER Work on Master
**ALWAYS create a feature branch before making changes.** Never commit directly to master.

```bash
# Before starting ANY work
git checkout master
git pull
git checkout -b feature/your-feature-name

# After work is complete, merge via PR or:
git checkout master
git merge feature/your-feature-name
git push
```

### Temperature: Always Celsius
All internal calculations, storage, and API responses use Celsius. Only Tilt BLE broadcasts Fahrenheit - convert immediately on ingestion. Frontend converts for display based on user preference.

### Database: Eager Loading Required
When serializing nested relationships, use `selectinload()` to avoid `MissingGreenlet` errors:
```python
# WRONG - causes MissingGreenlet
select(Batch).options(selectinload(Batch.recipe))

# RIGHT - eagerly loads nested relationship
select(Batch).options(selectinload(Batch.recipe).selectinload(Recipe.style))
```

### DateTime: UTC Serialization
Use `serialize_datetime_to_utc()` helper on Pydantic models:
```python
@field_serializer('created_at', 'updated_at')
def serialize_dt(self, dt: Optional[datetime]) -> Optional[str]:
    return serialize_datetime_to_utc(dt)
```

### Migrations
Manual migrations in `backend/database.py` via `init_db()`. Use `PRAGMA table_info()` to check columns. For complex changes, recreate table (SQLite limitation).

## Batch Lifecycle

**Status Flow:** Planning → Fermenting → Conditioning → Completed

**Reading Storage:** Only stored when status is "Fermenting" or "Conditioning". Live readings always visible via WebSocket regardless of status.

**Device Pairing:** Devices must be paired before logging. Unpaired devices appear on dashboard but don't persist readings.

**Soft Delete:** Batches use `deleted_at` timestamp. Hard delete cascades to readings.

## Temperature Control

Per-batch control via Home Assistant entities. Symmetric hysteresis with mutual exclusion (heater/cooler never simultaneous). 5-minute min cycle time.

## Environment Variables

- `SCANNER_MOCK=true` - Mock scanner for dev
- `SCANNER_RELAY_HOST=ip` - Relay from remote TiltPi
