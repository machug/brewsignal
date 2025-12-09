# ML Pipeline Integration Plan Review
**Reviewer:** Kieran (Senior Rails/Python Developer)
**Plan:** `plans/integrate-ml-pipeline-with-main-application.md`
**Date:** 2025-12-09

---

## Executive Summary

**Overall Assessment:** Plan is solid with good phasing and pragmatic approach. However, there are **critical gaps** in error handling, state management edge cases, and integration testing strategy. The plan treats ML as "nice to have" when it should be architected for reliability at scale.

**Key Concerns:**
1. WebSocket broadcasting has no ML failure mode strategy
2. State hydration lacks transaction safety and rollback
3. No monitoring/observability for ML in production
4. Integration tests are missing for the actual endpoints being created
5. Type safety gaps in Python (Optional types used inconsistently)

**Verdict:** **NEEDS REVISION** - Address critical concerns before Phase 1 implementation.

---

## Critical Issues (Must Fix Before Implementation)

### 1. WebSocket Broadcasting Error Handling (Phase 1)

**Current Plan (lines 216-234 in main.py):**
```python
# Update in-memory latest_readings cache
latest_readings[reading.id] = {
    "sg": sg_calibrated,
    "temp": temp_calibrated,
    # Missing ML fields!
}
```

**Problem:**
The plan says "Add ML fields to latest_readings dict" but doesn't specify:
- What happens when `ml_outputs` is empty dict (ML failure)?
- Should we broadcast `None` or omit the keys entirely?
- How does frontend distinguish "no ML yet" vs "ML failed" vs "ML disabled"?

**Required:**
```python
# Option A: Always include keys (cleaner for frontend)
latest_readings[reading.id] = {
    "sg": sg_calibrated,
    "temp": temp_calibrated,
    # ML fields - always present, None if unavailable
    "sg_filtered": ml_outputs.get("sg_filtered"),
    "temp_filtered": ml_outputs.get("temp_filtered"),
    "confidence": ml_outputs.get("confidence"),
    "is_anomaly": ml_outputs.get("is_anomaly", False),
    "ml_status": "ok" if ml_outputs else "disabled",  # NEW: explicit status
}

# Option B: Nested structure (better for schema evolution)
latest_readings[reading.id] = {
    "sg": sg_calibrated,
    "temp": temp_calibrated,
    "ml": {
        "available": bool(ml_outputs),
        "sg_filtered": ml_outputs.get("sg_filtered"),
        "temp_filtered": ml_outputs.get("temp_filtered"),
        "confidence": ml_outputs.get("confidence"),
        "is_anomaly": ml_outputs.get("is_anomaly", False),
    } if ml_outputs else None
}
```

**Recommendation:** Use Option B (nested structure). Prevents namespace pollution and makes schema evolution easier.

**Impact:** HIGH - This affects every WebSocket consumer and chart rendering.

---

### 2. State Hydration Transaction Safety (Phase 2)

**Current Plan (lines 173-271 in pipeline_manager.py):**
```python
async def reload_from_database(self, device_id, batch_id, db_session):
    # Query readings
    # Load history into pipeline
    # No transaction handling!
```

**Problems:**
1. **Race Condition:** What if new readings arrive during hydration?
2. **Partial State:** If hydration fails mid-way, pipeline is in inconsistent state
3. **No Rollback:** Can't restore previous ML state if hydration fails
4. **Database Lock:** Loading 2 weeks of data (2016 readings) with no pagination

