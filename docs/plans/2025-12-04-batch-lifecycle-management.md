# Batch Lifecycle Management Design

**Date:** 2025-12-04
**Status:** Approved for Implementation
**Issue:** #41

## Overview

Implement comprehensive batch lifecycle management to handle batches from creation through completion and cleanup. This design consolidates historical viewing, data maintenance, and orphaned data detection into a unified system.

## Problem Statement

Current limitations:
1. **No historical view** - Completed batches are hidden from main UI with no dedicated archive view
2. **No soft delete** - Hard delete is all-or-nothing with cascade, no way to hide batches without losing data
3. **Orphaned data risks** - Readings can exist without batch linkage, no cleanup tools
4. **Status management gaps** - Some transitions are manual, no validation rules
5. **Data maintenance** - No UI for bulk cleanup, date range deletion, or integrity checks

## Design Principles

1. **Incremental enhancement** - Build on existing status-based lifecycle
2. **Soft delete by default** - Preserve data unless explicitly requested
3. **Preview-first operations** - All destructive operations show preview before execution
4. **Minimal schema changes** - Single column addition to maintain migration simplicity
5. **Preserve API contracts** - Existing frontend code continues to work

## Architecture Overview

### Status Model Simplification

**Before:**
- Statuses: `planning`, `fermenting`, `conditioning`, `completed`, `archived`
- Hard delete only
- Confusion between `archived` and deleted states

**After:**
- Statuses: `planning`, `fermenting`, `conditioning`, `completed`
- Soft delete via `deleted_at` timestamp
- `archived` status removed (migrated to `completed`)

**Lifecycle Flow:**
```
planning → fermenting → conditioning → completed
                ↓           ↓            ↓
            (soft delete at any stage)
```

## Database Schema Changes

### Batch Model

```python
class Batch(Base):
    # ... existing fields ...

    # Status values: 'planning', 'fermenting', 'conditioning', 'completed'
    status: Mapped[str] = mapped_column(String(20), default="planning")

    # NEW: Soft delete timestamp
    deleted_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    # Helper property for queries
    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None
```

### Migration

```python
# In backend/database.py
async def _migrate_add_deleted_at():
    """Add deleted_at column and migrate 'archived' status to 'completed'."""

    # Check if column exists
    cursor = await db.execute("PRAGMA table_info(batches)")
    columns = {row[1] for row in cursor.fetchall()}

    if 'deleted_at' not in columns:
        # 1. Add deleted_at column
        await db.execute("ALTER TABLE batches ADD COLUMN deleted_at TIMESTAMP")

        # 2. Migrate any 'archived' status to 'completed'
        await db.execute(
            "UPDATE batches SET status = 'completed' WHERE status = 'archived'"
        )

        await db.commit()
```

**Call from `init_db()`:**
```python
async def init_db():
    # ... existing migrations ...
    await _migrate_add_deleted_at()
    # ... rest of init ...
```

## API Design

### Updated Batch Endpoints

#### List Batches (Enhanced)

```python
@router.get("", response_model=list[BatchResponse])
async def list_batches(
    status: Optional[str] = Query(None, description="Filter by status"),
    device_id: Optional[str] = Query(None, description="Filter by device"),
    include_deleted: bool = Query(False, description="Include soft-deleted batches"),
    deleted_only: bool = Query(False, description="Show only deleted batches (for maintenance)"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List batches with filters. By default excludes deleted batches."""
    query = (
        select(Batch)
        .options(selectinload(Batch.recipe).selectinload(Recipe.style))
        .order_by(Batch.created_at.desc())
    )

    # Soft delete filter (default: hide deleted)
    if deleted_only:
        query = query.where(Batch.deleted_at.is_not(None))
    elif not include_deleted:
        query = query.where(Batch.deleted_at.is_(None))

    # Status filter
    if status:
        query = query.where(Batch.status == status)

    # Device filter
    if device_id:
        query = query.where(Batch.device_id == device_id)

    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()
```

#### Convenience Endpoints

