"""Tests for AG-UI tasting tools."""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Batch
from backend.services.llm.tools.tasting import (
    start_tasting_session,
    save_tasting_note,
    get_batch_tasting_notes,
)


@pytest_asyncio.fixture
async def test_batch(test_db: AsyncSession) -> Batch:
    """Create a test batch for tasting tool tests."""
    batch = Batch(name="Test IPA", status="fermenting", user_id="test-user")
    test_db.add(batch)
    await test_db.commit()
    await test_db.refresh(batch)
    return batch


class TestTastingTools:
    """Test AG-UI tasting tool functions."""

    @pytest.mark.asyncio
    async def test_start_tasting_session(self, test_db: AsyncSession, test_batch: Batch):
        """start_tasting_session returns batch context for guided tasting."""
        result = await start_tasting_session(
            db=test_db,
            batch_id=test_batch.id,
            user_id="test-user"
        )
        assert result["success"] is True
        assert "batch" in result
        assert result["batch"]["id"] == test_batch.id

    @pytest.mark.asyncio
    async def test_start_tasting_session_batch_not_found(self, test_db: AsyncSession):
        """start_tasting_session returns error for non-existent batch."""
        result = await start_tasting_session(
            db=test_db,
            batch_id=99999,
            user_id="test-user"
        )
        assert result["success"] is False
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_save_tasting_note(self, test_db: AsyncSession, test_batch: Batch):
        """save_tasting_note creates a complete tasting record."""
        result = await save_tasting_note(
            db=test_db,
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
    async def test_save_tasting_note_minimal(self, test_db: AsyncSession, test_batch: Batch):
        """save_tasting_note works with only required fields."""
        result = await save_tasting_note(
            db=test_db,
            batch_id=test_batch.id,
            appearance_score=3,
            aroma_score=3,
            flavor_score=3,
            mouthfeel_score=3,
            overall_score=3,
            user_id="test-user"
        )
        assert result["success"] is True
        assert result["tasting_note"]["total_score"] == 15

    @pytest.mark.asyncio
    async def test_save_tasting_note_batch_not_found(self, test_db: AsyncSession):
        """save_tasting_note returns error for non-existent batch."""
        result = await save_tasting_note(
            db=test_db,
            batch_id=99999,
            appearance_score=4,
            aroma_score=4,
            flavor_score=4,
            mouthfeel_score=4,
            overall_score=4,
            user_id="test-user"
        )
        assert result["success"] is False
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_save_tasting_note_with_ai_fields(self, test_db: AsyncSession, test_batch: Batch):
        """save_tasting_note supports AI-assisted fields."""
        result = await save_tasting_note(
            db=test_db,
            batch_id=test_batch.id,
            appearance_score=4,
            aroma_score=4,
            flavor_score=4,
            mouthfeel_score=4,
            overall_score=4,
            ai_suggestions="Try colder serving temperature",
            interview_transcript={"q1": "How does it look?", "a1": "Clear and golden"},
            user_id="test-user"
        )
        assert result["success"] is True
        assert result["tasting_note"]["total_score"] == 20

    @pytest.mark.asyncio
    async def test_get_batch_tasting_notes(self, test_db: AsyncSession, test_batch: Batch):
        """get_batch_tasting_notes returns all tastings for a batch."""
        await save_tasting_note(
            db=test_db, batch_id=test_batch.id,
            appearance_score=4, aroma_score=4, flavor_score=4,
            mouthfeel_score=4, overall_score=4, user_id="test-user"
        )
        await save_tasting_note(
            db=test_db, batch_id=test_batch.id,
            appearance_score=5, aroma_score=5, flavor_score=5,
            mouthfeel_score=5, overall_score=5, user_id="test-user"
        )

        result = await get_batch_tasting_notes(db=test_db, batch_id=test_batch.id, user_id="test-user")
        assert result["count"] == 2

    @pytest.mark.asyncio
    async def test_get_batch_tasting_notes_empty(self, test_db: AsyncSession, test_batch: Batch):
        """get_batch_tasting_notes returns empty list for batch with no tastings."""
        result = await get_batch_tasting_notes(db=test_db, batch_id=test_batch.id, user_id="test-user")
        assert result["count"] == 0
        assert result["tasting_notes"] == []

    @pytest.mark.asyncio
    async def test_get_batch_tasting_notes_includes_details(self, test_db: AsyncSession, test_batch: Batch):
        """get_batch_tasting_notes returns full tasting details."""
        await save_tasting_note(
            db=test_db, batch_id=test_batch.id,
            appearance_score=4, appearance_notes="Clear golden",
            aroma_score=4, aroma_notes="Hoppy",
            flavor_score=5, flavor_notes="Balanced",
            mouthfeel_score=4, mouthfeel_notes="Medium body",
            overall_score=4, overall_notes="Great beer",
            user_id="test-user"
        )

        result = await get_batch_tasting_notes(db=test_db, batch_id=test_batch.id, user_id="test-user")
        assert result["count"] == 1
        note = result["tasting_notes"][0]
        assert note["appearance_notes"] == "Clear golden"
        assert note["aroma_notes"] == "Hoppy"
        assert note["flavor_notes"] == "Balanced"
        assert note["mouthfeel_notes"] == "Medium body"
        assert note["overall_notes"] == "Great beer"
