"""Tests for run_deferred_backfills (tilt_ui-h0j).

The recipe style_id backfill runs off the startup critical path so a slow sweep
can't blow the platform healthcheck window (Railway's 30s). The wrapper must run
it and never propagate an exception: a failed backfill retries on the next boot.
The migration itself is covered by test_backfill_recipe_style_id.py.
"""

import backend.migrations.backfill_recipe_style_id as style_mod
import pytest

from backend.database import run_deferred_backfills


class TestRunDeferredBackfills:
    @pytest.mark.asyncio
    async def test_runs_style_migration(self, monkeypatch):
        calls = []

        async def fake_style(engine):
            calls.append("style")

        monkeypatch.setattr(style_mod, "migrate_backfill_recipe_style_id", fake_style)
        await run_deferred_backfills()
        assert calls == ["style"]

    @pytest.mark.asyncio
    async def test_swallows_migration_error(self, monkeypatch):
        async def boom(engine):
            raise RuntimeError("backfill exploded")

        monkeypatch.setattr(style_mod, "migrate_backfill_recipe_style_id", boom)
        await run_deferred_backfills()  # must not raise
