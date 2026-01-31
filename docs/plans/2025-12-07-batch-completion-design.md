# Batch Completion Feature Design

**Date:** 2025-12-07
**Issue:** #75 - Implement a 'complete batch' feature
**Status:** Approved

## Overview

Add ability to complete batches and stop logging hydrometer readings. Batch status will control when readings are stored to the database, allowing users to see live readings during planning (to validate OG) without polluting the database, then log during fermentation and conditioning, and finally stop logging when complete.

## User Workflow

### 1. Planning Phase
- Create batch, assign device, status remains "Planning"
- Hydrometer readings visible on dashboard (live WebSocket)
- User can see current SG to validate OG measurement
- **Readings NOT stored in database**

### 2. Start Fermentation
- User changes status: Planning → Fermenting (via dropdown)
- System immediately starts logging readings to database
- Readings auto-link to batch
- Temperature control starts (if configured)

### 3. Conditioning Phase
- User changes status: Fermenting → Conditioning (via dropdown)
- System continues logging readings (need wort temp for cold crash monitoring)
- **UI shows reminder:** "Adjust target temperature for cold crash if needed"
- Temperature control continues (if configured)

### 4. Complete Batch
- User changes status: Conditioning → Completed (via dropdown)
- System immediately stops logging readings to database
- Live readings still visible on dashboard (WebSocket)
- Temperature control stops

## Technical Design

### Backend Changes

#### 1. Reading Storage Logic (`backend/main.py`)

**Current behavior:**
```python
if device.paired:
    batch_id = await link_reading_to_batch(session, reading.id)
    # Store reading in database
```

**New behavior:**
```python
# Always try to link to active batch
batch_id = await link_reading_to_batch(session, reading.id)

# Only store readings if linked to active batch (fermenting or conditioning)
if batch_id is not None:
    # Calculate time since batch start for ML pipeline
    # Process through ML pipeline
    # Store reading in database
```

**Key change:** Move batch linking BEFORE the conditional, use `batch_id is not None` as gate for storage.

#### 2. Batch Linking Logic (`backend/services/batch_linker.py`)

**Current behavior:**
```python
query = (
    select(Batch)
    .where(Batch.device_id == device_id)
    .where(Batch.status == "fermenting")  # Only fermenting
    .order_by(Batch.start_time.desc())
    .limit(1)
)
```

**New behavior:**
```python
query = (
    select(Batch)
    .where(Batch.device_id == device_id)
    .where(Batch.status.in_(["fermenting", "conditioning"]))  # Both active phases
    .order_by(Batch.start_time.desc())
    .limit(1)
)
```

**Impact:** Readings will link to batches in both "fermenting" and "conditioning" status.

### Frontend Changes

#### 1. Status Change Handler (`frontend/src/routes/batches/[id]/+page.svelte`)

Add conditioning reminder when transitioning to conditioning status:

```typescript
async function handleStatusChange(newStatus: BatchStatus) {
    if (!batch || statusUpdating) return;

    // Show reminder when entering conditioning
    if (newStatus === 'conditioning' && batch.status === 'fermenting') {
        const proceed = confirm(
            '💡 Entering Conditioning Phase\n\n' +
            'Reminder: Adjust target temperature if cold crashing.\n\n' +
            'Continue?'
        );
        if (!proceed) return;
    }

    statusUpdating = true;
    try {
        batch = await updateBatch(batch.id, { status: newStatus });
        // ... existing reload logic ...
    } catch (e) {
        console.error('Failed to update status:', e);
    } finally {
        statusUpdating = false;
    }
}
```

**Alternative (better UX):** Toast notification instead of blocking confirm dialog:
```typescript
if (newStatus === 'conditioning' && batch.status === 'fermenting') {
    // Show non-blocking toast notification
    showToast('💡 Don\'t forget to adjust target temp for cold crash if needed', 'info');
}
```

#### 2. No Other UI Changes Needed

- Status dropdown already includes all statuses (Planning, Fermenting, Conditioning, Completed)
- `handleStatusChange()` already calls update API
- All UI components already handle status changes