**Required Fix:**
```python
async def reload_from_database(
    self,
    device_id: str,
    batch_id: int,
    db_session,
    max_readings: int = 5000  # NEW: prevent unbounded queries
) -> dict:
    """Reload ML pipeline history from database readings.

    CRITICAL: This operation is NOT atomic. New readings may arrive during
    hydration, creating a "split brain" where some readings are in the old
    state and others in the new state.

    Mitigation: Only call during service startup or when no readings are
    actively being processed.
    """
    # Snapshot current state for rollback
    old_pipeline = self.pipelines.get(device_id)

    try:
        # Create new pipeline instance (don't mutate existing)
        new_pipeline = MLPipeline(self.config)

        # Query with limit to prevent OOM
        query = (
            select(Reading)
            .where(Reading.batch_id == batch_id)
            .where(Reading.device_id == device_id)
            .order_by(Reading.timestamp.desc())  # Get latest first
            .limit(max_readings)
        )

        result = await db_session.execute(query)
        readings = result.scalars().all()

        if not readings:
            return {
                "success": False,
                "readings_loaded": 0,
                "error": "No readings found for batch"
            }

        # Reverse to chronological order
        readings = list(reversed(readings))

        # Build data arrays
        # ... (existing logic)

        # Load history into NEW pipeline (not existing one)
        new_pipeline.load_history(sgs=sgs, temps=temps, times=times)

        # Atomic swap (only if successful)
        self.pipelines[device_id] = new_pipeline

        logger.info(
            f"Reloaded {len(sgs)} readings from database for device {device_id}"
        )

        return {
            "success": True,
            "readings_loaded": len(sgs),
            "error": None
        }

    except Exception as e:
        logger.error(f"Failed to reload from database: {e}")
        # Restore old state if it existed
        if old_pipeline:
            self.pipelines[device_id] = old_pipeline
        return {
            "success": False,
            "readings_loaded": 0,
            "error": str(e)
        }
```

**Impact:** CRITICAL - Without this, hydration failures leave ML in broken state.

---

### 3. Missing Integration Tests (All Phases)

**Current Plan:**
- "Integration tests: API endpoints return valid predictions" (line 470)
- No actual test code provided
- Relies on unit tests (48/48) but those don't test FastAPI endpoints

**Problem:**
Looking at `/home/ladmin/Projects/tilt_ui/tests/test_ml_integration_e2e.py`, I see ONE test that covers:
- `handle_tilt_reading()` function
- Database storage
- WebSocket broadcast

But the plan adds THREE new API endpoints in Phase 2:
- `GET /api/batches/{id}/predictions`
- `POST /api/batches/{id}/reload-ml`
- Auto-hydration in lifespan()

**Required:**
```python
# File: tests/test_ml_api_endpoints.py

@pytest.mark.asyncio
async def test_predictions_endpoint_returns_valid_data():
    """Test GET /api/batches/{id}/predictions."""
    # Setup: Create batch with 50 readings
    # Call endpoint
    # Assert: predicted_fg is float, estimated_completion is ISO datetime
    # Assert: r_squared > 0.8 (good fit)
    pass

@pytest.mark.asyncio
async def test_predictions_endpoint_handles_insufficient_data():
    """Test predictions with <10 readings."""
    # Setup: Create batch with 5 readings
    # Call endpoint
    # Assert: available=false, predicted_fg=None
    pass

@pytest.mark.asyncio
async def test_reload_ml_endpoint_hydrates_state():
    """Test POST /api/batches/{id}/reload-ml."""
    # Setup: Create batch with 100 readings
    # Restart MLPipelineManager (fresh state)
    # Call reload endpoint
    # Assert: readings_loaded == 100
    # Call predictions endpoint
    # Assert: predictions available
    pass

@pytest.mark.asyncio
async def test_reload_ml_handles_concurrent_readings():
    """Test reload while new readings arrive (race condition)."""
    # Setup: Create batch with 50 readings
    # Start reload in background task
    # Send new reading via handle_tilt_reading
    # Assert: No errors, state is consistent
    pass

@pytest.mark.asyncio
async def test_startup_hydration_for_active_batches():
    """Test lifespan() auto-hydration."""
    # Setup: Create 3 active batches (fermenting/conditioning)
    # Create 1 completed batch (should NOT hydrate)
    # Trigger lifespan startup
    # Assert: 3 pipelines hydrated, 1 skipped
    pass
```

**Impact:** HIGH - Can't ship to production without integration tests.

---

### 4. Type Safety Gaps in Python

**Current Code (models.py:132-143):**
```python
# ML outputs - Kalman filtered values (Celsius)
sg_filtered: Mapped[Optional[float]] = mapped_column()
temp_filtered: Mapped[Optional[float]] = mapped_column()

# ML outputs - Confidence and rates
confidence: Mapped[Optional[float]] = mapped_column()  # 0.0-1.0
sg_rate: Mapped[Optional[float]] = mapped_column()     # d(SG)/dt in points/hour
temp_rate: Mapped[Optional[float]] = mapped_column()   # d(temp)/dt in °C/hour
```