```python
@router.get("/active", response_model=list[BatchResponse])
async def list_active_batches(db: AsyncSession = Depends(get_db)):
    """Active batches: planning or fermenting status, not deleted."""
    query = (
        select(Batch)
        .options(selectinload(Batch.recipe).selectinload(Recipe.style))
        .where(
            Batch.deleted_at.is_(None),
            Batch.status.in_(["planning", "fermenting"])
        )
        .order_by(Batch.created_at.desc())
    )
    result = await db.execute(query)
    return result.scalars().all()

@router.get("/completed", response_model=list[BatchResponse])
async def list_completed_batches(db: AsyncSession = Depends(get_db)):
    """Historical batches: completed or conditioning, not deleted."""
    query = (
        select(Batch)
        .options(selectinload(Batch.recipe).selectinload(Recipe.style))
        .where(
            Batch.deleted_at.is_(None),
            Batch.status.in_(["completed", "conditioning"])
        )
        .order_by(Batch.updated_at.desc())
    )
    result = await db.execute(query)
    return result.scalars().all()
```

#### Soft Delete & Restore

```python
@router.post("/{batch_id}/delete")
async def soft_delete_batch(
    batch_id: int,
    hard_delete: bool = Query(False, description="Cascade delete readings"),
    db: AsyncSession = Depends(get_db),
):
    """Soft delete or hard delete a batch.

    - Soft delete (default): Sets deleted_at timestamp, preserves all data
    - Hard delete: Cascade removes all readings via relationship
    """
    batch = await db.get(Batch, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    if hard_delete:
        # Hard delete: cascade removes readings via relationship
        await db.delete(batch)
        await db.commit()
        return {"status": "deleted", "type": "hard", "batch_id": batch_id}
    else:
        # Soft delete: set timestamp
        batch.deleted_at = datetime.now(timezone.utc)
        await db.commit()
        return {"status": "deleted", "type": "soft", "batch_id": batch_id}

@router.post("/{batch_id}/restore")
async def restore_batch(batch_id: int, db: AsyncSession = Depends(get_db)):
    """Restore a soft-deleted batch."""
    batch = await db.get(Batch, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    if not batch.deleted_at:
        raise HTTPException(status_code=400, detail="Batch is not deleted")

    batch.deleted_at = None
    await db.commit()
    return {"status": "restored", "batch_id": batch_id}
```

### New Maintenance Router

Create `backend/routers/maintenance.py`:

