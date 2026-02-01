"""Tests for extended TastingNote model fields."""

import pytest
from sqlalchemy import text


class TestTastingNoteExtended:
    """Test extended TastingNote fields."""

    @pytest.mark.asyncio
    async def test_tasting_note_has_extended_fields(self, test_db):
        """TastingNote table has new extended columns."""
        result = await test_db.execute(text("PRAGMA table_info(tasting_notes)"))
        columns = {row[1] for row in result.fetchall()}
        new_fields = {
            "user_id", "days_since_packaging", "serving_temp_c", "glassware",
            "total_score", "to_style", "style_deviation_notes",
            "ai_suggestions", "interview_transcript"
        }
        assert new_fields.issubset(columns), f"Missing columns: {new_fields - columns}"