**Problem:**
`Optional[float]` means "could be None OR could be float". But there's no validation:
- `confidence` should be constrained to 0.0-1.0 (not -5.0 or 100.0)
- `sg_rate` could be absurd values (1000.0 points/hour)
- `anomaly_score` same issue

**Current Plan (models.py:873-880 - ReadingResponse):**
```python
# ML outputs
sg_filtered: Optional[float] = None
temp_filtered: Optional[float] = None
confidence: Optional[float] = None
sg_rate: Optional[float] = None
temp_rate: Optional[float] = None
is_anomaly: Optional[bool] = None
anomaly_score: Optional[float] = None
anomaly_reasons: Optional[str] = None
```

**Required:**
```python
from pydantic import BaseModel, Field, field_validator

class ReadingResponse(BaseModel):
    # ... existing fields ...

    # ML outputs with validation
    sg_filtered: Optional[float] = Field(None, ge=0.990, le=1.200)
    temp_filtered: Optional[float] = Field(None, ge=-10.0, le=50.0)  # Celsius
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    sg_rate: Optional[float] = Field(None, ge=-0.1, le=0.1)  # Reasonable fermentation rate
    temp_rate: Optional[float] = Field(None, ge=-5.0, le=5.0)  # °C/hour
    is_anomaly: Optional[bool] = None
    anomaly_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    anomaly_reasons: Optional[str] = None  # JSON string

    @field_validator('anomaly_reasons')
    @classmethod
    def validate_json_array(cls, v: Optional[str]) -> Optional[str]:
        """Ensure anomaly_reasons is valid JSON array if present."""
        if v is None:
            return v
        try:
            reasons = json.loads(v)
            if not isinstance(reasons, list):
                raise ValueError("anomaly_reasons must be JSON array")
            return v
        except json.JSONDecodeError:
            raise ValueError("anomaly_reasons must be valid JSON")
```

**Impact:** MEDIUM - Prevents garbage data from corrupting charts and predictions.

---

### 5. No Monitoring/Observability (Production Readiness)

**Current Plan:**
- Phase 3 mentions "ML Metrics Dashboard" (lines 163-167)
- But only for UI display, not production monitoring

**Missing:**
1. **ML Processing Time Metrics:**
   - Plan says "<10ms per reading" but no way to measure in production
   - No alerting if processing suddenly takes 500ms (blocking readings)

2. **ML Failure Rate:**
   - Plan logs errors but doesn't track failure percentage
   - If ML fails 50% of the time, would anyone know?

3. **State Hydration Delays:**
   - "State hydration completes in <5 seconds" - how do we verify?
   - What if it takes 60 seconds and blocks startup?

4. **Anomaly Detection Accuracy:**
   - "90% accuracy" - how is this measured in production?
   - No feedback loop to improve thresholds

**Required:**
```python
# File: backend/ml/metrics.py
from dataclasses import dataclass, field
from time import time
from collections import deque

@dataclass
class MLMetrics:
    """Production metrics for ML pipeline."""

    # Processing time (rolling window)
    processing_times_ms: deque = field(default_factory=lambda: deque(maxlen=1000))

    # Failure tracking
    total_readings: int = 0
    ml_failures: int = 0

    # Hydration tracking
    last_hydration_duration_ms: Optional[float] = None
    hydration_failures: int = 0

    def record_processing_time(self, duration_ms: float):
        """Record ML processing time."""
        self.processing_times_ms.append(duration_ms)
        self.total_readings += 1

    def record_failure(self):
        """Record ML pipeline failure."""
        self.ml_failures += 1
        self.total_readings += 1

    def get_failure_rate(self) -> float:
        """Get ML failure rate (0.0-1.0)."""
        if self.total_readings == 0:
            return 0.0
        return self.ml_failures / self.total_readings

    def get_p95_processing_time_ms(self) -> float:
        """Get 95th percentile processing time."""
        if not self.processing_times_ms:
            return 0.0
        sorted_times = sorted(self.processing_times_ms)
        idx = int(len(sorted_times) * 0.95)
        return sorted_times[idx]

# Global metrics instance
ml_metrics = MLMetrics()


# File: backend/routers/system.py (add endpoint)
@router.get("/api/system/ml-metrics")
async def get_ml_metrics():
    """Get ML pipeline production metrics."""
    from backend.ml.metrics import ml_metrics

    return {
        "total_readings": ml_metrics.total_readings,
        "failure_rate": ml_metrics.get_failure_rate(),
        "p95_processing_time_ms": ml_metrics.get_p95_processing_time_ms(),
        "avg_processing_time_ms": sum(ml_metrics.processing_times_ms) / len(ml_metrics.processing_times_ms) if ml_metrics.processing_times_ms else 0,
        "last_hydration_duration_ms": ml_metrics.last_hydration_duration_ms,
        "hydration_failures": ml_metrics.hydration_failures,
    }
```

