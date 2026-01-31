# Outlier Filtering Design

**Date:** 2025-11-30
**Issue:** [#16 - Outlier readings causing extreme min/max statistics](https://github.com/machug/tilt_ui/issues/16)

## Problem

Impossible values (SG=5.075, Temp=3552°C) are stored without validation and corrupt statistics displays.

## Decision

Store outlier readings but flag them as `invalid` status. Use dual-layer filtering:
1. Backend marks new outliers on ingest
2. Frontend filters outliers from statistics calculations

## Valid Ranges

| Metric | Min | Max | Rationale |
|--------|-----|-----|-----------|
| Specific Gravity | 0.500 | 1.200 | Covers all brewing scenarios with margin |
| Temperature (°F) | 32 | 212 | Physical limits (freezing to boiling) |
| Temperature (°C) | 0 | 100 | Physical limits (freezing to boiling) |

## Layer 1: Backend (IngestManager)

**File:** `backend/services/ingest_manager.py`

Add validation after unit conversion, before database storage:

```python
SG_MIN, SG_MAX = 0.500, 1.200
TEMP_MIN_F, TEMP_MAX_F = 32.0, 212.0

def _validate_reading(self, reading: IngestReading) -> str:
    """Return 'invalid' if outlier, else original status."""
    sg = reading.sg_calibrated or reading.sg_raw
    temp = reading.temp_calibrated or reading.temp_raw

    if sg is not None and not (SG_MIN <= sg <= SG_MAX):
        return ReadingStatus.INVALID.value
    if temp is not None and not (TEMP_MIN_F <= temp <= TEMP_MAX_F):
        return ReadingStatus.INVALID.value
    return reading.status
```

Call this in `_store_reading()` before creating the Reading model.

## Layer 2: Frontend (FermentationStats)

**File:** `frontend/src/lib/components/FermentationStats.svelte`

Filter readings before calculating statistics:

```typescript
const SG_MIN = 0.5, SG_MAX = 1.2;
const TEMP_MIN_C = 0, TEMP_MAX_C = 100;

// Filter out invalid status AND out-of-range values (for historical data)
const validReadings = sorted.filter(r => r.status !== 'invalid');

const sgValues = validReadings
    .map(r => r.sg_calibrated ?? r.sg_raw)
    .filter((v): v is number => v !== null && v >= SG_MIN && v <= SG_MAX);

const tempValues = validReadings
    .map(r => r.temp_calibrated ?? r.temp_raw)
    .filter((v): v is number => v !== null && v >= TEMP_MIN_C && v <= TEMP_MAX_C);
```

## Why Dual-Layer?

- **Backend alone** wouldn't fix existing bad data already in DB
- **Frontend alone** wouldn't prevent new bad data from being stored
- **Both together** provides defense in depth

## Files to Modify

1. `backend/services/ingest_manager.py` - Add `_validate_reading()` method
2. `frontend/src/lib/components/FermentationStats.svelte` - Filter before stats calculation

## Testing

1. Verify existing outlier data is excluded from stats display
2. Send a test reading with SG=5.0, confirm it's stored with status='invalid'
3. Confirm valid readings (SG=1.050) are stored with status='valid'
