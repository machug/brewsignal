"""Tests for AG-UI reflection tools."""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Batch
from backend.services.llm.tools.reflections import (
    create_batch_reflection,
    get_batch_reflections,
    update_batch_reflection,
)


@pytest_asyncio.fixture
async def test_batch(test_db: AsyncSession) -> Batch:
    """Create a test batch for reflection tests."""
    batch = Batch(name="Test IPA", status="fermenting", user_id="test-user")
    test_db.add(batch)
    await test_db.commit()
    await test_db.refresh(batch)
    return batch


class TestReflectionTools:
    """Test AG-UI reflection tool functions."""

    @pytest.mark.asyncio
    async def test_create_batch_reflection(self, test_db: AsyncSession, test_batch: Batch):
        """create_batch_reflection creates and returns reflection."""
        result = await create_batch_reflection(
            db=test_db,
            batch_id=test_batch.id,
            phase="brew_day",
            what_went_well="Great efficiency",
            user_id="test-user"
        )
        assert result["success"] is True
        assert result["reflection"]["phase"] == "brew_day"
        assert result["reflection"]["what_went_well"] == "Great efficiency"

    @pytest.mark.asyncio
    async def test_create_batch_reflection_with_metrics(self, test_db: AsyncSession, test_batch: Batch):
        """create_batch_reflection supports metrics dict."""
        metrics = {"efficiency_actual": 72.5, "efficiency_expected": 75.0}
        result = await create_batch_reflection(
            db=test_db,
            batch_id=test_batch.id,
            phase="brew_day",
            metrics=metrics,
            user_id="test-user"
        )
        assert result["success"] is True
        assert result["reflection"]["metrics"] == metrics

    @pytest.mark.asyncio
    async def test_create_batch_reflection_batch_not_found(self, test_db: AsyncSession):
        """create_batch_reflection returns error for non-existent batch."""
        result = await create_batch_reflection(
            db=test_db,
            batch_id=99999,
            phase="brew_day",
            user_id="test-user"
        )
        assert result["success"] is False
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_create_batch_reflection_duplicate_phase(self, test_db: AsyncSession, test_batch: Batch):
        """create_batch_reflection rejects duplicate phase for same batch."""
        await create_batch_reflection(
            db=test_db,
            batch_id=test_batch.id,
            phase="brew_day",
            user_id="test-user"
        )
        result = await create_batch_reflection(
            db=test_db,
            batch_id=test_batch.id,
            phase="brew_day",
            user_id="test-user"
        )
        assert result["success"] is False
        assert "already exists" in result["error"]

    @pytest.mark.asyncio
    async def test_get_batch_reflections(self, test_db: AsyncSession, test_batch: Batch):
        """get_batch_reflections returns all reflections for a batch."""
        await create_batch_reflection(
            db=test_db, batch_id=test_batch.id, phase="brew_day", user_id="test-user"
        )
        await create_batch_reflection(
            db=test_db, batch_id=test_batch.id, phase="fermentation", user_id="test-user"
        )

        result = await get_batch_reflections(db=test_db, batch_id=test_batch.id, user_id="test-user")
        assert result["count"] == 2
        phases = [r["phase"] for r in result["reflections"]]
        assert "brew_day" in phases
        assert "fermentation" in phases

    @pytest.mark.asyncio
    async def test_get_batch_reflections_filter_by_phase(self, test_db: AsyncSession, test_batch: Batch):
        """get_batch_reflections can filter by phase."""
        await create_batch_reflection(
            db=test_db, batch_id=test_batch.id, phase="brew_day", user_id="test-user"
        )
        await create_batch_reflection(
            db=test_db, batch_id=test_batch.id, phase="fermentation", user_id="test-user"
        )

        result = await get_batch_reflections(
            db=test_db, batch_id=test_batch.id, phase="fermentation", user_id="test-user"
        )
        assert result["count"] == 1
        assert result["reflections"][0]["phase"] == "fermentation"

    @pytest.mark.asyncio
    async def test_get_batch_reflections_empty(self, test_db: AsyncSession, test_batch: Batch):
        """get_batch_reflections returns empty list for batch with no reflections."""
        result = await get_batch_reflections(db=test_db, batch_id=test_batch.id, user_id="test-user")
        assert result["count"] == 0
        assert result["reflections"] == []

    @pytest.mark.asyncio
    async def test_update_batch_reflection(self, test_db: AsyncSession, test_batch: Batch):
        """update_batch_reflection updates reflection fields."""
        create_result = await create_batch_reflection(
            db=test_db, batch_id=test_batch.id, phase="brew_day", user_id="test-user"
        )
        reflection_id = create_result["reflection"]["id"]

        result = await update_batch_reflection(
            db=test_db,
            reflection_id=reflection_id,
            lessons_learned="Preheat mash tun",
            user_id="test-user"
        )
        assert result["success"] is True
        assert result["reflection"]["lessons_learned"] == "Preheat mash tun"

    @pytest.mark.asyncio
    async def test_update_batch_reflection_multiple_fields(self, test_db: AsyncSession, test_batch: Batch):
        """update_batch_reflection can update multiple fields."""
        create_result = await create_batch_reflection(
            db=test_db, batch_id=test_batch.id, phase="brew_day", user_id="test-user"
        )
        reflection_id = create_result["reflection"]["id"]

        result = await update_batch_reflection(
            db=test_db,
            reflection_id=reflection_id,
            what_went_well="Good efficiency",
            what_went_wrong="Boil over",
            lessons_learned="Watch the kettle",
            user_id="test-user"
        )
        assert result["success"] is True
        assert result["reflection"]["what_went_well"] == "Good efficiency"
        assert result["reflection"]["what_went_wrong"] == "Boil over"
        assert result["reflection"]["lessons_learned"] == "Watch the kettle"

    @pytest.mark.asyncio
    async def test_update_batch_reflection_not_found(self, test_db: AsyncSession):
        """update_batch_reflection returns error for non-existent reflection."""
        result = await update_batch_reflection(
            db=test_db,
            reflection_id=99999,
            lessons_learned="Something",
            user_id="test-user"
        )
        assert result["success"] is False
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_update_batch_reflection_preserves_existing_fields(
        self, test_db: AsyncSession, test_batch: Batch
    ):
        """update_batch_reflection preserves fields not being updated."""
        create_result = await create_batch_reflection(
            db=test_db,
            batch_id=test_batch.id,
            phase="brew_day",
            what_went_well="Good start",
            user_id="test-user"
        )
        reflection_id = create_result["reflection"]["id"]

        result = await update_batch_reflection(
            db=test_db,
            reflection_id=reflection_id,
            lessons_learned="Learn more",
            user_id="test-user"
        )
        assert result["success"] is True
        # Original field should be preserved
        assert result["reflection"]["what_went_well"] == "Good start"
        # New field should be set
        assert result["reflection"]["lessons_learned"] == "Learn more"