**Usage in main.py:**
```python
from backend.ml.metrics import ml_metrics
from time import perf_counter

# In handle_tilt_reading()
if ml_pipeline_manager:
    try:
        start = perf_counter()
        ml_outputs = ml_pipeline_manager.process_reading(...)
        duration_ms = (perf_counter() - start) * 1000
        ml_metrics.record_processing_time(duration_ms)

        # Alert if processing is slow
        if duration_ms > 50:  # 5x expected time
            logging.warning(f"Slow ML processing: {duration_ms:.1f}ms for {reading.id}")
    except Exception as e:
        ml_metrics.record_failure()
        logging.error(f"ML pipeline failed for {reading.id}: {e}")
```

**Impact:** CRITICAL for production - Can't debug what you can't measure.

---

## Major Issues (Should Fix in Phase 1)

### 6. Dashboard Display Logic Ambiguity (Phase 1)

**Plan says (lines 64-67):**
> Show filtered SG/temp instead of calibrated (smoother, less noisy)
> Add confidence badge (🟢 High >0.8, 🟡 Medium 0.5-0.8, 🔴 Low <0.5)
> Add anomaly alert banner when `is_anomaly === true`

**Questions:**
1. **Fallback Logic:** What if `sg_filtered` is `null`? Show `sg_calibrated`? Show "N/A"?
2. **Historical Data:** Existing readings have no ML fields. Do charts break?
3. **Toggle Behavior:** Can users switch back to raw data? Or force them to ML view?

**Required Spec:**
```typescript
// File: frontend/src/routes/+page.svelte

function getDisplaySG(reading: HistoricalReading): number | null {
    // Priority order: filtered > calibrated > raw > null
    return reading.sg_filtered ?? reading.sg_calibrated ?? reading.sg_raw ?? null;
}

function getDisplayTemp(reading: HistoricalReading): number | null {
    return reading.temp_filtered ?? reading.temp_calibrated ?? reading.temp_raw ?? null;
}

function getConfidenceBadge(confidence: number | null | undefined): string {
    if (confidence === null || confidence === undefined) {
        return "⚪ No ML";  // Distinguish from low confidence
    }
    if (confidence > 0.8) return "🟢 High";
    if (confidence > 0.5) return "🟡 Medium";
    return "🔴 Low";
}
```

**Impact:** MEDIUM - Prevents user confusion when ML is not available.

---

### 7. Anomaly Reasons Parsing (Phase 3)

**Current Schema (models.py:143):**
```python
anomaly_reasons: Mapped[Optional[str]] = mapped_column(Text)  # JSON array
```

**Current Handling (main.py:208):**
```python
anomaly_reasons=json.dumps(ml_outputs.get("anomaly_reasons", [])) if ml_outputs.get("anomaly_reasons") else None,
```

**Problem:**
- Frontend receives JSON **string**, not array
- Frontend has to parse it: `JSON.parse(reading.anomaly_reasons)`
- What if parsing fails? Chart breaks.

**Better Approach:**
```python
# Option 1: Parse in Pydantic serializer
class ReadingResponse(BaseModel):
    anomaly_reasons: Optional[list[str]] = None  # Send as array, not string

    @field_serializer('anomaly_reasons')
    def serialize_reasons(self, v: Optional[str]) -> Optional[list[str]]:
        """Convert JSON string to array for frontend."""
        if v is None:
            return None
        try:
            return json.loads(v)
        except json.JSONDecodeError:
            logging.error(f"Invalid anomaly_reasons JSON: {v}")
            return []

# Option 2: Use JSON column type (SQLite 3.38+ / PostgreSQL)
# This is cleaner but requires migration
from sqlalchemy import JSON
anomaly_reasons: Mapped[Optional[list[str]]] = mapped_column(JSON)
```

