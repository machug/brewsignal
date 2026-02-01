# Batch Post-Mortem Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement a comprehensive post-mortem system with phase reflections, AI insights, and BJCP-style tasting notes.

**Architecture:** New `BatchReflection` table for phase-specific reflections, extend existing `TastingNote` with additional fields. AG-UI tools enable AI-guided data capture. Multi-tenant isolation via user_id on all new records.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic, SQLite migrations, AG-UI tools

**Design Doc:** `docs/plans/2026-02-01-batch-post-mortem-design.md`

---

## Task 1: BatchReflection Model

**Files:**
- Modify: `backend/models.py` (add BatchReflection SQLAlchemy model)
- Modify: `backend/models.py` (add Pydantic schemas)
- Modify: `backend/database.py` (add migration function)
- Test: `backend/tests/test_batch_reflection_model.py`

**Step 1: Write the failing test**

Create `backend/tests/test_batch_reflection_model.py`:

```python
"""Tests for BatchReflection model."""

import pytest
from datetime import datetime, timezone

from backend.models import BatchReflection, BatchReflectionCreate, BatchReflectionResponse


class TestBatchReflectionModel:
    """Test BatchReflection SQLAlchemy model."""

    def test_batch_reflection_has_required_fields(self):
        """BatchReflection model has all required fields."""
        # Check the model has expected columns
        columns = {c.name for c in BatchReflection.__table__.columns}
        required = {
            "id", "batch_id", "user_id", "phase", "created_at", "updated_at",
            "metrics", "what_went_well", "what_went_wrong", "lessons_learned",
            "next_time_changes", "ai_summary", "ai_generated_at", "ai_model_version"
        }
        assert required.issubset(columns), f"Missing columns: {required - columns}"

    def test_batch_reflection_phase_values(self):
        """Phase field accepts valid phase values."""
        valid_phases = ["brew_day", "fermentation", "packaging", "conditioning"]
        for phase in valid_phases:
            reflection = BatchReflection(batch_id=1, phase=phase)
            assert reflection.phase == phase


class TestBatchReflectionCreate:
    """Test BatchReflectionCreate Pydantic schema."""

    def test_create_with_minimal_fields(self):
        """Create schema works with minimal required fields."""
        data = BatchReflectionCreate(batch_id=1, phase="brew_day")
        assert data.batch_id == 1
        assert data.phase == "brew_day"
        assert data.metrics is None

    def test_create_with_metrics(self):
        """Create schema accepts metrics JSON."""
        metrics = {"efficiency_actual": 72.5, "efficiency_expected": 75.0}
        data = BatchReflectionCreate(batch_id=1, phase="brew_day", metrics=metrics)
        assert data.metrics == metrics

    def test_create_validates_phase(self):
        """Create schema rejects invalid phase."""
        with pytest.raises(ValueError, match="phase must be one of"):
            BatchReflectionCreate(batch_id=1, phase="invalid_phase")


class TestBatchReflectionResponse:
    """Test BatchReflectionResponse Pydantic schema."""

    def test_response_from_attributes(self):
        """Response schema can be created from model attributes."""
        now = datetime.now(timezone.utc)
        # Simulate ORM object attributes
        class MockReflection:
            id = 1
            batch_id = 1
            user_id = "user-123"
            phase = "brew_day"
            created_at = now
            updated_at = now
            metrics = {"efficiency_actual": 72.5}
            what_went_well = "Hit mash temp"
            what_went_wrong = None
            lessons_learned = None
            next_time_changes = None
            ai_summary = "Good brew day"
            ai_generated_at = now
            ai_model_version = "claude-3"

        response = BatchReflectionResponse.model_validate(MockReflection())
        assert response.id == 1
        assert response.phase == "brew_day"
        assert response.metrics == {"efficiency_actual": 72.5}
```

**Step 2: Run test to verify it fails**

Run: `cd /home/ladmin/Projects/brewsignal/brewsignal-web && python -m pytest backend/tests/test_batch_reflection_model.py -v`

Expected: FAIL with `ImportError: cannot import name 'BatchReflection'`

**Step 3: Write BatchReflection SQLAlchemy model**

Add to `backend/models.py` after the `TastingNote` class (around line 1080):

```python
class BatchReflection(Base):
    """Phase-specific reflections for a batch (brew day, fermentation, etc.)."""
    __tablename__ = "batch_reflections"
    __table_args__ = (
        Index("ix_batch_reflections_batch_phase", "batch_id", "phase"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batches.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    phase: Mapped[str] = mapped_column(String(20), nullable=False)  # brew_day, fermentation, packaging, conditioning

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Structured metrics (JSON blob, phase-specific)
    metrics: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Freeform reflection fields
    what_went_well: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    what_went_wrong: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    lessons_learned: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    next_time_changes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # AI-generated content
    ai_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ai_generated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ai_model_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Relationship
    batch: Mapped["Batch"] = relationship(back_populates="reflections")
```

**Step 4: Add Pydantic schemas**

Add to `backend/models.py` after TastingNoteResponse (around line 2140):

```python
# =============================================================================
# Batch Reflection Schemas
# =============================================================================

class BatchReflectionCreate(BaseModel):
    """Create a new batch reflection."""
    batch_id: int
    phase: str
    metrics: Optional[dict] = None
    what_went_well: Optional[str] = None
    what_went_wrong: Optional[str] = None
    lessons_learned: Optional[str] = None
    next_time_changes: Optional[str] = None

    @field_validator("phase")
    @classmethod
    def validate_phase(cls, v: str) -> str:
        valid = ["brew_day", "fermentation", "packaging", "conditioning"]
        if v not in valid:
            raise ValueError(f"phase must be one of: {', '.join(valid)}")
        return v


class BatchReflectionUpdate(BaseModel):
    """Update an existing batch reflection."""
    metrics: Optional[dict] = None
    what_went_well: Optional[str] = None
    what_went_wrong: Optional[str] = None
    lessons_learned: Optional[str] = None
    next_time_changes: Optional[str] = None


class BatchReflectionResponse(BaseModel):
    """Response schema for a batch reflection."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    batch_id: int
    user_id: Optional[str] = None
    phase: str
    created_at: datetime
    updated_at: datetime
    metrics: Optional[dict] = None
    what_went_well: Optional[str] = None
    what_went_wrong: Optional[str] = None
    lessons_learned: Optional[str] = None
    next_time_changes: Optional[str] = None
    ai_summary: Optional[str] = None
    ai_generated_at: Optional[datetime] = None
    ai_model_version: Optional[str] = None

    @field_serializer('created_at', 'updated_at', 'ai_generated_at')
    def serialize_dt(self, dt: Optional[datetime]) -> Optional[str]:
        return serialize_datetime_to_utc(dt)
```

**Step 5: Add relationship to Batch model**

In `backend/models.py`, find the Batch class and add after `tasting_notes` relationship:

```python
    reflections: Mapped[list["BatchReflection"]] = relationship(
        back_populates="batch", cascade="all, delete-orphan"
    )
```

**Step 6: Run test to verify it passes**

Run: `cd /home/ladmin/Projects/brewsignal/brewsignal-web && python -m pytest backend/tests/test_batch_reflection_model.py -v`

Expected: PASS (all 5 tests)

**Step 7: Commit**

```bash
git add backend/models.py backend/tests/test_batch_reflection_model.py
git commit -m "feat(models): Add BatchReflection model and schemas

Adds SQLAlchemy model for phase-specific batch reflections with:
- Structured metrics (JSON) for phase-specific data
- Freeform reflection fields (what_went_well, lessons_learned, etc.)
- AI-generated summary fields
- Multi-tenant user_id support"
```

---

## Task 2: BatchReflection Migration

**Files:**
- Modify: `backend/database.py` (add migration function)
- Test: `backend/tests/test_batch_reflection_migration.py`

**Step 1: Write the failing test**

Create `backend/tests/test_batch_reflection_migration.py`:

```python
"""Tests for BatchReflection migration."""

import pytest
from sqlalchemy import inspect, text


class TestBatchReflectionMigration:
    """Test batch_reflections table migration."""

    @pytest.mark.asyncio
    async def test_batch_reflections_table_exists(self, db):
        """batch_reflections table is created."""
        result = await db.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='batch_reflections'"
        ))
        table = result.scalar()
        assert table == "batch_reflections"

    @pytest.mark.asyncio
    async def test_batch_reflections_has_columns(self, db):
        """batch_reflections table has all required columns."""
        result = await db.execute(text("PRAGMA table_info(batch_reflections)"))
        columns = {row[1] for row in result.fetchall()}
        required = {
            "id", "batch_id", "user_id", "phase", "created_at", "updated_at",
            "metrics", "what_went_well", "what_went_wrong", "lessons_learned",
            "next_time_changes", "ai_summary", "ai_generated_at", "ai_model_version"
        }
        assert required.issubset(columns), f"Missing columns: {required - columns}"

    @pytest.mark.asyncio
    async def test_batch_reflections_indexes(self, db):
        """batch_reflections table has required indexes."""
        result = await db.execute(text("PRAGMA index_list(batch_reflections)"))
        indexes = {row[1] for row in result.fetchall()}
        # Should have user_id index and batch_phase composite index
        assert any("user_id" in idx for idx in indexes)
```

**Step 2: Run test to verify it fails**

Run: `cd /home/ladmin/Projects/brewsignal/brewsignal-web && python -m pytest backend/tests/test_batch_reflection_migration.py -v`

Expected: FAIL - table doesn't exist yet (create_all needs to run with new model)

**Step 3: Verify migration works via create_all**

The SQLAlchemy model will be created via `Base.metadata.create_all()` in `init_db()`. No additional migration function needed for new tables.

**Step 4: Run test to verify it passes**

Run: `cd /home/ladmin/Projects/brewsignal/brewsignal-web && python -m pytest backend/tests/test_batch_reflection_migration.py -v`

Expected: PASS (create_all handles new table creation)

**Step 5: Commit**

```bash
git add backend/tests/test_batch_reflection_migration.py
git commit -m "test(migration): Add BatchReflection table migration tests"
```

---

## Task 3: Extend TastingNote Model

**Files:**
- Modify: `backend/models.py` (extend TastingNote with new fields)
- Modify: `backend/database.py` (add migration for new columns)
- Test: `backend/tests/test_tasting_note_extended.py`

**Step 1: Write the failing test**

Create `backend/tests/test_tasting_note_extended.py`:

```python
"""Tests for extended TastingNote model fields."""

import pytest
from sqlalchemy import text


class TestTastingNoteExtended:
    """Test extended TastingNote fields."""

    @pytest.mark.asyncio
    async def test_tasting_note_has_extended_fields(self, db):
        """TastingNote table has new extended columns."""
        result = await db.execute(text("PRAGMA table_info(tasting_notes)"))
        columns = {row[1] for row in result.fetchall()}
        new_fields = {
            "user_id", "days_since_packaging", "serving_temp_c", "glassware",
            "total_score", "to_style", "style_deviation_notes",
            "ai_suggestions", "interview_transcript"
        }
        assert new_fields.issubset(columns), f"Missing columns: {new_fields - columns}"
```

**Step 2: Run test to verify it fails**

Run: `cd /home/ladmin/Projects/brewsignal/brewsignal-web && python -m pytest backend/tests/test_tasting_note_extended.py -v`

Expected: FAIL with missing columns

**Step 3: Extend TastingNote SQLAlchemy model**

In `backend/models.py`, modify the `TastingNote` class to add new fields after existing fields:

```python
class TastingNote(Base):
    """Tasting notes for a batch - can have multiple over time as beer conditions."""
    __tablename__ = "tasting_notes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batches.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)  # NEW: Multi-tenant

    # When tasted
    tasted_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))

    # Context - NEW fields
    days_since_packaging: Mapped[Optional[int]] = mapped_column(nullable=True)
    serving_temp_c: Mapped[Optional[float]] = mapped_column(nullable=True)
    glassware: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Appearance (1-5 scale)
    appearance_score: Mapped[Optional[int]] = mapped_column()
    appearance_notes: Mapped[Optional[str]] = mapped_column(Text)

    # Aroma (1-5 scale)
    aroma_score: Mapped[Optional[int]] = mapped_column()
    aroma_notes: Mapped[Optional[str]] = mapped_column(Text)

    # Flavor (1-5 scale)
    flavor_score: Mapped[Optional[int]] = mapped_column()
    flavor_notes: Mapped[Optional[str]] = mapped_column(Text)

    # Mouthfeel (1-5 scale)
    mouthfeel_score: Mapped[Optional[int]] = mapped_column()
    mouthfeel_notes: Mapped[Optional[str]] = mapped_column(Text)

    # Overall impression
    overall_score: Mapped[Optional[int]] = mapped_column()
    overall_notes: Mapped[Optional[str]] = mapped_column(Text)

    # Computed total - NEW
    total_score: Mapped[Optional[int]] = mapped_column(nullable=True)

    # Style assessment - NEW
    to_style: Mapped[Optional[bool]] = mapped_column(nullable=True)
    style_deviation_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # AI-assisted - NEW
    ai_suggestions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    interview_transcript: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationship
    batch: Mapped["Batch"] = relationship(back_populates="tasting_notes")
```

**Step 4: Add migration function**

Add to `backend/database.py` before `init_db()`:

```python
def _migrate_extend_tasting_notes(conn):
    """Add extended fields to tasting_notes table."""
    from sqlalchemy import inspect, text
    inspector = inspect(conn)

    if "tasting_notes" not in inspector.get_table_names():
        return  # Fresh install, create_all will handle it

    columns = [c["name"] for c in inspector.get_columns("tasting_notes")]

    new_columns = [
        ("user_id", "VARCHAR(36)"),
        ("days_since_packaging", "INTEGER"),
        ("serving_temp_c", "REAL"),
        ("glassware", "VARCHAR(50)"),
        ("total_score", "INTEGER"),
        ("to_style", "BOOLEAN"),
        ("style_deviation_notes", "TEXT"),
        ("ai_suggestions", "TEXT"),
        ("interview_transcript", "TEXT"),  # JSON stored as TEXT in SQLite
    ]

    for col_name, col_type in new_columns:
        if col_name not in columns:
            try:
                conn.execute(text(f"ALTER TABLE tasting_notes ADD COLUMN {col_name} {col_type}"))
                print(f"Migration: Added {col_name} column to tasting_notes table")
            except Exception as e:
                print(f"Migration: Skipping {col_name} on tasting_notes - {e}")

    # Add index for user_id if it doesn't exist
    if "user_id" not in columns:
        try:
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_tasting_notes_user_id ON tasting_notes(user_id)"))
        except Exception:
            pass
```

**Step 5: Call migration in init_db()**

In `backend/database.py`, add to `init_db()`:

```python
        _migrate_extend_tasting_notes(conn)
```

**Step 6: Update Pydantic schemas**

Update `TastingNoteCreate`, `TastingNoteUpdate`, and `TastingNoteResponse` in `backend/models.py`:

```python
class TastingNoteCreate(BaseModel):
    """Create a new tasting note for a batch."""
    batch_id: int
    tasted_at: Optional[datetime] = None
    days_since_packaging: Optional[int] = None
    serving_temp_c: Optional[float] = None
    glassware: Optional[str] = None
    appearance_score: Optional[int] = None
    appearance_notes: Optional[str] = None
    aroma_score: Optional[int] = None
    aroma_notes: Optional[str] = None
    flavor_score: Optional[int] = None
    flavor_notes: Optional[str] = None
    mouthfeel_score: Optional[int] = None
    mouthfeel_notes: Optional[str] = None
    overall_score: Optional[int] = None
    overall_notes: Optional[str] = None
    to_style: Optional[bool] = None
    style_deviation_notes: Optional[str] = None

    @field_validator("appearance_score", "aroma_score", "flavor_score", "mouthfeel_score", "overall_score")
    @classmethod
    def validate_score(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and (v < 1 or v > 5):
            raise ValueError("Score must be between 1 and 5")
        return v


class TastingNoteUpdate(BaseModel):
    """Update an existing tasting note."""
    tasted_at: Optional[datetime] = None
    days_since_packaging: Optional[int] = None
    serving_temp_c: Optional[float] = None
    glassware: Optional[str] = None
    appearance_score: Optional[int] = None
    appearance_notes: Optional[str] = None
    aroma_score: Optional[int] = None
    aroma_notes: Optional[str] = None
    flavor_score: Optional[int] = None
    flavor_notes: Optional[str] = None
    mouthfeel_score: Optional[int] = None
    mouthfeel_notes: Optional[str] = None
    overall_score: Optional[int] = None
    overall_notes: Optional[str] = None
    to_style: Optional[bool] = None
    style_deviation_notes: Optional[str] = None

    @field_validator("appearance_score", "aroma_score", "flavor_score", "mouthfeel_score", "overall_score")
    @classmethod
    def validate_score(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and (v < 1 or v > 5):
            raise ValueError("Score must be between 1 and 5")
        return v


class TastingNoteResponse(BaseModel):
    """Response schema for a tasting note."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    batch_id: int
    user_id: Optional[str] = None
    tasted_at: datetime
    days_since_packaging: Optional[int] = None
    serving_temp_c: Optional[float] = None
    glassware: Optional[str] = None
    appearance_score: Optional[int] = None
    appearance_notes: Optional[str] = None
    aroma_score: Optional[int] = None
    aroma_notes: Optional[str] = None
    flavor_score: Optional[int] = None
    flavor_notes: Optional[str] = None
    mouthfeel_score: Optional[int] = None
    mouthfeel_notes: Optional[str] = None
    overall_score: Optional[int] = None
    overall_notes: Optional[str] = None
    total_score: Optional[int] = None
    to_style: Optional[bool] = None
    style_deviation_notes: Optional[str] = None
    ai_suggestions: Optional[str] = None
    interview_transcript: Optional[dict] = None
    created_at: datetime
    updated_at: datetime

    @field_serializer('tasted_at', 'created_at', 'updated_at')
    def serialize_dt(self, dt: Optional[datetime]) -> Optional[str]:
        return serialize_datetime_to_utc(dt)
```

**Step 7: Run test to verify it passes**

Run: `cd /home/ladmin/Projects/brewsignal/brewsignal-web && python -m pytest backend/tests/test_tasting_note_extended.py -v`

Expected: PASS

**Step 8: Commit**

```bash
git add backend/models.py backend/database.py backend/tests/test_tasting_note_extended.py
git commit -m "feat(models): Extend TastingNote with context and AI fields

Adds to TastingNote:
- user_id for multi-tenant isolation
- Context fields: days_since_packaging, serving_temp_c, glassware
- total_score computed field
- Style assessment: to_style, style_deviation_notes
- AI fields: ai_suggestions, interview_transcript"
```

---

## Task 4: Reflections Router

**Files:**
- Create: `backend/routers/reflections.py`
- Modify: `backend/main.py` (register router)
- Test: `backend/tests/test_reflections_api.py`

**Step 1: Write the failing test**

Create `backend/tests/test_reflections_api.py`:

```python
"""Tests for reflections API endpoints."""

import pytest
from httpx import AsyncClient


class TestReflectionsAPI:
    """Test reflection CRUD endpoints."""

    @pytest.mark.asyncio
    async def test_create_reflection(self, client: AsyncClient, test_batch):
        """POST /api/batches/{id}/reflections creates a reflection."""
        response = await client.post(
            f"/api/batches/{test_batch.id}/reflections",
            json={
                "phase": "brew_day",
                "what_went_well": "Hit mash temp on first try",
                "metrics": {"efficiency_actual": 72.5, "efficiency_expected": 75.0}
            }
        )
        assert response.status_code == 201
        data = response.json()
        assert data["phase"] == "brew_day"
        assert data["what_went_well"] == "Hit mash temp on first try"
        assert data["metrics"]["efficiency_actual"] == 72.5

    @pytest.mark.asyncio
    async def test_list_reflections(self, client: AsyncClient, test_batch):
        """GET /api/batches/{id}/reflections returns all reflections."""
        # Create a reflection first
        await client.post(
            f"/api/batches/{test_batch.id}/reflections",
            json={"phase": "brew_day", "what_went_well": "Good efficiency"}
        )

        response = await client.get(f"/api/batches/{test_batch.id}/reflections")
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert data[0]["phase"] == "brew_day"

    @pytest.mark.asyncio
    async def test_get_reflection_by_phase(self, client: AsyncClient, test_batch):
        """GET /api/batches/{id}/reflections/{phase} returns specific phase."""
        await client.post(
            f"/api/batches/{test_batch.id}/reflections",
            json={"phase": "fermentation", "what_went_well": "Clean fermentation"}
        )

        response = await client.get(f"/api/batches/{test_batch.id}/reflections/fermentation")
        assert response.status_code == 200
        data = response.json()
        assert data["phase"] == "fermentation"

    @pytest.mark.asyncio
    async def test_update_reflection(self, client: AsyncClient, test_batch):
        """PUT /api/batches/{id}/reflections/{id} updates a reflection."""
        create_resp = await client.post(
            f"/api/batches/{test_batch.id}/reflections",
            json={"phase": "brew_day"}
        )
        reflection_id = create_resp.json()["id"]

        response = await client.put(
            f"/api/batches/{test_batch.id}/reflections/{reflection_id}",
            json={"lessons_learned": "Start heating strike water earlier"}
        )
        assert response.status_code == 200
        assert response.json()["lessons_learned"] == "Start heating strike water earlier"

    @pytest.mark.asyncio
    async def test_reflection_user_isolation(self, client: AsyncClient, test_batch):
        """Reflections are filtered by user ownership."""
        # Create reflection
        await client.post(
            f"/api/batches/{test_batch.id}/reflections",
            json={"phase": "brew_day"}
        )

        # Should see our own reflection
        response = await client.get(f"/api/batches/{test_batch.id}/reflections")
        assert response.status_code == 200
        assert len(response.json()) >= 1
```

**Step 2: Run test to verify it fails**

Run: `cd /home/ladmin/Projects/brewsignal/brewsignal-web && python -m pytest backend/tests/test_reflections_api.py -v`

Expected: FAIL with 404 (router not registered)

**Step 3: Create reflections router**

Create `backend/routers/reflections.py`:

```python
"""Batch reflections API endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import AuthUser, require_auth
from ..database import get_db
from ..models import (
    Batch,
    BatchReflection,
    BatchReflectionCreate,
    BatchReflectionUpdate,
    BatchReflectionResponse,
)
from .batches import user_owns_batch, get_user_batch

router = APIRouter(prefix="/api/batches", tags=["reflections"])


@router.post("/{batch_id}/reflections", response_model=BatchReflectionResponse, status_code=201)
async def create_reflection(
    batch_id: int,
    data: BatchReflectionCreate,
    user: AuthUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Create a new reflection for a batch phase."""
    # Verify batch exists and user owns it
    batch = await get_user_batch(batch_id, user, db)

    # Check if reflection already exists for this phase
    existing = await db.execute(
        select(BatchReflection).where(
            BatchReflection.batch_id == batch_id,
            BatchReflection.phase == data.phase
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail=f"Reflection for phase '{data.phase}' already exists. Use PUT to update."
        )

    reflection = BatchReflection(
        batch_id=batch_id,
        user_id=user.user_id,
        phase=data.phase,
        metrics=data.metrics,
        what_went_well=data.what_went_well,
        what_went_wrong=data.what_went_wrong,
        lessons_learned=data.lessons_learned,
        next_time_changes=data.next_time_changes,
    )
    db.add(reflection)
    await db.commit()
    await db.refresh(reflection)
    return reflection


@router.get("/{batch_id}/reflections", response_model=list[BatchReflectionResponse])
async def list_reflections(
    batch_id: int,
    user: AuthUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """List all reflections for a batch."""
    # Verify batch exists and user owns it
    await get_user_batch(batch_id, user, db)

    result = await db.execute(
        select(BatchReflection)
        .where(BatchReflection.batch_id == batch_id)
        .order_by(BatchReflection.created_at)
    )
    return result.scalars().all()


@router.get("/{batch_id}/reflections/{phase}", response_model=BatchReflectionResponse)
async def get_reflection_by_phase(
    batch_id: int,
    phase: str,
    user: AuthUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific phase reflection for a batch."""
    await get_user_batch(batch_id, user, db)

    result = await db.execute(
        select(BatchReflection).where(
            BatchReflection.batch_id == batch_id,
            BatchReflection.phase == phase
        )
    )
    reflection = result.scalar_one_or_none()
    if not reflection:
        raise HTTPException(status_code=404, detail=f"No reflection found for phase '{phase}'")
    return reflection


@router.put("/{batch_id}/reflections/{reflection_id}", response_model=BatchReflectionResponse)
async def update_reflection(
    batch_id: int,
    reflection_id: int,
    data: BatchReflectionUpdate,
    user: AuthUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Update a reflection."""
    await get_user_batch(batch_id, user, db)

    result = await db.execute(
        select(BatchReflection).where(
            BatchReflection.id == reflection_id,
            BatchReflection.batch_id == batch_id
        )
    )
    reflection = result.scalar_one_or_none()
    if not reflection:
        raise HTTPException(status_code=404, detail="Reflection not found")

    # Update fields if provided
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(reflection, field, value)

    await db.commit()
    await db.refresh(reflection)
    return reflection
```

**Step 4: Register router in main.py**

In `backend/main.py`, add import and registration:

```python
from .routers import reflections

app.include_router(reflections.router)
```

**Step 5: Add test fixtures**

Add to `backend/tests/conftest.py` if not present:

```python
@pytest.fixture
async def test_batch(db):
    """Create a test batch for reflection tests."""
    from backend.models import Batch
    batch = Batch(name="Test Batch", status="brewing", user_id="test-user")
    db.add(batch)
    await db.commit()
    await db.refresh(batch)
    return batch
```

**Step 6: Run test to verify it passes**

Run: `cd /home/ladmin/Projects/brewsignal/brewsignal-web && python -m pytest backend/tests/test_reflections_api.py -v`

Expected: PASS (all 5 tests)

**Step 7: Commit**

```bash
git add backend/routers/reflections.py backend/main.py backend/tests/test_reflections_api.py backend/tests/conftest.py
git commit -m "feat(api): Add batch reflections CRUD endpoints

- POST /api/batches/{id}/reflections - create phase reflection
- GET /api/batches/{id}/reflections - list all reflections
- GET /api/batches/{id}/reflections/{phase} - get specific phase
- PUT /api/batches/{id}/reflections/{id} - update reflection

Includes user ownership verification and multi-tenant isolation."
```

---

## Task 5: AG-UI Reflection Tools

**Files:**
- Create: `backend/services/llm/tools/reflections.py`
- Modify: `backend/services/llm/tools/__init__.py`
- Test: `backend/tests/test_reflection_tools.py`

**Step 1: Write the failing test**

Create `backend/tests/test_reflection_tools.py`:

```python
"""Tests for AG-UI reflection tools."""

import pytest
from backend.services.llm.tools.reflections import (
    create_batch_reflection,
    get_batch_reflections,
    update_batch_reflection,
)


class TestReflectionTools:
    """Test AG-UI reflection tool functions."""

    @pytest.mark.asyncio
    async def test_create_batch_reflection(self, db, test_batch):
        """create_batch_reflection creates and returns reflection."""
        result = await create_batch_reflection(
            db=db,
            batch_id=test_batch.id,
            phase="brew_day",
            what_went_well="Great efficiency",
            user_id="test-user"
        )
        assert result["success"] is True
        assert result["reflection"]["phase"] == "brew_day"
        assert result["reflection"]["what_went_well"] == "Great efficiency"

    @pytest.mark.asyncio
    async def test_get_batch_reflections(self, db, test_batch):
        """get_batch_reflections returns all reflections for a batch."""
        await create_batch_reflection(
            db=db, batch_id=test_batch.id, phase="brew_day", user_id="test-user"
        )
        await create_batch_reflection(
            db=db, batch_id=test_batch.id, phase="fermentation", user_id="test-user"
        )

        result = await get_batch_reflections(db=db, batch_id=test_batch.id, user_id="test-user")
        assert result["count"] == 2
        phases = [r["phase"] for r in result["reflections"]]
        assert "brew_day" in phases
        assert "fermentation" in phases

    @pytest.mark.asyncio
    async def test_update_batch_reflection(self, db, test_batch):
        """update_batch_reflection updates reflection fields."""
        create_result = await create_batch_reflection(
            db=db, batch_id=test_batch.id, phase="brew_day", user_id="test-user"
        )
        reflection_id = create_result["reflection"]["id"]

        result = await update_batch_reflection(
            db=db,
            reflection_id=reflection_id,
            lessons_learned="Preheat mash tun",
            user_id="test-user"
        )
        assert result["success"] is True
        assert result["reflection"]["lessons_learned"] == "Preheat mash tun"
```

**Step 2: Run test to verify it fails**

Run: `cd /home/ladmin/Projects/brewsignal/brewsignal-web && python -m pytest backend/tests/test_reflection_tools.py -v`

Expected: FAIL with `ImportError`

**Step 3: Create reflection tools**

Create `backend/services/llm/tools/reflections.py`:

```python
"""Batch reflection tools for the AI brewing assistant."""

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Batch, BatchReflection


async def create_batch_reflection(
    db: AsyncSession,
    batch_id: int,
    phase: str,
    metrics: Optional[dict] = None,
    what_went_well: Optional[str] = None,
    what_went_wrong: Optional[str] = None,
    lessons_learned: Optional[str] = None,
    next_time_changes: Optional[str] = None,
    user_id: Optional[str] = None,
) -> dict[str, Any]:
    """Create a reflection for a batch phase.

    Use this to record observations and learnings after completing a brewing phase.
    """
    # Verify batch exists
    batch_result = await db.execute(select(Batch).where(Batch.id == batch_id))
    batch = batch_result.scalar_one_or_none()
    if not batch:
        return {"success": False, "error": f"Batch {batch_id} not found"}

    # Check for existing reflection
    existing = await db.execute(
        select(BatchReflection).where(
            BatchReflection.batch_id == batch_id,
            BatchReflection.phase == phase
        )
    )
    if existing.scalar_one_or_none():
        return {"success": False, "error": f"Reflection for phase '{phase}' already exists"}

    reflection = BatchReflection(
        batch_id=batch_id,
        user_id=user_id,
        phase=phase,
        metrics=metrics,
        what_went_well=what_went_well,
        what_went_wrong=what_went_wrong,
        lessons_learned=lessons_learned,
        next_time_changes=next_time_changes,
    )
    db.add(reflection)
    await db.commit()
    await db.refresh(reflection)

    return {
        "success": True,
        "reflection": {
            "id": reflection.id,
            "batch_id": reflection.batch_id,
            "phase": reflection.phase,
            "metrics": reflection.metrics,
            "what_went_well": reflection.what_went_well,
            "what_went_wrong": reflection.what_went_wrong,
            "lessons_learned": reflection.lessons_learned,
            "next_time_changes": reflection.next_time_changes,
            "ai_summary": reflection.ai_summary,
            "created_at": reflection.created_at.isoformat() if reflection.created_at else None,
        }
    }


async def get_batch_reflections(
    db: AsyncSession,
    batch_id: int,
    phase: Optional[str] = None,
    user_id: Optional[str] = None,
) -> dict[str, Any]:
    """Get reflections for a batch, optionally filtered by phase."""
    query = select(BatchReflection).where(BatchReflection.batch_id == batch_id)
    if phase:
        query = query.where(BatchReflection.phase == phase)
    query = query.order_by(BatchReflection.created_at)

    result = await db.execute(query)
    reflections = result.scalars().all()

    return {
        "count": len(reflections),
        "reflections": [
            {
                "id": r.id,
                "batch_id": r.batch_id,
                "phase": r.phase,
                "metrics": r.metrics,
                "what_went_well": r.what_went_well,
                "what_went_wrong": r.what_went_wrong,
                "lessons_learned": r.lessons_learned,
                "next_time_changes": r.next_time_changes,
                "ai_summary": r.ai_summary,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in reflections
        ]
    }


async def update_batch_reflection(
    db: AsyncSession,
    reflection_id: int,
    metrics: Optional[dict] = None,
    what_went_well: Optional[str] = None,
    what_went_wrong: Optional[str] = None,
    lessons_learned: Optional[str] = None,
    next_time_changes: Optional[str] = None,
    user_id: Optional[str] = None,
) -> dict[str, Any]:
    """Update an existing batch reflection."""
    result = await db.execute(
        select(BatchReflection).where(BatchReflection.id == reflection_id)
    )
    reflection = result.scalar_one_or_none()
    if not reflection:
        return {"success": False, "error": f"Reflection {reflection_id} not found"}

    # Update provided fields
    if metrics is not None:
        reflection.metrics = metrics
    if what_went_well is not None:
        reflection.what_went_well = what_went_well
    if what_went_wrong is not None:
        reflection.what_went_wrong = what_went_wrong
    if lessons_learned is not None:
        reflection.lessons_learned = lessons_learned
    if next_time_changes is not None:
        reflection.next_time_changes = next_time_changes

    await db.commit()
    await db.refresh(reflection)

    return {
        "success": True,
        "reflection": {
            "id": reflection.id,
            "batch_id": reflection.batch_id,
            "phase": reflection.phase,
            "metrics": reflection.metrics,
            "what_went_well": reflection.what_went_well,
            "what_went_wrong": reflection.what_went_wrong,
            "lessons_learned": reflection.lessons_learned,
            "next_time_changes": reflection.next_time_changes,
            "ai_summary": reflection.ai_summary,
            "updated_at": reflection.updated_at.isoformat() if reflection.updated_at else None,
        }
    }
```