```python
"""Data maintenance and cleanup operations."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import delete, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Batch, Device, Reading, serialize_datetime_to_utc

router = APIRouter(prefix="/api/maintenance", tags=["maintenance"])


class OrphanedDataReport(BaseModel):
    """Report of orphaned readings and unused devices."""
    readings_without_batch: int
    readings_from_deleted_batches: int
    devices_without_active_batch: int
    unpaired_devices_with_readings: int


class CleanupPreview(BaseModel):
    """Preview of cleanup operation results."""
    readings_to_delete: int
    affected_batches: list[int]
    affected_devices: list[str]
    date_range: Optional[tuple[str, str]] = None


class CleanupRequest(BaseModel):
    """Request parameters for cleanup operation."""
    batch_id: Optional[int] = None
    device_id: Optional[str] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    include_deleted_batches: bool = False
    preview_only: bool = True  # Safety: default to preview


@router.get("/orphaned-data", response_model=OrphanedDataReport)
async def get_orphaned_data_report(db: AsyncSession = Depends(get_db)):
    """Identify orphaned readings and unused devices for data integrity check."""

    # Readings with no batch linkage
    no_batch = await db.execute(
        select(func.count(Reading.id)).where(Reading.batch_id.is_(None))
    )

    # Readings linked to deleted batches
    deleted_batch_query = (
        select(func.count(Reading.id))
        .join(Batch, Reading.batch_id == Batch.id)
        .where(Batch.deleted_at.is_not(None))
    )
    deleted_batch = await db.execute(deleted_batch_query)

    # Devices not assigned to any active batch
    unused_devices_query = (
        select(func.count(Device.id))
        .outerjoin(
            Batch,
            (Device.id == Batch.device_id) & (Batch.status == "fermenting")
        )
        .where(Batch.id.is_(None))
    )
    unused_devices = await db.execute(unused_devices_query)

    # Unpaired devices with readings (data pollution)
    unpaired_with_data_query = (
        select(func.count(distinct(Reading.device_id)))
        .join(Device, Reading.device_id == Device.id)
        .where(Device.paired == False, Reading.device_id.is_not(None))
    )
    unpaired_with_data = await db.execute(unpaired_with_data_query)

    return OrphanedDataReport(
        readings_without_batch=no_batch.scalar() or 0,
        readings_from_deleted_batches=deleted_batch.scalar() or 0,
        devices_without_active_batch=unused_devices.scalar() or 0,
        unpaired_devices_with_readings=unpaired_with_data.scalar() or 0,
    )


@router.post("/cleanup-readings", response_model=CleanupPreview)
async def cleanup_readings(
    request: CleanupRequest,
    db: AsyncSession = Depends(get_db),
):
    """Delete readings by batch, device, or date range. Preview by default.

    Safety features:
    - Defaults to preview_only=True (must explicitly set to False to execute)
    - Shows exact count, affected entities, and date range before deletion
    - Supports filtering by batch, device, date range, or combinations
    """

    # Build query for readings to delete
    query = select(Reading)

    # Apply filters
    if request.batch_id:
        query = query.where(Reading.batch_id == request.batch_id)
    if request.device_id:
        query = query.where(Reading.device_id == request.device_id)
    if request.date_from:
        query = query.where(Reading.timestamp >= request.date_from)
    if request.date_to:
        query = query.where(Reading.timestamp <= request.date_to)
    if request.include_deleted_batches:
        # Include readings from deleted batches
        query = query.outerjoin(Batch).where(
            (Batch.deleted_at.is_not(None)) | (Reading.batch_id.is_(None))
        )

    # Get preview data
    result = await db.execute(query)
    reading_list = result.scalars().all()

    # Calculate preview metadata
    affected_batches = sorted(list(set(r.batch_id for r in reading_list if r.batch_id)))
    affected_devices = sorted(list(set(r.device_id for r in reading_list if r.device_id)))

    date_range = None
    if reading_list:
        timestamps = [r.timestamp for r in reading_list]
        min_date = min(timestamps)
        max_date = max(timestamps)
        date_range = (
            serialize_datetime_to_utc(min_date),
            serialize_datetime_to_utc(max_date),
        )

    # Execute deletion if not preview
    if not request.preview_only:
        delete_query = delete(Reading)

        # Apply same filters as select query
        if request.batch_id:
            delete_query = delete_query.where(Reading.batch_id == request.batch_id)
        if request.device_id:
            delete_query = delete_query.where(Reading.device_id == request.device_id)
        if request.date_from:
            delete_query = delete_query.where(Reading.timestamp >= request.date_from)
        if request.date_to:
            delete_query = delete_query.where(Reading.timestamp <= request.date_to)

        await db.execute(delete_query)
        await db.commit()

    return CleanupPreview(
        readings_to_delete=len(reading_list),
        affected_batches=affected_batches,
        affected_devices=affected_devices,
        date_range=date_range,
    )
```

**Register in `backend/main.py`:**
```python
from .routers import maintenance

app.include_router(maintenance.router)
```

## Frontend Changes

### 1. Batch List Page - Tabbed Interface

**Location:** `frontend/src/routes/batches/+page.svelte`