**Recommendation:** Use Option 2 (JSON column). Cleaner and safer.

**Impact:** MEDIUM - Prevents JSON parsing bugs in frontend.

---

### 8. Feature Flag Exposure (Phase 2)

**Current Plan:**
- MLConfig exists with feature flags (enable_kalman, enable_anomaly, etc.)
- But no API endpoint to read config
- No way to verify which features are enabled in production

**Required:**
```python
# File: backend/routers/system.py
@router.get("/api/system/ml-config")
async def get_ml_config():
    """Get ML feature configuration (read-only)."""
    from backend.main import ml_pipeline_manager

    if not ml_pipeline_manager:
        return {"enabled": False}

    config = ml_pipeline_manager.config
    return {
        "enabled": True,
        "features": {
            "kalman_filter": config.enable_kalman_filter,
            "anomaly_detection": config.enable_anomaly_detection,
            "predictions": config.enable_predictions,
            "mpc": config.enable_mpc,
            "slm": config.enable_slm,
        },
        "parameters": {
            "anomaly_min_history": config.anomaly_min_history,
            "prediction_min_readings": config.prediction_min_readings,
        }
    }
```

**Impact:** LOW - But needed for debugging production issues.

---

## Minor Issues (Nice to Have)

### 9. Naming Consistency

**Good:**
- `sg_filtered`, `temp_filtered` - Clear what they are
- `confidence` - Standard ML term
- `is_anomaly` - Boolean naming convention

**Questionable:**
- `sg_rate` - Is this derivative? Velocity? Rate of change?
  - Better: `sg_derivative` or `d_sg_dt` (more precise)
- `anomaly_score` - Score on what scale? What does 0.7 mean?
  - Better: `anomaly_probability` or `anomaly_confidence`

**Recommendation:** Keep current names (already in database), but add comments clarifying units.

---

### 10. Database Index Missing

**Current Schema (models.py:132-143):**
```python
sg_filtered: Mapped[Optional[float]] = mapped_column()
is_anomaly: Mapped[Optional[bool]] = mapped_column(default=False)
```

**Problem:**
If users want to query "all anomalies for this batch":
```sql
SELECT * FROM readings WHERE batch_id = 5 AND is_anomaly = true;
```
This does a full table scan (no index on `is_anomaly`).

**Better:**
```python
# Add composite index for common queries
__table_args__ = (
    Index('ix_readings_batch_anomaly', 'batch_id', 'is_anomaly'),
    Index('ix_readings_device_timestamp', 'device_id', 'timestamp'),
)
```

**Impact:** LOW - Only matters with large datasets (>10k readings).

---

### 11. Phase 3 Chart Toggle Implementation Gap

**Plan says (lines 152-157):**
> Add toggle to show raw vs filtered data
> Plot `sg_filtered` as smooth line, `sg_calibrated` as scatter points
> Add confidence band (±1σ) around filtered line
> Color-code anomaly points in red

**Question:**
How do you render confidence bands with uPlot? The plan doesn't specify:
- Is this a filled area between two series?
- Do you compute `sg_filtered + 1σ` and `sg_filtered - 1σ`?
- Where does `σ` (standard deviation) come from? Not in database schema!

**Required:**
Either:
1. Add `uncertainty` field to database schema (predicted by Kalman filter)
2. Use fixed band (e.g., ±0.002 SG) for visual purposes only
3. Compute from historical variance (expensive)

**Recommendation:** Option 2 (fixed band) for Phase 3. Option 1 for Phase 4 if users request it.

**Impact:** LOW - Feature not critical, but plan should clarify.

---

## Testing Strategy Gaps

### 12. No Regression Tests for Reading Ingestion

**Current Tests:**
- `test_ml_integration_e2e.py` - ONE test for basic flow
- ML unit tests (48 tests) - Don't touch FastAPI

**Missing:**
1. **Performance Regression:** Does ML slow down reading ingestion?
   - Need benchmark: "Ingest 1000 readings in <5 seconds"
2. **Memory Regression:** Does ML cause memory leaks?
   - Need test: "Process 10,000 readings, memory usage <100 MB growth"
3. **Concurrent Readings:** Can ML handle burst of readings?
   - Need test: "Send 50 readings/second for 10 seconds, no errors"