**Step 4: Add tool definitions to __init__.py**

In `backend/services/llm/tools/__init__.py`, add imports and tool definitions:

```python
from .reflections import (
    create_batch_reflection,
    get_batch_reflections,
    update_batch_reflection,
)

# Add to TOOL_DEFINITIONS list:
    {
        "type": "function",
        "function": {
            "name": "create_batch_reflection",
            "description": "Create a reflection for a batch phase (brew_day, fermentation, packaging, conditioning). Use this to record what went well, what went wrong, and lessons learned after completing a brewing phase.",
            "parameters": {
                "type": "object",
                "properties": {
                    "batch_id": {"type": "integer", "description": "The batch ID"},
                    "phase": {"type": "string", "enum": ["brew_day", "fermentation", "packaging", "conditioning"], "description": "The brewing phase this reflection is for"},
                    "metrics": {"type": "object", "description": "Phase-specific metrics (efficiency, FG, etc.)"},
                    "what_went_well": {"type": "string", "description": "What went well during this phase"},
                    "what_went_wrong": {"type": "string", "description": "What went wrong or could be improved"},
                    "lessons_learned": {"type": "string", "description": "Key takeaways from this phase"},
                    "next_time_changes": {"type": "string", "description": "What to do differently next time"}
                },
                "required": ["batch_id", "phase"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_batch_reflections",
            "description": "Get all reflections for a batch, or a specific phase reflection. Use this to review past observations and learnings.",
            "parameters": {
                "type": "object",
                "properties": {
                    "batch_id": {"type": "integer", "description": "The batch ID"},
                    "phase": {"type": "string", "enum": ["brew_day", "fermentation", "packaging", "conditioning"], "description": "Optional: filter to specific phase"}
                },
                "required": ["batch_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_batch_reflection",
            "description": "Update an existing batch reflection with new observations or learnings.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reflection_id": {"type": "integer", "description": "The reflection ID to update"},
                    "metrics": {"type": "object", "description": "Updated metrics"},
                    "what_went_well": {"type": "string"},
                    "what_went_wrong": {"type": "string"},
                    "lessons_learned": {"type": "string"},
                    "next_time_changes": {"type": "string"}
                },
                "required": ["reflection_id"]
            }
        }
    },
```

**Step 5: Add execute_tool handlers**

In the `execute_tool` function in `__init__.py`:

```python
    elif name == "create_batch_reflection":
        return await create_batch_reflection(db, user_id=user_id, **arguments)
    elif name == "get_batch_reflections":
        return await get_batch_reflections(db, user_id=user_id, **arguments)
    elif name == "update_batch_reflection":
        return await update_batch_reflection(db, user_id=user_id, **arguments)
```

**Step 6: Run test to verify it passes**

Run: `cd /home/ladmin/Projects/brewsignal/brewsignal-web && python -m pytest backend/tests/test_reflection_tools.py -v`

Expected: PASS

**Step 7: Commit**

```bash
git add backend/services/llm/tools/reflections.py backend/services/llm/tools/__init__.py backend/tests/test_reflection_tools.py
git commit -m "feat(ag-ui): Add batch reflection tools

- create_batch_reflection: Record phase observations
- get_batch_reflections: Retrieve reflections for a batch
- update_batch_reflection: Update existing reflections

Enables AI to help capture and query brewing learnings."
```

---

## Task 6: Extended Tasting Note Router Updates

**Files:**
- Modify: `backend/routers/batches.py` (update tasting note endpoints)
- Test: `backend/tests/test_tasting_notes_extended.py`

**Step 1: Write the failing test**

Create `backend/tests/test_tasting_notes_extended.py`:

```python
"""Tests for extended tasting note API endpoints."""

import pytest
from httpx import AsyncClient


class TestTastingNotesExtendedAPI:
    """Test extended tasting note fields in API."""

    @pytest.mark.asyncio
    async def test_create_tasting_note_with_context(self, client: AsyncClient, test_batch):
        """POST tasting note accepts context fields."""
        response = await client.post(
            f"/api/batches/{test_batch.id}/tasting-notes",
            json={
                "batch_id": test_batch.id,
                "days_since_packaging": 14,
                "serving_temp_c": 4.0,
                "glassware": "tulip",
                "appearance_score": 4,
                "appearance_notes": "Clear golden color",
                "aroma_score": 4,
                "flavor_score": 5,
                "mouthfeel_score": 4,
                "overall_score": 4,
            }
        )
        assert response.status_code == 201
        data = response.json()
        assert data["days_since_packaging"] == 14
        assert data["serving_temp_c"] == 4.0
        assert data["glassware"] == "tulip"

    @pytest.mark.asyncio
    async def test_create_tasting_note_calculates_total(self, client: AsyncClient, test_batch):
        """POST tasting note calculates total_score."""
        response = await client.post(
            f"/api/batches/{test_batch.id}/tasting-notes",
            json={
                "batch_id": test_batch.id,
                "appearance_score": 4,
                "aroma_score": 4,
                "flavor_score": 5,
                "mouthfeel_score": 4,
                "overall_score": 4,
            }
        )
        assert response.status_code == 201
        data = response.json()
        assert data["total_score"] == 21  # 4+4+5+4+4

    @pytest.mark.asyncio
    async def test_tasting_note_style_assessment(self, client: AsyncClient, test_batch):
        """POST tasting note accepts style assessment fields."""
        response = await client.post(
            f"/api/batches/{test_batch.id}/tasting-notes",
            json={
                "batch_id": test_batch.id,
                "appearance_score": 3,
                "to_style": False,
                "style_deviation_notes": "Too dark for style, more like a brown ale"
            }
        )
        assert response.status_code == 201
        data = response.json()
        assert data["to_style"] is False
        assert "Too dark" in data["style_deviation_notes"]

    @pytest.mark.asyncio
    async def test_tasting_note_user_isolation(self, client: AsyncClient, test_batch):
        """Tasting notes are filtered by user ownership."""
        # Create a tasting note
        await client.post(
            f"/api/batches/{test_batch.id}/tasting-notes",
            json={"batch_id": test_batch.id, "appearance_score": 4}
        )

        # List should return our note
        response = await client.get(f"/api/batches/{test_batch.id}/tasting-notes")
        assert response.status_code == 200
        assert len(response.json()) >= 1
```

**Step 2: Run test to verify current behavior**

Run: `cd /home/ladmin/Projects/brewsignal/brewsignal-web && python -m pytest backend/tests/test_tasting_notes_extended.py -v`

Expected: Some tests may fail due to missing total_score calculation

**Step 3: Update tasting note endpoints**

In `backend/routers/batches.py`, update the create tasting note endpoint to calculate total_score and accept new fields. Find the existing tasting note POST endpoint and update:

```python
@router.post("/{batch_id}/tasting-notes", response_model=TastingNoteResponse, status_code=201)
async def create_tasting_note(
    batch_id: int,
    data: TastingNoteCreate,
    user: AuthUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Create a new tasting note for a batch."""
    batch = await get_user_batch(batch_id, user, db)

    # Calculate total score if all scores provided
    scores = [data.appearance_score, data.aroma_score, data.flavor_score,
              data.mouthfeel_score, data.overall_score]
    total = sum(s for s in scores if s is not None) if any(scores) else None

    note = TastingNote(
        batch_id=batch_id,
        user_id=user.user_id,
        tasted_at=data.tasted_at or datetime.now(timezone.utc),
        days_since_packaging=data.days_since_packaging,
        serving_temp_c=data.serving_temp_c,
        glassware=data.glassware,
        appearance_score=data.appearance_score,
        appearance_notes=data.appearance_notes,
        aroma_score=data.aroma_score,
        aroma_notes=data.aroma_notes,
        flavor_score=data.flavor_score,
        flavor_notes=data.flavor_notes,
        mouthfeel_score=data.mouthfeel_score,
        mouthfeel_notes=data.mouthfeel_notes,
        overall_score=data.overall_score,
        overall_notes=data.overall_notes,
        total_score=total,
        to_style=data.to_style,
        style_deviation_notes=data.style_deviation_notes,
    )
    db.add(note)
    await db.commit()
    await db.refresh(note)
    return note
```

**Step 4: Run test to verify it passes**

Run: `cd /home/ladmin/Projects/brewsignal/brewsignal-web && python -m pytest backend/tests/test_tasting_notes_extended.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/routers/batches.py backend/tests/test_tasting_notes_extended.py
git commit -m "feat(api): Extend tasting note endpoints with context and scoring

- Accept context fields: days_since_packaging, serving_temp_c, glassware
- Calculate total_score from individual scores
- Accept style assessment: to_style, style_deviation_notes
- Add user_id for multi-tenant isolation"
```

---

## Task 7: AG-UI Tasting Tools

**Files:**
- Create: `backend/services/llm/tools/tasting.py`
- Modify: `backend/services/llm/tools/__init__.py`
- Test: `backend/tests/test_tasting_tools.py`

**Step 1: Write the failing test**

Create `backend/tests/test_tasting_tools.py`:

```python
"""Tests for AG-UI tasting tools."""

import pytest
from datetime import datetime, timezone
from backend.services.llm.tools.tasting import (
    start_tasting_session,
    save_tasting_note,
    get_batch_tasting_notes,
)


class TestTastingTools:
    """Test AG-UI tasting tool functions."""

    @pytest.mark.asyncio
    async def test_start_tasting_session(self, db, test_batch_with_recipe):
        """start_tasting_session returns batch context for guided tasting."""
        result = await start_tasting_session(
            db=db,
            batch_id=test_batch_with_recipe.id,
            user_id="test-user"
        )
        assert result["success"] is True
        assert "batch" in result
        assert result["batch"]["id"] == test_batch_with_recipe.id
        # Should include style info if recipe has it
        assert "style_guidelines" in result or "style" in result["batch"]

    @pytest.mark.asyncio
    async def test_save_tasting_note(self, db, test_batch):
        """save_tasting_note creates a complete tasting record."""
        result = await save_tasting_note(
            db=db,
            batch_id=test_batch.id,
            appearance_score=4,
            appearance_notes="Clear golden",
            aroma_score=4,
            aroma_notes="Malty with floral hops",
            flavor_score=5,
            flavor_notes="Well balanced",
            mouthfeel_score=4,
            mouthfeel_notes="Medium body",
            overall_score=4,
            overall_notes="Excellent beer",
            serving_temp_c=4.0,
            glassware="pint",
            user_id="test-user"
        )
        assert result["success"] is True
        assert result["tasting_note"]["total_score"] == 21
        assert result["tasting_note"]["appearance_score"] == 4

    @pytest.mark.asyncio
    async def test_get_batch_tasting_notes(self, db, test_batch):
        """get_batch_tasting_notes returns all tastings for a batch."""
        # Create two tasting notes
        await save_tasting_note(
            db=db, batch_id=test_batch.id,
            appearance_score=4, aroma_score=4, flavor_score=4,
            mouthfeel_score=4, overall_score=4, user_id="test-user"
        )
        await save_tasting_note(
            db=db, batch_id=test_batch.id,
            appearance_score=5, aroma_score=5, flavor_score=5,
            mouthfeel_score=5, overall_score=5, user_id="test-user"
        )

        result = await get_batch_tasting_notes(db=db, batch_id=test_batch.id, user_id="test-user")
        assert result["count"] == 2
        # Should be ordered by date
        assert result["tasting_notes"][0]["total_score"] == 20
        assert result["tasting_notes"][1]["total_score"] == 25
```

**Step 2: Run test to verify it fails**

Run: `cd /home/ladmin/Projects/brewsignal/brewsignal-web && python -m pytest backend/tests/test_tasting_tools.py -v`

Expected: FAIL with `ImportError`

**Step 3: Create tasting tools**

Create `backend/services/llm/tools/tasting.py`:

```python
"""Tasting note tools for the AI brewing assistant."""

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.models import Batch, TastingNote, Recipe


async def start_tasting_session(
    db: AsyncSession,
    batch_id: int,
    user_id: Optional[str] = None,
) -> dict[str, Any]:
    """Start a guided tasting session for a batch.

    Returns batch context including recipe, style, and previous tastings
    to help guide the tasting interview.
    """
    result = await db.execute(
        select(Batch)
        .options(
            selectinload(Batch.recipe).selectinload(Recipe.style),
            selectinload(Batch.tasting_notes)
        )
        .where(Batch.id == batch_id)
    )
    batch = result.scalar_one_or_none()
    if not batch:
        return {"success": False, "error": f"Batch {batch_id} not found"}

    # Calculate days since packaging if packaged_at is set
    days_since_packaging = None
    if batch.packaged_at:
        days_since_packaging = (datetime.now(timezone.utc) - batch.packaged_at).days

    # Get style guidelines if available
    style_info = None
    if batch.recipe and batch.recipe.style:
        style = batch.recipe.style
        style_info = {
            "name": style.name,
            "category": style.category_name,
            "appearance": style.appearance,
            "aroma": style.aroma,
            "flavor": style.flavor,
            "mouthfeel": style.mouthfeel,
            "overall_impression": style.overall_impression,
        }

    # Get previous tasting scores for comparison
    previous_tastings = []
    for note in batch.tasting_notes:
        previous_tastings.append({
            "tasted_at": note.tasted_at.isoformat() if note.tasted_at else None,
            "total_score": note.total_score,
            "days_since_packaging": note.days_since_packaging,
        })

    return {
        "success": True,
        "batch": {
            "id": batch.id,
            "name": batch.name,
            "recipe_name": batch.recipe.name if batch.recipe else None,
            "status": batch.status,
            "measured_og": batch.measured_og,
            "measured_fg": batch.measured_fg,
            "measured_abv": batch.measured_abv,
            "packaged_at": batch.packaged_at.isoformat() if batch.packaged_at else None,
            "days_since_packaging": days_since_packaging,
        },
        "style_guidelines": style_info,
        "previous_tastings": previous_tastings,
        "tasting_count": len(previous_tastings),
    }


async def save_tasting_note(
    db: AsyncSession,
    batch_id: int,
    appearance_score: int,
    aroma_score: int,
    flavor_score: int,
    mouthfeel_score: int,
    overall_score: int,
    appearance_notes: Optional[str] = None,
    aroma_notes: Optional[str] = None,
    flavor_notes: Optional[str] = None,
    mouthfeel_notes: Optional[str] = None,
    overall_notes: Optional[str] = None,
    days_since_packaging: Optional[int] = None,
    serving_temp_c: Optional[float] = None,
    glassware: Optional[str] = None,
    to_style: Optional[bool] = None,
    style_deviation_notes: Optional[str] = None,
    ai_suggestions: Optional[str] = None,
    interview_transcript: Optional[dict] = None,
    user_id: Optional[str] = None,
) -> dict[str, Any]:
    """Save a complete tasting note for a batch."""
    # Verify batch exists
    batch_result = await db.execute(select(Batch).where(Batch.id == batch_id))
    batch = batch_result.scalar_one_or_none()
    if not batch:
        return {"success": False, "error": f"Batch {batch_id} not found"}

    # Calculate total score
    total_score = appearance_score + aroma_score + flavor_score + mouthfeel_score + overall_score

    # Auto-calculate days_since_packaging if not provided
    if days_since_packaging is None and batch.packaged_at:
        days_since_packaging = (datetime.now(timezone.utc) - batch.packaged_at).days

    note = TastingNote(
        batch_id=batch_id,
        user_id=user_id,
        tasted_at=datetime.now(timezone.utc),
        days_since_packaging=days_since_packaging,
        serving_temp_c=serving_temp_c,
        glassware=glassware,
        appearance_score=appearance_score,
        appearance_notes=appearance_notes,
        aroma_score=aroma_score,
        aroma_notes=aroma_notes,
        flavor_score=flavor_score,
        flavor_notes=flavor_notes,
        mouthfeel_score=mouthfeel_score,
        mouthfeel_notes=mouthfeel_notes,
        overall_score=overall_score,
        overall_notes=overall_notes,
        total_score=total_score,
        to_style=to_style,
        style_deviation_notes=style_deviation_notes,
        ai_suggestions=ai_suggestions,
        interview_transcript=interview_transcript,
    )
    db.add(note)
    await db.commit()
    await db.refresh(note)

    return {
        "success": True,
        "tasting_note": {
            "id": note.id,
            "batch_id": note.batch_id,
            "tasted_at": note.tasted_at.isoformat(),
            "days_since_packaging": note.days_since_packaging,
            "total_score": note.total_score,
            "appearance_score": note.appearance_score,
            "aroma_score": note.aroma_score,
            "flavor_score": note.flavor_score,
            "mouthfeel_score": note.mouthfeel_score,
            "overall_score": note.overall_score,
            "to_style": note.to_style,
        }
    }


async def get_batch_tasting_notes(
    db: AsyncSession,
    batch_id: int,
    user_id: Optional[str] = None,
) -> dict[str, Any]:
    """Get all tasting notes for a batch."""
    result = await db.execute(
        select(TastingNote)
        .where(TastingNote.batch_id == batch_id)
        .order_by(TastingNote.tasted_at)
    )
    notes = result.scalars().all()

    return {
        "count": len(notes),
        "tasting_notes": [
            {
                "id": n.id,
                "tasted_at": n.tasted_at.isoformat() if n.tasted_at else None,
                "days_since_packaging": n.days_since_packaging,
                "total_score": n.total_score,
                "appearance_score": n.appearance_score,
                "appearance_notes": n.appearance_notes,
                "aroma_score": n.aroma_score,
                "aroma_notes": n.aroma_notes,
                "flavor_score": n.flavor_score,
                "flavor_notes": n.flavor_notes,
                "mouthfeel_score": n.mouthfeel_score,
                "mouthfeel_notes": n.mouthfeel_notes,
                "overall_score": n.overall_score,
                "overall_notes": n.overall_notes,
                "to_style": n.to_style,
                "style_deviation_notes": n.style_deviation_notes,
                "ai_suggestions": n.ai_suggestions,
            }
            for n in notes
        ]
    }
```

**Step 4: Add to __init__.py**

Add imports, tool definitions, and execute_tool handlers similar to Task 5.

**Step 5: Run test to verify it passes**

Run: `cd /home/ladmin/Projects/brewsignal/brewsignal-web && python -m pytest backend/tests/test_tasting_tools.py -v`

Expected: PASS

**Step 6: Commit**

```bash
git add backend/services/llm/tools/tasting.py backend/services/llm/tools/__init__.py backend/tests/test_tasting_tools.py
git commit -m "feat(ag-ui): Add tasting note tools

- start_tasting_session: Get batch context for guided tasting
- save_tasting_note: Create complete tasting record
- get_batch_tasting_notes: Retrieve all tastings for a batch

Enables AI-guided BJCP-style tasting interviews."
```

---

## Remaining Tasks (Outlined)

### Task 8: AI Insight Generation
- Create `backend/services/llm/insight_generator.py`
- Implement prompts for each phase
- Add `regenerate_reflection_insights` tool
- Test AI summary generation

### Task 9: Search/Learning Tools
- Add `search_past_reflections` tool
- Add `search_past_tastings` tool
- Enable AI to reference past learnings

### Task 10: Frontend - Reflection Cards
- Create `ReflectionCard.svelte` component
- Add to batch detail page
- Display metrics, notes, AI summary

### Task 11: Frontend - Tasting Notes List
- Create `TastingNotesList.svelte` component
- Add to batch detail page
- Show dated entries with scores

### Task 12: Frontend - Tasting Wizard
- Create multi-step `TastingWizard.svelte`
- Steps: Context → Appearance → Aroma → Flavor → Mouthfeel → Overall
- AI suggestions inline

### Task 13: Tasting Interview Flow
- Implement conversational tasting in AG-UI
- Style-specific prompts
- Save interview transcript

---

## Running All Tests

After completing all tasks:

```bash
cd /home/ladmin/Projects/brewsignal/brewsignal-web
python -m pytest backend/tests/test_batch_reflection*.py backend/tests/test_tasting*.py backend/tests/test_reflection*.py -v
```

Expected: All tests PASS