```svelte
<script lang="ts">
  import { onMount } from 'svelte';
  import BatchCard from '$lib/components/BatchCard.svelte';
  import type { Batch } from '$lib/types';

  type TabType = 'active' | 'completed' | 'deleted';
  let activeTab: TabType = 'active';

  let activeBatches: Batch[] = [];
  let completedBatches: Batch[] = [];
  let deletedBatches: Batch[] = [];

  async function loadBatches() {
    if (activeTab === 'active') {
      const res = await fetch('/api/batches/active');
      activeBatches = await res.json();
    } else if (activeTab === 'completed') {
      const res = await fetch('/api/batches/completed');
      completedBatches = await res.json();
    } else {
      const res = await fetch('/api/batches?deleted_only=true');
      deletedBatches = await res.json();
    }
  }

  $: activeTab && loadBatches();

  $: currentBatches =
    activeTab === 'active' ? activeBatches :
    activeTab === 'completed' ? completedBatches :
    deletedBatches;
</script>

<div class="batches-page">
  <header>
    <h1>Batches</h1>
    <a href="/batches/new" class="btn-primary">New Batch</a>
  </header>

  <nav class="tabs">
    <button
      class:active={activeTab === 'active'}
      on:click={() => activeTab = 'active'}
    >
      Active ({activeBatches.length})
    </button>
    <button
      class:active={activeTab === 'completed'}
      on:click={() => activeTab = 'completed'}
    >
      History ({completedBatches.length})
    </button>
    <button
      class:active={activeTab === 'deleted'}
      on:click={() => activeTab = 'deleted'}
    >
      Deleted ({deletedBatches.length})
    </button>
  </nav>

  <div class="batch-list">
    {#each currentBatches as batch}
      <BatchCard
        {batch}
        readonly={activeTab === 'completed'}
        showRestoreButton={activeTab === 'deleted'}
        on:restore={loadBatches}
        on:delete={loadBatches}
      />
    {/each}

    {#if currentBatches.length === 0}
      <p class="empty-state">
        {activeTab === 'active' ? 'No active batches' :
         activeTab === 'completed' ? 'No completed batches yet' :
         'No deleted batches'}
      </p>
    {/if}
  </div>
</div>
```

### 2. Historical Batch Detail Page

**Location:** `frontend/src/routes/batches/[id]/history/+page.svelte`

Read-only view for completed batches with full chart data:

```svelte
<script lang="ts">
  import { page } from '$app/stores';
  import TiltChart from '$lib/components/TiltChart.svelte';
  import FermentationStats from '$lib/components/FermentationStats.svelte';
  import BatchTimelineCard from '$lib/components/BatchTimelineCard.svelte';
  import RecipeCard from '$lib/components/RecipeCard.svelte';

  const batchId = $page.params.id;

  let batch: Batch;
  let readings: Reading[] = [];

  async function loadBatch() {
    const res = await fetch(`/api/batches/${batchId}`);
    batch = await res.json();

    // Load full historical readings
    const readingsRes = await fetch(`/api/readings?batch_id=${batchId}&limit=10000`);
    readings = await readingsRes.json();
  }

  function exportCSV() {
    // Export readings as CSV
    const csv = readings.map(r =>
      `${r.timestamp},${r.sg_calibrated},${r.temp_calibrated}`
    ).join('\n');

    const blob = new Blob([`timestamp,sg,temp\n${csv}`], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `batch-${batchId}-data.csv`;
    a.click();
  }
</script>

<div class="batch-history">
  <header>
    <h1>{batch?.name || 'Batch History'}</h1>
    <div class="actions">
      <button on:click={exportCSV}>Export CSV</button>
      <a href="/batches/{batchId}">Back to Batch</a>
    </div>
  </header>

  <div class="banner info">
    📚 Historical view - Read-only
  </div>

  <div class="cards">
    {#if batch?.recipe}
      <RecipeCard recipe={batch.recipe} />
    {/if}

    <BatchTimelineCard {batch} />

    <div class="stats-card">
      <h3>Final Stats</h3>
      <dl>
        <dt>OG</dt><dd>{batch?.measured_og?.toFixed(3) || 'N/A'}</dd>
        <dt>FG</dt><dd>{batch?.measured_fg?.toFixed(3) || 'N/A'}</dd>
        <dt>ABV</dt><dd>{batch?.measured_abv?.toFixed(1) || 'N/A'}%</dd>
        <dt>Attenuation</dt><dd>{batch?.measured_attenuation?.toFixed(1) || 'N/A'}%</dd>
      </dl>
    </div>
  </div>

  <div class="chart-section">
    <h2>Fermentation Chart</h2>
    <TiltChart
      {readings}
      {batch}
      readonly={true}
      showControls={false}
    />
  </div>
</div>
```

