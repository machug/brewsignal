"""Tests for BatchReflection model."""

import pytest
from datetime import datetime, timezone

from backend.models import BatchReflection, BatchReflectionCreate, BatchReflectionResponse


class TestBatchReflectionModel:
    """Test BatchReflection SQLAlchemy model."""

    def test_batch_reflection_has_required_fields(self):
        """BatchReflection model has all required fields."""
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
