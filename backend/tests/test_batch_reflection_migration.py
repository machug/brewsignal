"""Tests for BatchReflection migration."""

import pytest
from sqlalchemy import text


class TestBatchReflectionMigration:
    """Test batch_reflections table migration."""

    @pytest.mark.asyncio
    async def test_batch_reflections_table_exists(self, test_db):
        """batch_reflections table is created."""
        result = await test_db.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='batch_reflections'"
        ))
        table = result.scalar()
        assert table == "batch_reflections"

    @pytest.mark.asyncio
    async def test_batch_reflections_has_columns(self, test_db):
        """batch_reflections table has all required columns."""
        result = await test_db.execute(text("PRAGMA table_info(batch_reflections)"))
        columns = {row[1] for row in result.fetchall()}
        required = {
            "id", "batch_id", "user_id", "phase", "created_at", "updated_at",
            "metrics", "what_went_well", "what_went_wrong", "lessons_learned",
            "next_time_changes", "ai_summary", "ai_generated_at", "ai_model_version"
        }
        assert required.issubset(columns), f"Missing columns: {required - columns}"

    @pytest.mark.asyncio
    async def test_batch_reflections_indexes(self, test_db):
        """batch_reflections table has required indexes."""
        result = await test_db.execute(text("PRAGMA index_list(batch_reflections)"))
        indexes = {row[1] for row in result.fetchall()}
        # Should have user_id index and batch_phase composite index
        assert any("user_id" in idx for idx in indexes)