### 3. Data Maintenance Page

**Location:** `frontend/src/routes/system/maintenance/+page.svelte`

```svelte
<script lang="ts">
  import { onMount } from 'svelte';

  let orphanedReport = {
    readings_without_batch: 0,
    readings_from_deleted_batches: 0,
    devices_without_active_batch: 0,
    unpaired_devices_with_readings: 0,
  };

  let cleanupRequest = {
    batch_id: null,
    device_id: null,
    date_from: null,
    date_to: null,
    include_deleted_batches: false,
    preview_only: true,
  };

  let cleanupPreview = null;
  let isExecuting = false;

  async function loadOrphanedReport() {
    const res = await fetch('/api/maintenance/orphaned-data');
    orphanedReport = await res.json();
  }

  async function previewCleanup() {
    const res = await fetch('/api/maintenance/cleanup-readings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...cleanupRequest, preview_only: true }),
    });
    cleanupPreview = await res.json();
  }

  async function executeCleanup() {
    if (!cleanupPreview) return;

    const confirmed = confirm(
      `Delete ${cleanupPreview.readings_to_delete} readings?\n\n` +
      `Affected batches: ${cleanupPreview.affected_batches.length}\n` +
      `Affected devices: ${cleanupPreview.affected_devices.length}\n\n` +
      `This action cannot be undone.`
    );

    if (!confirmed) return;

    isExecuting = true;
    try {
      await fetch('/api/maintenance/cleanup-readings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...cleanupRequest, preview_only: false }),
      });

      // Refresh reports
      await loadOrphanedReport();
      cleanupPreview = null;
      cleanupRequest = {
        batch_id: null,
        device_id: null,
        date_from: null,
        date_to: null,
        include_deleted_batches: false,
        preview_only: true,
      };
    } finally {
      isExecuting = false;
    }
  }

  onMount(loadOrphanedReport);
</script>

<div class="maintenance-page">
  <h1>Data Maintenance</h1>

  <!-- Orphaned Data Report -->
  <section class="card">
    <h2>Data Integrity Report</h2>
    <button on:click={loadOrphanedReport}>Refresh</button>

    <dl class="report">
      <dt>Readings without batch:</dt>
      <dd class:warn={orphanedReport.readings_without_batch > 0}>
        {orphanedReport.readings_without_batch}
      </dd>

      <dt>Readings from deleted batches:</dt>
      <dd class:warn={orphanedReport.readings_from_deleted_batches > 0}>
        {orphanedReport.readings_from_deleted_batches}
      </dd>

      <dt>Devices without active batch:</dt>
      <dd>{orphanedReport.devices_without_active_batch}</dd>

      <dt>Unpaired devices with data:</dt>
      <dd class:warn={orphanedReport.unpaired_devices_with_readings > 0}>
        {orphanedReport.unpaired_devices_with_readings}
      </dd>
    </dl>
  </section>

  <!-- Cleanup Tool -->
  <section class="card">
    <h2>Cleanup Readings</h2>

    <form on:submit|preventDefault={previewCleanup}>
      <div class="form-grid">
        <label>
          Batch ID
          <input
            type="number"
            bind:value={cleanupRequest.batch_id}
            placeholder="All batches"
          />
        </label>

        <label>
          Device ID
          <input
            type="text"
            bind:value={cleanupRequest.device_id}
            placeholder="All devices"
          />
        </label>

        <label>
          Date From
          <input type="date" bind:value={cleanupRequest.date_from} />
        </label>

        <label>
          Date To
          <input type="date" bind:value={cleanupRequest.date_to} />
        </label>
      </div>

      <label class="checkbox">
        <input
          type="checkbox"
          bind:checked={cleanupRequest.include_deleted_batches}
        />
        Include readings from deleted batches
      </label>

      <button type="submit" class="btn-secondary">Preview Cleanup</button>
    </form>

    {#if cleanupPreview}
      <div class="preview-box">
        <h3>Preview Results</h3>
        <dl>
          <dt>Readings to delete:</dt>
          <dd class="highlight">{cleanupPreview.readings_to_delete}</dd>

          <dt>Affected batches:</dt>
          <dd>{cleanupPreview.affected_batches.join(', ') || 'None'}</dd>

          <dt>Affected devices:</dt>
          <dd>{cleanupPreview.affected_devices.join(', ') || 'None'}</dd>

          {#if cleanupPreview.date_range}
            <dt>Date range:</dt>
            <dd>
              {new Date(cleanupPreview.date_range[0]).toLocaleDateString()}
              to
              {new Date(cleanupPreview.date_range[1]).toLocaleDateString()}
            </dd>
          {/if}
        </dl>

        <button
          on:click={executeCleanup}
          disabled={isExecuting || cleanupPreview.readings_to_delete === 0}
          class="btn-danger"
        >
          {isExecuting ? 'Executing...' : 'Execute Cleanup'}
        </button>
      </div>
    {/if}
  </section>
</div>

<style>
  .report dt {
    font-weight: 600;
  }

  .report dd.warn {
    color: var(--warning);
    font-weight: bold;
  }

  .preview-box {
    margin-top: 1rem;
    padding: 1rem;
    border: 2px solid var(--warning);
    border-radius: 8px;
    background: var(--surface-secondary);
  }

  .highlight {
    font-size: 1.5rem;
    font-weight: bold;
    color: var(--danger);
  }
</style>
```