**Required:**
```python
# File: tests/test_ml_performance.py
import pytest
import asyncio
from time import perf_counter

@pytest.mark.asyncio
async def test_reading_ingestion_performance():
    """Ensure ML doesn't slow down reading ingestion."""
    # Setup: 1000 readings
    readings = [create_test_reading(i) for i in range(1000)]

    start = perf_counter()
    for reading in readings:
        await handle_tilt_reading(reading)
    duration = perf_counter() - start

    assert duration < 5.0, f"Ingestion took {duration:.2f}s (expected <5s)"
    print(f"Ingestion rate: {len(readings)/duration:.1f} readings/sec")

@pytest.mark.asyncio
async def test_concurrent_reading_burst():
    """Test ML handles burst of concurrent readings."""
    readings = [create_test_reading(i) for i in range(50)]

    # Send all readings concurrently
    tasks = [handle_tilt_reading(r) for r in readings]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Assert: No exceptions raised
    errors = [r for r in results if isinstance(r, Exception)]
    assert len(errors) == 0, f"Got {len(errors)} errors during burst"
```

**Impact:** MEDIUM - Can't ship to production without performance validation.

---

## Edge Cases Not Covered

### 13. ML State Staleness

**Scenario:**
1. Batch fermenting for 7 days (2016 readings in ML state)
2. User changes batch status to "completed" (stops logging)
3. 2 weeks pass
4. User restarts batch (status back to "fermenting")
5. ML pipeline still has stale state from 2 weeks ago

**Current Plan:** No handling for this. ML will use old state and make nonsensical predictions.

**Required:**
```python
# In batch status transition (when starting new batch)
if old_status != "fermenting" and new_status == "fermenting":
    # Reset ML pipeline for fresh start
    if ml_pipeline_manager:
        ml_pipeline_manager.reset_pipeline(
            device_id=batch.device_id,
            initial_sg=batch.original_gravity or 1.050,
            initial_temp=20.0  # Default temp
        )
        logging.info(f"Reset ML pipeline for device {batch.device_id} (batch {batch.id})")
```

**Impact:** LOW - Edge case, but would cause confusing UX if hit.

---

### 14. Database Hydration with Missing Calibration

**Scenario:**
1. User collects 100 readings (stored with `sg_calibrated`)
2. User deletes calibration points
3. User triggers ML reload
4. `sg_calibrated` becomes `None` for all readings
5. ML hydration fails with "No readings found"

**Current Code (pipeline_manager.py:230-234):**
```python
sg = reading.sg_filtered if reading.sg_filtered is not None else reading.sg_calibrated
temp = reading.temp_filtered if reading.temp_filtered is not None else reading.temp_calibrated

if sg is None or temp is None:
    continue  # Skip readings with missing data
```

**Result:** Hydration silently skips all readings, returns "success" with 0 readings loaded.

**Better:**
```python
if sg is None or temp is None:
    skipped_count += 1
    continue

# After loop
if skipped_count > 0:
    logger.warning(f"Skipped {skipped_count} readings with missing data during hydration")

if len(sgs) == 0 and skipped_count > 0:
    return {
        "success": False,
        "readings_loaded": 0,
        "error": f"All {skipped_count} readings have missing calibration data"
    }
```

**Impact:** LOW - Rare, but error message would help debugging.

---

### 15. WebSocket Message Size Growth

**Current Plan:**
> WebSocket message size increase <50% (ML fields are compact)

**Reality Check:**
Current message (main.py:216-231): ~200 bytes
```json
{
  "id": "BLUE",
  "device_id": "BLUE",
  "color": "BLUE",
  "beer_name": "My IPA",
  "sg": 1.050,
  "temp": 20.0,
  "rssi": -60
}
```

Adding ML fields: +8 fields × ~20 bytes/field = ~160 bytes
New total: ~360 bytes (80% increase, not 50%)

With 10 devices broadcasting every 30 seconds:
- Old: 10 × 200 bytes × 120 msgs/hour = 240 KB/hour
- New: 10 × 360 bytes × 120 msgs/hour = 432 KB/hour

**Not a problem** for WebSocket, but plan's estimate is wrong.

**Impact:** NONE - Just note the estimate is low.

---

## Documentation Requirements

### 16. Missing User-Facing Documentation

**Plan mentions (lines 388-401):**
- Update README with ML features section
- Create "Understanding ML Predictions" guide
- Add FAQ for anomaly detection

