# Integrate ML Pipeline with Main Application

**GitHub Issue:** #62
**Type:** Feature Enhancement
**Priority:** Medium
**Complexity:** Medium

## Overview

The ML pipeline is complete and tested (PR #61, 48/48 tests passing) with Kalman filtering, anomaly detection, curve fitting, and MPC. The backend integration is partially complete - ML outputs are stored in the database but not exposed to users. This plan completes the integration by adding WebSocket broadcasting, API endpoints, state persistence, and frontend visualization.

## Current State

### ✅ Complete

**Backend ML Infrastructure:**
- `backend/ml/pipeline_manager.py` - Per-device ML pipeline instances
- `backend/ml/pipeline.py` - Core ML pipeline (Kalman, anomaly, predictions)
- `backend/ml/config.py` - ML configuration with feature flags
- Database schema includes ML fields: `sg_filtered`, `temp_filtered`, `confidence`, `sg_rate`, `temp_rate`, `is_anomaly`, `anomaly_score`, `anomaly_reasons`
- `backend/main.py:247` - MLPipelineManager initialized in lifespan
- `backend/main.py:174-188` - ML processing integrated into `handle_tilt_reading()`
- `backend/main.py:201-208` - ML outputs stored in Reading model

**Frontend Types:**
- `frontend/src/lib/api.ts:15-18` - TypeScript types include ML fields

### ❌ Missing

**Real-time Updates:**
- ML outputs NOT included in WebSocket broadcasts (`backend/main.py:216-234`)
- ML outputs NOT in `latest_readings` cache
- No separate `ml_update` WebSocket message type for predictions

**API Endpoints:**
- No `/api/batches/{id}/predictions` endpoint for FG estimates
- No `/api/devices/{id}/ml-state` endpoint for ML metrics
- No `/api/ml/reload` endpoint to hydrate from database

**State Persistence:**
- ML state lost on service restart (in-memory only)
- No hydration from database on startup
- ~157 KB per device lost on crash/restart

**Frontend Visualization:**
- Dashboard shows `sg_calibrated`, not `sg_filtered`
- No confidence indicators or anomaly alerts
- No FG prediction display
- No ML-smoothed chart lines

## Proposed Solution

### Phase 1: Real-time ML Broadcasting (Quick Win)

**Goal:** Make ML outputs visible in real-time without requiring service restart

**Changes:**

1. **Update WebSocket Broadcast** (`backend/main.py:216-234`)
   - Add ML fields to `latest_readings` dict
   - Include `sg_filtered`, `temp_filtered`, `confidence`, `is_anomaly`
   - Broadcast happens on every reading (existing flow)

2. **Add Dashboard ML Display** (`frontend/src/routes/+page.svelte`)
   - Show filtered SG/temp instead of calibrated (smoother, less noisy)
   - Add confidence badge (🟢 High >0.8, 🟡 Medium 0.5-0.8, 🔴 Low <0.5)
   - Add anomaly alert banner when `is_anomaly === true`

**Files Modified:**
- `backend/main.py` (lines 216-231)
- `frontend/src/routes/+page.svelte` (dashboard cards)

**Acceptance Criteria:**
- [ ] WebSocket broadcasts include `sg_filtered`, `temp_filtered`, `confidence`, `is_anomaly`
- [ ] Dashboard displays filtered values instead of calibrated
- [ ] Confidence indicator visible on dashboard cards
- [ ] Anomaly alerts appear in real-time when detected

**Estimated Effort:** 2-4 hours

---

### Phase 2: Predictions API & State Hydration (Core Value)

**Goal:** Expose fermentation predictions and ensure ML state survives restarts

**Changes:**

1. **Add Predictions API Endpoint** (`backend/routers/batches.py`)
   ```python
   # File: backend/routers/batches.py:500
   @router.get("/api/batches/{batch_id}/predictions")
   async def get_batch_predictions(
       batch_id: int,
       db: AsyncSession = Depends(get_db)
   ):
       """Get ML predictions for active batch."""
       # Get active device for batch
       # Call ml_pipeline_manager.get_device_state(device_id)
       # Return FG estimate, completion time, confidence
   ```

2. **Add ML State Reload Endpoint** (`backend/routers/batches.py`)
   ```python
   # File: backend/routers/batches.py:530
   @router.post("/api/batches/{batch_id}/reload-ml")
   async def reload_ml_state(
       batch_id: int,
       device_id: str,
       db: AsyncSession = Depends(get_db)
   ):
       """Hydrate ML pipeline from database readings."""
       # Call ml_pipeline_manager.reload_from_database()
       # Returns success, readings_loaded, error
   ```

3. **Auto-hydrate on Batch Start** (`backend/main.py` lifespan)
   - On startup, query active batches (status='fermenting' or 'conditioning')
   - For each batch, call `reload_from_database()` with last 48 hours
   - Ensures predictions work immediately after service restart

4. **Batch Detail Predictions Display** (`frontend/src/routes/batches/[id]/+page.svelte`)
   - Fetch `/api/batches/{id}/predictions` on mount
   - Display FG estimate with confidence interval
   - Show estimated completion date
   - Add "Recalculate" button that calls `/reload-ml` endpoint

**Files Created/Modified:**
- `backend/routers/batches.py` (new endpoints)
- `backend/main.py` (lifespan hydration logic)
- `frontend/src/routes/batches/[id]/+page.svelte` (predictions section)
- `frontend/src/lib/api.ts` (prediction types and API calls)

**Acceptance Criteria:**
- [ ] `/api/batches/{id}/predictions` returns FG estimate, completion time, confidence
- [ ] `/api/batches/{id}/reload-ml` hydrates ML state from database
- [ ] Service startup auto-hydrates ML state for active batches
- [ ] Batch detail page shows FG prediction with confidence
- [ ] "Recalculate" button reloads ML state
- [ ] ML state survives service restarts (predictions don't reset to zero)

**Estimated Effort:** 6-8 hours

---

### Phase 3: Advanced Visualization (Polish)

**Goal:** Rich ML visualization for power users and debugging

**Changes:**

1. **ML-Filtered Chart Series** (`frontend/src/lib/components/FermentationChart.svelte`)
   - Add toggle to show raw vs filtered data
   - Plot `sg_filtered` as smooth line, `sg_calibrated` as scatter points
   - Add confidence band (±1σ) around filtered line
   - Color-code anomaly points in red

2. **Anomaly Details Panel** (`frontend/src/routes/batches/[id]/+page.svelte`)
   - List all anomaly events with timestamps
   - Show `anomaly_reasons` (parsed from JSON)
   - Examples: "Stuck fermentation", "Temperature spike", "Unrealistic SG drop"

3. **ML Metrics Dashboard** (`frontend/src/routes/system/+page.svelte`)
   - Show active ML pipelines count
   - Per-device history buffer size
   - ML processing overhead (avg ms per reading)
   - Feature flag status from `MLConfig`

**Files Modified:**
- `frontend/src/lib/components/FermentationChart.svelte` (filtered series)
- `frontend/src/routes/batches/[id]/+page.svelte` (anomaly panel)
- `frontend/src/routes/system/+page.svelte` (ML metrics)
- `backend/routers/system.py` (ML metrics endpoint)

**Acceptance Criteria:**
- [ ] Chart shows toggle for "Raw" vs "Filtered" data
- [ ] Filtered SG/temp lines visibly smoother than raw
- [ ] Anomaly points highlighted in red on chart
- [ ] Anomaly panel lists all detected anomalies with reasons
- [ ] System page shows ML pipeline status and metrics

**Estimated Effort:** 8-10 hours

---

## Technical Considerations

### Performance

**Current Overhead:**
- ML pipeline processing: ~5-10ms per reading (measured in tests)
- Kalman filter: ~1ms
- Anomaly detection: ~2-3ms
- Curve fitting: ~3-5ms (only when history >= 10 readings)

**Optimization Strategies:**
- ML processing is synchronous (no `await`) - already non-blocking for FastAPI
- Database writes happen after ML processing (correct order)
- Consider caching predictions for 5-10 minutes if API endpoint gets heavy traffic

### State Management

**In-Memory State Size:**
- Each device stores ~2 weeks of history: 2016 readings × 2 floats × 8 bytes = ~32 KB
- With derivatives and metadata: ~157 KB per device
- 10 devices = ~1.6 MB total (acceptable)

**Database Hydration:**
- Query last 48 hours on startup: `WHERE timestamp > NOW() - INTERVAL 48 HOUR`
- Typical fermentation: ~288 readings (6/hour × 48 hours)
- Load time: <100ms per device

### Error Handling

**Graceful Degradation:**
- If ML pipeline fails, fall back to calibrated values (current behavior)
- Log errors but don't crash reading handler
- Frontend shows "N/A" for missing ML fields

**Validation:**
- ML outputs validated in tests (48/48 passing)
- Anomaly detection based on fermentation physics (not arbitrary thresholds)
- Confidence scores provide user visibility into ML uncertainty

### Feature Flags

**MLConfig** (`backend/ml/config.py`):
- `enable_kalman: bool = True` - Toggle Kalman filtering
- `enable_anomaly_detection: bool = True` - Toggle anomaly detection
- `enable_predictions: bool = True` - Toggle curve fitting
- `enable_mpc: bool = False` - MPC not yet integrated (Phase 4)

## Alternative Approaches Considered

### Option 1: Separate ML Results Table

**Approach:** Create `ml_results` table instead of adding columns to `readings`

**Pros:**
- Clean separation of raw vs ML data
- Easier to rebuild ML state without touching raw data
- Could store multiple ML model versions

**Cons:**
- Extra JOIN on every batch query
- More complex hydration logic
- Denormalized data (reading_id foreign key)

**Decision:** Rejected - ML outputs are tightly coupled to readings, JOIN overhead not worth it

### Option 2: Compute ML On-Demand

**Approach:** Don't store ML outputs, compute when needed via API

**Pros:**
- No database bloat
- Can recompute with different ML parameters
- Easier to experiment with models

**Cons:**
- Slow API responses (need to process 2 weeks of data)
- Can't display anomalies that happened in the past
- No WebSocket real-time updates

**Decision:** Rejected - Real-time visibility is core value prop

### Option 3: Redis for ML State

**Approach:** Store ML state in Redis instead of SQLite

**Pros:**
- Fast in-memory access
- Built-in TTL for old state
- Better for distributed systems

**Cons:**
- Extra dependency (adds complexity to RPi deployment)
- State not queryable in same SQL queries as readings
- Overhead for single-instance deployment

**Decision:** Deferred to future if scaling becomes issue

## Dependencies & Prerequisites

**Code Dependencies:**
- ✅ PR #61 merged (ML pipeline implementation)
- ✅ Database migrations complete (ML columns exist)
- ✅ TypeScript types updated

**Infrastructure:**
- ✅ SQLite async support (already in use)
- ✅ WebSocket infrastructure (working)
- ✅ uPlot charting library (installed)

**No Blockers Identified**

## Risk Analysis & Mitigation

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| ML processing slows down reading ingestion | High | Low | Already tested at <10ms, async architecture |
| State hydration causes startup delay | Medium | Low | Limit to 48 hours, async initialization |
| Frontend bundle size increases | Low | Low | ML code is backend-only, minimal frontend changes |
| Anomaly false positives confuse users | Medium | Medium | Tune thresholds, add "Dismiss" button |
| Database bloat from ML columns | Low | Low | 8 new columns × 4-8 bytes = 32-64 bytes/reading |

## Implementation Checklist

### Phase 1: Real-time ML Broadcasting

- [ ] Update `backend/main.py:216-231` to include ML fields in `latest_readings`
- [ ] Modify `frontend/src/routes/+page.svelte` dashboard cards to show filtered values
- [ ] Add confidence badge component
- [ ] Add anomaly alert banner
- [ ] Test WebSocket broadcasts include ML data
- [ ] Test dashboard updates in real-time
- [ ] Verify anomaly alerts appear when triggered

### Phase 2: Predictions API & State Hydration

- [ ] Create `GET /api/batches/{id}/predictions` endpoint
- [ ] Create `POST /api/batches/{id}/reload-ml` endpoint
- [ ] Add auto-hydration logic to `lifespan()` in `backend/main.py`
- [ ] Update `frontend/src/lib/api.ts` with prediction types
- [ ] Add predictions section to batch detail page
- [ ] Add "Recalculate" button
- [ ] Test predictions endpoint returns valid FG estimates
- [ ] Test state survives service restart
- [ ] Test manual reload via button

### Phase 3: Advanced Visualization

- [ ] Add filtered series toggle to FermentationChart
- [ ] Implement confidence band rendering
- [ ] Color-code anomaly points on chart
- [ ] Create anomaly details panel
- [ ] Add ML metrics to system page
- [ ] Create `GET /api/system/ml-metrics` endpoint
- [ ] Test chart toggle switches between raw/filtered
- [ ] Test anomalies appear in panel with reasons
- [ ] Test system metrics display correctly

## Success Metrics

**User-Facing:**
- Smoother charts (reduce visual noise by 50%+)
- FG predictions within ±0.003 SG of actual
- Anomaly detection accuracy >90% (validate against known issues)
- Zero user complaints about performance degradation

**Technical:**
- ML processing overhead <10ms per reading
- State hydration completes in <5 seconds on startup
- WebSocket message size increase <50% (ML fields are compact)
- No increase in database query times

## Future Considerations

### Phase 4: MPC Temperature Control (Deferred)

**Goal:** Use ML-predicted fermentation trajectory to optimize temperature control

**Changes:**
- Enable `MLConfig.enable_mpc = True`
- Integrate MPC controller with temperature control loop
- Predict temperature trajectory to minimize overshoot
- Learn system dynamics (heater/cooler response times)

**Complexity:** High - requires extensive testing and validation

**Status:** Deferred until Phases 1-3 proven stable

### Phase 5: Multi-Model Comparison (Future)

**Goal:** A/B test different ML models or parameters

**Changes:**
- Store multiple ML results per reading (`ml_results` table)
- UI toggle to compare models side-by-side
- Metrics dashboard to evaluate model performance

**Complexity:** Medium-High

**Status:** Research phase, pending user feedback on Phase 1-3

## Documentation Requirements

**Code Documentation:**
- [ ] Add docstrings to new API endpoints
- [ ] Document WebSocket message format changes
- [ ] Add inline comments for hydration logic

**User Documentation:**
- [ ] Update README with ML features section
- [ ] Create "Understanding ML Predictions" guide
- [ ] Add FAQ for anomaly detection

**Developer Documentation:**
- [ ] Update `CLAUDE.md` with ML integration notes
- [ ] Document ML feature flags in config
- [ ] Add troubleshooting guide for ML errors

## References & Research

### Internal Code References

**ML Pipeline Implementation:**
- `backend/ml/pipeline_manager.py:29-41` - Pipeline creation and lifecycle
- `backend/ml/pipeline_manager.py:74-140` - Process reading and flatten outputs
- `backend/ml/pipeline_manager.py:142-171` - Get device state and predictions
- `backend/ml/pipeline_manager.py:173-271` - Reload from database

**Current Integration Points:**
- `backend/main.py:32` - MLPipelineManager import
- `backend/main.py:42` - Global ml_pipeline_manager instance
- `backend/main.py:174-188` - ML processing in handle_tilt_reading()
- `backend/main.py:201-208` - ML outputs stored to database
- `backend/main.py:247` - MLPipelineManager initialized in lifespan

**Database Schema:**
- `backend/models.py:132-143` - Reading model ML fields
- `backend/models.py:873-880` - ReadingResponse ML fields

**Frontend Types:**
- `frontend/src/lib/api.ts:15-18` - Reading interface with ML fields

### External References

**ML Algorithms:**
- Kalman Filtering for sensor fusion
- Anomaly detection based on fermentation physics
- Exponential curve fitting for FG prediction

**Best Practices:**
- FastAPI background tasks for async initialization
- WebSocket broadcasting patterns
- Graceful degradation for ML failures

### Related Work

**GitHub Issues:**
- Issue #62 - This issue
- PR #61 - ML Pipeline Implementation (merged)
- Issue #63 - Add heating/cooling to chart (complements this work)

**Validation:**
- 48/48 ML pipeline tests passing
- `backend/tests/ml/` - Comprehensive test suite

## Notes

**Critical Path:**
Phase 1 (broadcasting) → Phase 2 (predictions) → Phase 3 (visualization)

**Can Be Implemented Incrementally:**
Each phase delivers user value independently. Phase 1 can ship without Phase 2.

**Database Migrations:**
No migrations needed - ML columns already exist in schema.

**Deployment:**
Follow standard deployment workflow:
1. Build frontend locally: `cd frontend && npm run build`
2. Commit and push to GitHub
3. Deploy to RPi: `ssh pi@192.168.4.218 "cd /opt/brewsignal && git pull && sudo systemctl restart brewsignal"`
4. Verify via logs: `sudo journalctl -u brewsignal -f`

**Testing Strategy:**
- Unit tests: ML pipeline (already done)
- Integration tests: API endpoints return valid predictions
- Manual tests: WebSocket broadcasts, UI updates, chart rendering
- Regression tests: Ensure reading ingestion performance unchanged