## Implementation Phases

### Phase 1: Database & Backend (Core)

**Tasks:**
1. Add `deleted_at` column migration
2. Update Batch model and remove `archived` from status values
3. Update existing batch endpoints (add `include_deleted`, `deleted_only` params)
4. Add convenience endpoints (`/active`, `/completed`)
5. Add soft delete/restore endpoints
6. Test migration on dev database

**Files:**
- `backend/models.py` - Add `deleted_at` field
- `backend/database.py` - Add migration function
- `backend/routers/batches.py` - Update list endpoint, add soft delete/restore

### Phase 2: Maintenance API

**Tasks:**
1. Create `backend/routers/maintenance.py`
2. Implement orphaned data report endpoint
3. Implement cleanup preview/execute endpoint
4. Add Pydantic models for maintenance operations
5. Register maintenance router in main.py

**Files:**
- `backend/routers/maintenance.py` - New file
- `backend/main.py` - Register router

### Phase 3: Frontend - Batch List Tabs

**Tasks:**
1. Add tab navigation to batch list page
2. Connect tabs to API endpoints (`/active`, `/completed`, `?deleted_only=true`)
3. Update BatchCard component to support read-only mode
4. Add restore button for deleted batches
5. Update styling for tab interface

**Files:**
- `frontend/src/routes/batches/+page.svelte` - Add tabs
- `frontend/src/lib/components/BatchCard.svelte` - Add readonly prop

### Phase 4: Frontend - Historical View

**Tasks:**
1. Create historical batch detail page
2. Reuse existing TiltChart in read-only mode
3. Add export functionality (CSV, chart image)
4. Show final stats and recipe details
5. Add navigation from completed batch card to history view

**Files:**
- `frontend/src/routes/batches/[id]/history/+page.svelte` - New file
- `frontend/src/lib/components/TiltChart.svelte` - Add readonly prop

### Phase 5: Frontend - Maintenance UI

**Tasks:**
1. Create data maintenance page
2. Display orphaned data report
3. Build cleanup form with preview
4. Implement confirmation dialogs for destructive operations
5. Add refresh functionality after cleanup

**Files:**
- `frontend/src/routes/system/maintenance/+page.svelte` - New file
- `frontend/src/lib/api.ts` - Add maintenance API helpers