**Reality:** These are **critical** for Phase 1 launch. Without docs:
- Users won't understand confidence badges
- Users will panic when seeing anomaly alerts
- Users will file bugs: "Why is my SG different from before?" (filtered vs raw)

**Required Content:**
```markdown
# ML Features Guide

## Filtered Readings
BrewSignal uses Kalman filtering to smooth noisy sensor data. The **filtered** values are more accurate than raw readings and should be used for:
- Fermentation tracking
- Gravity-based alerts
- FG predictions

**When to trust filtered values:**
- Confidence: 🟢 High (>80%) - Trust filtered value
- Confidence: 🟡 Medium (50-80%) - Use with caution
- Confidence: 🔴 Low (<50%) - Use raw readings instead

## Anomaly Detection
Anomalies are readings that don't follow expected fermentation patterns:
- **Stuck Fermentation:** SG hasn't changed in 24+ hours
- **Temperature Spike:** Temp changed >5°F in 1 hour
- **Unrealistic Drop:** SG dropped >0.010 in 1 hour (sensor error)

**What to do:**
1. Check Tilt placement (not stuck to side)
2. Verify calibration is current
3. Inspect fermentation chamber for issues
4. If all looks normal, click "Dismiss" to ignore

## Predictions
After 10+ readings, BrewSignal predicts your final gravity (FG) and completion date.

**Accuracy:**
- Early fermentation (0-3 days): ±0.005 SG
- Mid fermentation (4-7 days): ±0.003 SG
- Late fermentation (8+ days): ±0.001 SG

**When predictions fail:**
- Not enough data (<10 readings)
- Atypical fermentation (stuck, temperature swings)
- Multiple strains (blend fermentations)
```

**Impact:** CRITICAL - Can't ship user-facing features without documentation.

---

## Positive Aspects (What's Good)

1. **Phased Approach:** Breaking into 3 phases is smart. Can ship Phase 1 independently.
2. **Graceful Degradation:** ML failures don't crash reading ingestion (line 186-187).
3. **Feature Flags:** MLConfig allows disabling features without code changes.
4. **Existing Tests:** 48/48 ML unit tests give confidence in core algorithms.
5. **Database Schema:** ML columns already exist, no migrations needed.
6. **TypeScript Types:** Frontend types include ML fields (api.ts:15-18).
7. **Naming Conventions:** Field names are clear and consistent.
8. **Performance Estimates:** Plan includes realistic overhead estimates (<10ms).
9. **Alternative Approaches:** Plan documents rejected approaches with rationale.
10. **Risk Analysis Table:** Identifies risks and mitigations upfront (lines 298-305).

---

## Recommendations Summary

### Before Phase 1 Implementation:

1. **CRITICAL:** Add nested `ml` object to WebSocket broadcast (Issue #1)
2. **CRITICAL:** Add production metrics and monitoring (Issue #5)
3. **HIGH:** Fix state hydration transaction safety (Issue #2)
4. **HIGH:** Write integration tests for new API endpoints (Issue #3)
5. **MEDIUM:** Add Pydantic field validation for ML outputs (Issue #4)
6. **MEDIUM:** Clarify dashboard fallback logic (Issue #6)
7. **LOW:** Add `GET /api/system/ml-config` endpoint (Issue #8)

### Before Phase 2 Implementation:

8. **HIGH:** Add batch status transition ML reset (Issue #13)
9. **MEDIUM:** Write performance regression tests (Issue #12)
10. **MEDIUM:** Improve hydration error messages (Issue #14)

### Before Phase 3 Implementation:

11. **MEDIUM:** Use JSON column for `anomaly_reasons` (Issue #7)
12. **LOW:** Clarify confidence band rendering (Issue #11)
13. **LOW:** Add database index for anomaly queries (Issue #10)

### Documentation (Before ANY release):

14. **CRITICAL:** Write "Understanding ML Predictions" user guide (Issue #16)

---

## Final Verdict

**Plan Quality:** 7/10
- Good phasing and architecture
- Realistic performance estimates
- Covers most happy paths

**Production Readiness:** 4/10
- Missing monitoring/observability
- Integration tests are minimal
- Error handling has gaps
- Documentation is weak

**Recommendation:**
**REVISE AND RESUBMIT** - Address critical issues (#1, #2, #3, #5, #16) before starting implementation. The ML code is solid, but the integration layer needs more rigor.

---

## Code Review Checklist

Use this checklist during implementation:

### Phase 1: Real-time ML Broadcasting
- [ ] WebSocket broadcast uses nested `ml` object structure
- [ ] Frontend handles missing ML fields gracefully
- [ ] Dashboard shows confidence badges with "No ML" state
- [ ] Anomaly alerts have dismiss button
- [ ] User documentation for ML features written
- [ ] Manual test: Restart service, verify ML resumes
- [ ] Manual test: Trigger anomaly, verify alert appears

### Phase 2: Predictions API & State Hydration
- [ ] `GET /api/batches/{id}/predictions` endpoint implemented
- [ ] `POST /api/batches/{id}/reload-ml` endpoint implemented
- [ ] Integration test for predictions endpoint (success case)
- [ ] Integration test for predictions endpoint (insufficient data)
- [ ] Integration test for reload endpoint (success)
- [ ] Integration test for reload endpoint (concurrent readings)
- [ ] Integration test for startup hydration (active batches)
- [ ] Hydration uses atomic swap pattern (no partial state)
- [ ] Hydration has max_readings limit (prevent OOM)
- [ ] Production metrics collected and exposed via API
- [ ] Manual test: Reload after calibration change
- [ ] Manual test: Restart service, predictions persist

### Phase 3: Advanced Visualization
- [ ] Chart toggle between raw/filtered works
- [ ] Anomaly panel parses JSON reasons correctly
- [ ] System page shows ML metrics
- [ ] Confidence bands render correctly
- [ ] Performance test: 10k readings render in <2s
- [ ] Manual test: Toggle chart, verify smoothing visible
- [ ] Manual test: View anomaly details, reasons make sense

---

## Questions for Plan Author

1. **WebSocket Structure:** Prefer nested `ml` object or flat structure? (See Issue #1)
2. **Hydration Timing:** Should reload endpoint be synchronous (wait for hydration) or async (return immediately)?
3. **Anomaly Dismissal:** Should dismissed anomalies be stored in database?
4. **Confidence Threshold:** Why 0.8 for "high" confidence? Based on testing or arbitrary?
5. **Database Size:** Have you calculated storage growth? 8 new columns × 4 bytes × 1M readings = 32 MB
6. **RPi Performance:** Have you tested ML pipeline on actual Raspberry Pi 4? ARM performance?
7. **Monitoring:** Do you have Grafana/Prometheus? Or custom dashboard only?
8. **Feature Flags:** Should these be configurable at runtime or compile-time only?

---

## Appendix: Proposed API Contracts

### GET /api/batches/{id}/predictions

**Response (success):**
```json
{
  "available": true,
  "predicted_fg": 1.012,
  "predicted_og": 1.050,
  "estimated_completion": "2025-12-15T14:30:00Z",
  "hours_to_completion": 48.5,
  "model_type": "exponential",
  "r_squared": 0.92,
  "confidence": "high",
  "readings_used": 45
}
```

**Response (insufficient data):**
```json
{
  "available": false,
  "predicted_fg": null,
  "predicted_og": null,
  "estimated_completion": null,
  "hours_to_completion": null,
  "model_type": null,
  "r_squared": null,
  "confidence": "none",
  "readings_used": 5,
  "error": "Insufficient readings (need 10, got 5)"
}
```

### POST /api/batches/{id}/reload-ml

**Request Body:**
```json
{
  "max_readings": 5000  // Optional, default 5000
}
```

**Response (success):**
```json
{
  "success": true,
  "readings_loaded": 287,
  "error": null,
  "duration_ms": 234,
  "skipped_readings": 3
}
```

**Response (failure):**
```json
{
  "success": false,
  "readings_loaded": 0,
  "error": "No readings found for batch",
  "duration_ms": 12,
  "skipped_readings": 0
}
```

### GET /api/system/ml-metrics

**Response:**
```json
{
  "enabled": true,
  "total_readings": 1543,
  "failure_rate": 0.002,
  "p95_processing_time_ms": 8.2,
  "avg_processing_time_ms": 4.7,
  "last_hydration_duration_ms": 234,
  "hydration_failures": 0,
  "active_pipelines": 3
}
```

---

**End of Review**