## Data Flow

### Planning Status
```
Tilt Reading → WebSocket Broadcast → Dashboard Display
                     ↓
              batch_linker.py
                     ↓
              Returns None (status != fermenting/conditioning)
                     ↓
              Skip database storage
```

### Fermenting/Conditioning Status
```
Tilt Reading → WebSocket Broadcast → Dashboard Display
                     ↓
              batch_linker.py
                     ↓
              Returns batch_id (status = fermenting OR conditioning)
                     ↓
              ML Pipeline → Database Storage (with batch link)
```

### Completed Status
```
Tilt Reading → WebSocket Broadcast → Dashboard Display
                     ↓
              batch_linker.py
                     ↓
              Returns None (status = completed)
                     ↓
              Skip database storage
```

## Edge Cases

### Device Pairing
- **Pairing controls visibility:** Unpaired devices don't broadcast to WebSocket
- **Batch status controls storage:** Visible devices only store readings if linked to active batch
- **Behavior:** Device must be BOTH paired AND linked to fermenting/conditioning batch to log

### Mid-Fermentation Device Change
- Old device: Stops getting readings linked (no active batch for that device)
- New device: Starts getting readings linked (has active batch)
- No special handling needed (existing behavior)

### Multiple Batches Per Device
- `batch_linker.py` uses `ORDER BY start_time DESC LIMIT 1` to find latest active batch
- Only one batch can be fermenting/conditioning per device at a time (enforced by UI)
- No conflicts expected

### Temperature Control
- Already stops when batch leaves "fermenting" status (existing logic in `temp_controller.py`)
- Will continue during "conditioning" status (existing logic checks `status == "fermenting"`)
- **Needs update:** Temperature controller should also run for "conditioning" status

## Migration & Rollout

### Database Migration
**None needed.** All required columns already exist.

### Backward Compatibility
- Existing batches with `status = "completed"` will immediately stop logging (desired behavior)
- Existing batches with `status = "fermenting"` continue logging (no change)
- Existing batches with `status = "conditioning"` will START logging (new feature)

### Deployment Steps
1. Deploy backend changes (main.py, batch_linker.py)
2. Deploy frontend changes (status change handler)
3. No database downtime required
4. Immediate effect on all batches

## Testing Plan

### Manual Testing
1. **Planning → Live but not logged**
   - Create batch, keep status = Planning
   - Verify readings appear on dashboard
   - Verify no new readings in database for device

2. **Fermenting → Logged**
   - Change status to Fermenting
   - Verify readings stored in database with batch_id link

3. **Conditioning → Still logged**
   - Change status to Conditioning
   - Verify readings still stored in database
   - Verify reminder shown in UI

4. **Completed → Not logged**
   - Change status to Completed
   - Verify readings stop storing in database
   - Verify readings still visible on dashboard (WebSocket)

### Automated Tests

**Add to `backend/tests/test_batches_api.py`:**
- `test_readings_not_stored_planning_status()` - Verify no storage when planning
- `test_readings_stored_fermenting_status()` - Verify storage when fermenting
- `test_readings_stored_conditioning_status()` - Verify storage when conditioning
- `test_readings_not_stored_completed_status()` - Verify no storage when completed

**Update existing tests:**
- `backend/tests/test_batch_linker.py` - Update to include conditioning in active batch tests

## Success Criteria

✅ Readings visible on dashboard during Planning (for OG validation)
✅ Readings stored during Fermenting
✅ Readings stored during Conditioning
✅ Readings NOT stored during Completed
✅ Temperature control continues during Conditioning
✅ UI reminder shown when entering Conditioning
✅ No database migrations required
✅ Existing batches behave correctly after deployment

## Future Enhancements (Out of Scope)

- Batch completion checklist (measure FG, package date, etc.)
- Auto-suggest FG measurement when status changes to Completed
- Analytics: average fermentation duration by recipe/style
- Email/notification when batch ready to complete (based on gravity stability)