### Phase 6: Testing & Documentation

**Tasks:**
1. Test migration on dev database with existing data
2. Test soft delete/restore workflow
3. Test cleanup operations with various filters
4. Update CLAUDE.md with new endpoints
5. Update user documentation

## Testing Strategy

### Unit Tests (Backend)

```python
# Test soft delete
async def test_soft_delete_batch():
    batch = create_test_batch()
    response = await client.post(f"/api/batches/{batch.id}/delete")
    assert response.status_code == 200
    assert response.json()["type"] == "soft"

    # Verify batch still exists but is marked deleted
    db_batch = await db.get(Batch, batch.id)
    assert db_batch.deleted_at is not None

# Test hard delete
async def test_hard_delete_batch():
    batch = create_test_batch_with_readings()
    readings_count = await count_readings_for_batch(batch.id)
    assert readings_count > 0

    response = await client.post(f"/api/batches/{batch.id}/delete?hard_delete=true")
    assert response.status_code == 200

    # Verify batch and readings are gone
    db_batch = await db.get(Batch, batch.id)
    assert db_batch is None
    readings_count = await count_readings_for_batch(batch.id)
    assert readings_count == 0

# Test cleanup preview vs execute
async def test_cleanup_preview_vs_execute():
    # Preview should not delete
    preview_response = await client.post("/api/maintenance/cleanup-readings", json={
        "batch_id": 123,
        "preview_only": True
    })
    readings_before = await count_readings()

    # Execute should delete
    execute_response = await client.post("/api/maintenance/cleanup-readings", json={
        "batch_id": 123,
        "preview_only": False
    })
    readings_after = await count_readings()

    assert readings_after < readings_before
```

### Integration Tests

1. **Migration Test**: Run migration on copy of production DB
2. **Lifecycle Test**: Create batch → ferment → complete → soft delete → restore
3. **Cleanup Test**: Create orphaned readings → detect → preview → cleanup → verify
4. **UI Test**: Navigate tabs → view history → execute cleanup with confirmation

## Security Considerations

1. **Confirmation Required**: All destructive operations require user confirmation
2. **Preview First**: Cleanup defaults to preview mode (must explicitly execute)
3. **Audit Trail**: Consider adding audit log for maintenance operations (future)
4. **Permissions**: Maintenance endpoints should eventually require admin role (future)

## Performance Considerations

1. **Index on deleted_at**: Add index for deleted batch filtering
2. **Pagination**: Maintain pagination support for all list endpoints
3. **Eager Loading**: Continue using `selectinload()` for recipe/style relationships
4. **Cleanup Batching**: For large datasets, consider batch deletion (future optimization)

## Success Criteria

### User Stories

✅ As a brewer, I can view completed batches in a dedicated history section
✅ As a brewer, I can soft delete batches without losing fermentation data
✅ As a brewer, I can restore accidentally deleted batches
✅ As a user, I can see orphaned readings and cleanup options
✅ As a user, I can preview exactly what will be deleted before confirming
✅ As a user, I can export historical batch data as CSV

### Technical Acceptance

- [ ] Migration runs successfully on existing database
- [ ] All existing batch endpoints continue to work (backward compatibility)
- [ ] Soft deleted batches are hidden from default views
- [ ] Cleanup operations show accurate preview before execution
- [ ] Frontend tabs correctly filter batches by lifecycle stage
- [ ] Historical view displays full chart data for completed batches
- [ ] No orphaned readings created by normal batch operations

## Future Enhancements

1. **Batch Events Timeline**: Add event logging (dry hop additions, temp changes, notes)
2. **Comparison View**: Compare multiple batches side-by-side
3. **Export Formats**: Add PDF export with charts embedded
4. **Audit Log**: Track who deleted/restored batches and when
5. **Automatic Cleanup**: Scheduled job to clean readings older than X days
6. **Batch Templates**: Create new batches from historical batch settings
7. **Permissions**: Role-based access control for maintenance operations

## Open Questions

None - design approved for implementation.
