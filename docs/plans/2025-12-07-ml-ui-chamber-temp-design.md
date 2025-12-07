# ML UI Integration, Chamber Temperature & Control Visualization Design

**Date:** 2025-12-07
**Issues:** #67, #62, #63
**Status:** Design Approved

## Overview

This design covers three related features that enhance fermentation monitoring visibility:

1. **Chamber Temperature Tracking (#67)** - Add third temperature source for fermentation chamber environment
2. **ML Pipeline UI Integration (#62)** - Make ML predictions and filtered values visible to users
3. **Heating/Cooling Visualization (#63)** - Display control activity as chart overlays

**Implementation Priority:**
1. #67 first (extends proven pattern, sets foundation)
2. #62 second (exposes existing ML data)
3. #63 third (builds on chamber temp context)

## Feature #67: Chamber Temperature Tracking

### Problem Statement

Currently, the system displays:
- Wort temperature (from Tilt/iSpindel/GravityMon)
- Ambient temperature (room environment outside chamber)

Missing: Temperature and humidity **inside the fermentation chamber**, which is essential for:
- Monitoring chamber performance
- Understanding heating/cooling effectiveness
- Diagnosing environmental control issues

### Architecture (Mirror Pattern)

Follow the proven `ambient_poller.py` pattern exactly to minimize risk and maintain consistency.

#### Database Layer

**New Table: `chamber_readings`**
```python
class ChamberReading(Base):
    __tablename__ = "chamber_readings"
    __table_args__ = (Index("ix_chamber_timestamp", "timestamp"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc), index=True)
    temperature: Mapped[Optional[float]] = mapped_column()  # Celsius
    humidity: Mapped[Optional[float]] = mapped_column()
    entity_id: Mapped[Optional[str]] = mapped_column(String(100))
```

**Migration:**
- Add to `backend/database.py` migrations
- Table created on app startup if missing
- No data migration needed (new feature)

**Pydantic Schema:**
```python
class ChamberReadingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    timestamp: datetime
    temperature: Optional[float]
    humidity: Optional[float]

    @field_serializer('timestamp')
    def serialize_dt(self, dt: datetime) -> str:
        return serialize_datetime_to_utc(dt)
```

#### Configuration Layer

**Add to `routers/config.py` DEFAULT_CONFIG:**
```python
"ha_chamber_temp_entity_id": "",
"ha_chamber_humidity_entity_id": "",
```

**Update Pydantic models:**
- `ConfigUpdate`: Add optional fields
- `ConfigResponse`: Add fields with defaults

#### Backend Service

**New File: `backend/chamber_poller.py`**

Clone `ambient_poller.py` with these changes:
- Poll interval: 30 seconds (same as ambient)
- Config keys: `ha_chamber_temp_entity_id`, `ha_chamber_humidity_entity_id`
- Table: `ChamberReading`
- WebSocket message type: `"chamber"`

**WebSocket Broadcast Format:**
```json
{
  "type": "chamber",
  "temperature": 18.5,
  "humidity": 65.0,
  "timestamp": "2025-12-07T10:30:00.000Z"
}
```

**Lifecycle Integration (`main.py`):**
```python
from .chamber_poller import start_chamber_poller, stop_chamber_poller

@app.on_event("startup")
async def startup():
    # ... existing startup code
    start_chamber_poller()

@app.on_event("shutdown")
async def shutdown():
    # ... existing shutdown code
    stop_chamber_poller()
```

#### API Layer

**New File: `backend/routers/chamber.py`**

```python
router = APIRouter(prefix="/api/chamber", tags=["chamber"])

@router.get("/current")
async def get_current_chamber():
    """Get current chamber temp/humidity from HA."""
    # Mirror ambient.py implementation
    # Return: {temperature, humidity, timestamp}

@router.get("/history", response_model=list[ChamberReadingResponse])
async def get_chamber_history(
    hours: int = Query(default=24, ge=1, le=720),
    db: AsyncSession = Depends(get_db)
):
    """Get historical chamber readings."""
    # Query ChamberReading table
    # Order by timestamp DESC
    # Limit 2000 records
```

**Register in `main.py`:**
```python
from .routers import chamber
app.include_router(chamber.router)
```

#### Frontend Integration

**System Settings Page (`frontend/src/routes/system/+page.svelte`):**

Add chamber sensor configuration section mirroring ambient UI:
- Entity ID input for chamber temperature
- Entity ID input for chamber humidity
- Test buttons to verify entities exist
- Save to config via PATCH `/api/config`

**Chart Integration (`FermentationChart.svelte`):**

Add chamber temperature as **fourth temperature series**:

**Series Definition:**
```javascript
{
  label: 'Chamber',
  scale: 'temp',
  stroke: '#a78bfa',  // purple (from tiltColorMap.PURPLE)
  width: 1.5,
  dash: [4, 2],  // Distinct from ambient [2, 4]
  value: (u, v) => v !== null ? v.toFixed(1) + '°' : '--',
  points: { show: false },
  paths: uPlot.paths.spline?.()
}
```

**Data Loading:**
```javascript
// Fetch chamber history alongside ambient
const chamberResp = await fetch(`/api/chamber/history?hours=${hours}`);
const chamberData = await chamberResp.json();

// Merge with chart data aligned by timestamp
// Handle missing data points (null values)
```

**WebSocket Handler:**
```javascript
if (msg.type === 'chamber') {
  // Update live chamber data
  // Append to chart if visible
}
```

**Visual Result:**

Chart will display three temperature lines:
1. **Wort** (tilt color, dashed `[4,4]`) - fermentation temp
2. **Ambient** (cyan `#22d3ee`, dashed `[2,4]`) - room temp
3. **Chamber** (purple `#a78bfa`, dashed `[4,2]`) - chamber temp

Plus gravity series and optional trend/filtered overlays.

---

## Feature #62: ML Pipeline UI Integration

### Problem Statement

PR #66 integrated the ML pipeline with live readings, but outputs are invisible to users:
- Kalman-filtered values exist but aren't displayed
- Predictions (FG, completion time) not shown
- Anomaly detection data hidden
- Confidence metrics unavailable

Users have no visibility into ML processing or benefits.

### Architecture

**Backend:** ML data already exists in `Reading` table and `MLPipelineManager` state from PR #66.

**Frontend:** Expose ML data through chart overlays, prediction panels, and anomaly indicators.

#### Backend Changes

**1. Verify ReadingResponse Schema**

Ensure `backend/models.py` includes ML fields:
```python
class ReadingResponse(BaseModel):
    # ... existing fields

    # ML outputs (optional, null if ML not run)
    sg_filtered: Optional[float]
    temp_filtered: Optional[float]
    confidence: Optional[float]
    sg_rate: Optional[float]
    temp_rate: Optional[float]
    is_anomaly: Optional[bool]
    anomaly_score: Optional[float]
    anomaly_reasons: Optional[list[str]]
```

**2. Batch Predictions Endpoint**

New endpoint to query ML state for predictions:

```python
# backend/routers/batches.py

@router.get("/{batch_id}/predictions")
async def get_batch_predictions(batch_id: int, db: AsyncSession = Depends(get_db)):
    """Get ML predictions for a batch."""
    batch = await get_batch_by_id(db, batch_id)
    if not batch or not batch.device_id:
        return {"error": "No device linked"}

    # Query MLPipelineManager for device state
    ml_manager = get_ml_manager()  # Access singleton
    predictions = ml_manager.get_predictions(batch.device_id)

    if not predictions:
        return {"available": False}

    return {
        "available": True,
        "predicted_fg": predictions.get("fg"),
        "estimated_completion": predictions.get("completion_date"),
        "confidence": predictions.get("confidence"),
        "data_quality": predictions.get("quality_score"),
        "num_readings": predictions.get("sample_count")
    }
```

**3. WebSocket ML Updates**

Extend reading broadcasts to include ML fields:
```python
# backend/main.py handle_tilt_reading()

await ws_manager.broadcast_json({
    "type": "reading",
    "device_id": device_id,
    "sg": calibrated_sg,
    "temp": calibrated_temp,
    "sg_filtered": ml_result.sg_filtered,  # NEW
    "temp_filtered": ml_result.temp_filtered,  # NEW
    "confidence": ml_result.confidence,  # NEW
    "is_anomaly": ml_result.is_anomaly,  # NEW
    "timestamp": serialize_datetime_to_utc(datetime.now(timezone.utc))
})
```

#### Frontend Chart Integration

**Filtered Series (Toggleable)**

Add filtered SG and temp series to `FermentationChart.svelte`:

```javascript
// Storage keys
const SHOW_FILTERED_SG = 'brewsignal_chart_show_filtered_sg';
const SHOW_FILTERED_TEMP = 'brewsignal_chart_show_filtered_temp';

let showFilteredSg = $state(false);
let showFilteredTemp = $state(false);

// Load from localStorage on mount
onMount(() => {
  showFilteredSg = localStorage.getItem(SHOW_FILTERED_SG) === 'true';
  showFilteredTemp = localStorage.getItem(SHOW_FILTERED_TEMP) === 'true';
});

// Add series after existing series
{
  label: 'Filtered SG',
  show: showFilteredSg,
  scale: 'sg',
  stroke: SG_COLOR,
  width: 1.5,
  dash: [4, 2],  // Dashed variant
  value: (u, v) => v !== null ? formatGravity(v) : '--',
  points: { show: false }
}

{
  label: 'Filtered Temp',
  show: showFilteredTemp,
  scale: 'temp',
  stroke: tempColor,
  width: 1,
  dash: [4, 2],
  value: (u, v) => v !== null ? v.toFixed(1) + '°' : '--',
  points: { show: false }
}
```

**Anomaly Markers**

Draw red triangles on SG series where `is_anomaly=true`:

```javascript
hooks: {
  draw: [
    (u) => {
      const ctx = u.ctx;
      for (let i = 0; i < timestamps.length; i++) {
        if (readings[i]?.is_anomaly) {
          const x = u.valToPos(timestamps[i], 'x', true);
          const y = u.valToPos(readings[i].sg, 'sg', true);

          // Draw red triangle marker
          ctx.fillStyle = '#ef4444';
          ctx.beginPath();
          ctx.moveTo(x, y - 6);
          ctx.lineTo(x - 4, y + 2);
          ctx.lineTo(x + 4, y + 2);
          ctx.fill();
        }
      }
    }
  ]
}
```

**Legend Toggles**

Add checkboxes to toggle filtered series:
```svelte
<label>
  <input type="checkbox" bind:checked={showFilteredSg} onchange={handleFilteredToggle}>
  Show Filtered SG
</label>
<label>
  <input type="checkbox" bind:checked={showFilteredTemp} onchange={handleFilteredToggle}>
  Show Filtered Temp
</label>
```

#### ML Predictions Panel

**New Component: `frontend/src/lib/components/MLPredictions.svelte`**

Display ML predictions on batch detail page:

```svelte
<script lang="ts">
  interface Props {
    batchId: number;
  }

  let { batchId }: Props = $props();
  let predictions = $state(null);
  let loading = $state(true);

  onMount(async () => {
    const resp = await fetch(`/api/batches/${batchId}/predictions`);
    predictions = await resp.json();
    loading = false;
  });
</script>

{#if predictions?.available}
  <div class="ml-panel">
    <h3>ML Predictions</h3>

    <div class="metric">
      <span class="label">Predicted FG:</span>
      <span class="value">{formatGravity(predictions.predicted_fg)}</span>
    </div>

    <div class="metric">
      <span class="label">Est. Completion:</span>
      <span class="value">
        {formatDate(predictions.estimated_completion)}
        ({predictions.days_remaining} days)
      </span>
    </div>

    <div class="metric">
      <span class="label">Confidence:</span>
      <div class="progress-bar">
        <div class="fill" style="width: {predictions.confidence * 100}%"></div>
      </div>
      <span class="percentage">{(predictions.confidence * 100).toFixed(0)}%</span>
    </div>

    <div class="metric">
      <span class="label">Data Quality:</span>
      <div class="progress-bar">
        <div class="fill" style="width: {predictions.data_quality * 100}%"></div>
      </div>
      <span class="percentage">{(predictions.data_quality * 100).toFixed(0)}%</span>
    </div>

    <div class="metric">
      <span class="label">Readings:</span>
      <span class="value">{predictions.num_readings} points</span>
    </div>
  </div>
{:else if !loading}
  <div class="ml-panel disabled">
    <p>ML predictions unavailable (insufficient data)</p>
  </div>
{/if}
```

Include on batch detail page (`batches/[id]/+page.svelte`):
```svelte
<MLPredictions batchId={batch.id} />
```

#### Anomaly Alerts

**Dashboard Badge (`FermentationCard.svelte`):**

Show warning icon if latest reading has anomaly:

```svelte
{#if latestReading?.is_anomaly}
  <div class="anomaly-badge" title="Anomaly: {latestReading.anomaly_reasons.join(', ')}">
    <svg><!-- warning icon --></svg>
  </div>
{/if}
```

**Batch Detail Panel:**

Show recent anomalies with timestamps:

```svelte
<div class="anomalies-panel">
  <h3>Recent Anomalies</h3>
  {#each recentAnomalies as reading}
    <div class="anomaly-item">
      <span class="timestamp">{formatDate(reading.timestamp)}</span>
      <ul class="reasons">
        {#each reading.anomaly_reasons as reason}
          <li>{reason}</li>
        {/each}
      </ul>
    </div>
  {/each}
</div>
```

---

## Feature #63: Heating/Cooling Activity Visualization

### Problem Statement

Temperature control is active but only shows real-time status. No historical view of:
- When heating/cooling was active
- How chamber responded to control actions
- Control cycle frequency and patterns

Difficult to diagnose control issues or optimize hysteresis settings.

### Architecture

Display heating and cooling periods as semi-transparent background bands on the fermentation chart.

#### Backend Changes

**1. Control Events API Endpoint**

```python
# backend/routers/batches.py

@router.get("/{batch_id}/control-events", response_model=list[ControlEventResponse])
async def get_control_events(
    batch_id: int,
    hours: int = Query(default=24, ge=1, le=720),
    db: AsyncSession = Depends(get_db)
):
    """Get heating/cooling control events for a batch."""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    result = await db.execute(
        select(ControlEvent)
        .where(
            ControlEvent.batch_id == batch_id,
            ControlEvent.timestamp >= since
        )
        .order_by(ControlEvent.timestamp)
    )

    return result.scalars().all()
```

**2. Verify ControlEvent Creation**

Ensure `backend/temp_controller.py` creates events on state changes:

```python
# When switching heater ON
control_event = ControlEvent(
    batch_id=batch.id,
    device_id=batch.device_id,
    action="heat_on",
    wort_temp=current_temp,
    ambient_temp=ambient_temp,
    target_temp=batch.temp_target
)
db.add(control_event)

# Similar for heat_off, cool_on, cool_off
```

Events should be created **only on transitions** (not every control loop iteration).

#### Frontend Chart Integration

**Data Loading (`FermentationChart.svelte`):**

```javascript
let controlEvents = $state<ControlEvent[]>([]);

async function loadData() {
  // ... existing data loading

  // Load control events
  const eventsResp = await fetch(`/api/batches/${batchId}/control-events?hours=${selectedRange}`);
  controlEvents = await eventsResp.json();
}

// Parse events into periods
interface ControlPeriod {
  start: number;  // Unix timestamp
  end: number;
  type: 'heating' | 'cooling';
}

function parseControlPeriods(events: ControlEvent[]): ControlPeriod[] {
  const periods: ControlPeriod[] = [];
  let heatingStart: number | null = null;
  let coolingStart: number | null = null;

  for (const event of events) {
    const timestamp = new Date(event.timestamp).getTime() / 1000;

    if (event.action === 'heat_on') {
      heatingStart = timestamp;
    } else if (event.action === 'heat_off' && heatingStart !== null) {
      periods.push({ start: heatingStart, end: timestamp, type: 'heating' });
      heatingStart = null;
    } else if (event.action === 'cool_on') {
      coolingStart = timestamp;
    } else if (event.action === 'cool_off' && coolingStart !== null) {
      periods.push({ start: coolingStart, end: timestamp, type: 'cooling' });
      coolingStart = null;
    }
  }

  // Handle ongoing periods (no corresponding off event)
  const now = Date.now() / 1000;
  if (heatingStart !== null) {
    periods.push({ start: heatingStart, end: now, type: 'heating' });
  }
  if (coolingStart !== null) {
    periods.push({ start: coolingStart, end: now, type: 'cooling' });
  }

  return periods;
}
```

**Background Band Rendering:**

Use uPlot `hooks.drawClear` to draw bands before series:

```javascript
// Toggle state
const SHOW_HEATING = 'brewsignal_chart_show_heating';
const SHOW_COOLING = 'brewsignal_chart_show_cooling';
let showHeating = $state(true);
let showCooling = $state(true);

// Chart options
hooks: {
  drawClear: [
    (u) => {
      const ctx = u.ctx;
      const periods = parseControlPeriods(controlEvents);

      for (const period of periods) {
        if (period.type === 'heating' && !showHeating) continue;
        if (period.type === 'cooling' && !showCooling) continue;

        const x0 = u.valToPos(period.start, 'x', true);
        const x1 = u.valToPos(period.end, 'x', true);

        // Draw background band
        ctx.fillStyle = period.type === 'heating'
          ? 'rgba(239, 68, 68, 0.1)'   // Subtle red
          : 'rgba(59, 130, 246, 0.1)';  // Subtle blue

        ctx.fillRect(
          x0,
          u.bbox.top,
          x1 - x0,
          u.bbox.height
        );
      }
    }
  ]
}
```

**Legend Toggles:**

Add checkboxes to control band visibility:

```svelte
<label>
  <input type="checkbox" bind:checked={showHeating} onchange={handleControlToggle}>
  <span style="color: #ef4444;">■</span> Heating
</label>
<label>
  <input type="checkbox" bind:checked={showCooling} onchange={handleControlToggle}>
  <span style="color: #3b82f6;">■</span> Cooling
</label>
```

**Visual Result:**

- Red bands show when heater was active
- Blue bands show when cooler was active
- Bands span full chart height behind data series
- Easy to correlate control activity with temp changes
- Toggle visibility to reduce clutter when not needed

---

## Implementation Sequence

### Phase 1: Chamber Temperature (#67)
**Estimated Effort:** 2-3 hours

1. Database migration (ChamberReading table)
2. Config updates (entity ID fields)
3. Backend service (chamber_poller.py)
4. API endpoints (chamber.py router)
5. Frontend config UI (System Settings)
6. Chart integration (purple dashed line)
7. Testing (verify polling, WebSocket, chart display)

### Phase 2: ML Integration (#62)
**Estimated Effort:** 4-5 hours

1. Verify ReadingResponse ML fields
2. Batch predictions endpoint
3. WebSocket ML field broadcast
4. Chart filtered series (toggleable)
5. Anomaly markers on chart
6. MLPredictions component
7. Dashboard anomaly badges
8. Batch detail anomaly panel
9. Testing (verify predictions, anomalies, filtering)

### Phase 3: Control Visualization (#63)
**Estimated Effort:** 3-4 hours

1. Control events API endpoint
2. Verify ControlEvent creation in temp_controller
3. Chart band rendering (uPlot hooks)
4. Period parsing logic
5. Legend toggles (heating/cooling)
6. Testing (verify bands align with events)

**Total Estimated Effort:** 9-12 hours

---

## Success Criteria

### Chamber Temperature (#67)
- ✅ Three temperature sources visible on chart (wort/ambient/chamber)
- ✅ Chamber sensor configurable via System Settings
- ✅ Real-time WebSocket updates for chamber readings
- ✅ Historical chamber data persisted and queryable

### ML Integration (#62)
- ✅ Filtered SG/temp series toggleable on chart
- ✅ Predictions panel shows FG estimate and completion date
- ✅ Anomaly markers visible on chart with reasons
- ✅ Dashboard shows anomaly badges
- ✅ Confidence metrics displayed

### Control Visualization (#63)
- ✅ Heating/cooling periods shown as background bands
- ✅ Bands toggleable independently
- ✅ Visual correlation between control and temperature
- ✅ Control events persisted with batch context

---

## Risk Assessment

**Low Risk:**
- Chamber temp (#67) mirrors proven ambient pattern
- ML data already exists, just exposing in UI
- Control events table already exists

**Medium Risk:**
- Chart performance with many series/bands (mitigate with toggles)
- ML state availability after restart (graceful degradation)

**Mitigation:**
- Use feature toggles for all new UI elements
- Graceful fallbacks when data unavailable
- Test with long fermentation datasets (2+ weeks)

---

## Future Enhancements

**Not in Scope (Post-MVP):**
- ML model retraining based on user feedback
- Predictive control (MPC temperature trajectories)
- Chamber temp alerts (threshold-based notifications)
- Historical control efficiency metrics
- Multi-batch control event correlation

These can be addressed in future iterations once core features are validated.
