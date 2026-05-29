"""Tests for run_deferred_backfills (tilt_ui-h0j).

The two recipe backfills (style_id, color_srm) were moved off the startup
critical path into a background task so a slow sweep can't blow the platform
healthcheck window (Railway's 30s). This wrapper must:

  1. run both migrations, in order (style_id before color_srm);
  2. never propagate an exception — a failed backfill must not take the app
     down, it just retries on the next boot.

The migrations themselves are covered by test_backfill_recipe_style_id.py and
test_backfill_recipe_color_srm.py; here we only verify the wrapper's contract.
"""

import backend.migrations.backfill_recipe_color_srm as color_mod
import backend.migrations.backfill_recipe_style_id as style_mod
import pytest

from backend.database import run_deferred_backfills


class TestRunDeferredBackfills:
    @pytest.mark.asyncio
    async def test_runs_both_migrations_in_order(self, monkeypatch):
        calls = []

        async def fake_style(engine):
            calls.append("style")

        async def fake_color(engine):
            calls.append("color")

        monkeypatch.setattr(style_mod, "migrate_backfill_recipe_style_id", fake_style)
        monkeypatch.setattr(color_mod, "migrate_backfill_recipe_color_srm", fake_color)

        await run_deferred_backfills()

        assert calls == ["style", "color"]

    @pytest.mark.asyncio
    async def test_swallows_migration_error(self, monkeypatch):
        async def boom(engine):
            raise RuntimeError("backfill exploded")

        ran_after = []

        async def fake_color(engine):
            ran_after.append("color")

        monkeypatch.setattr(style_mod, "migrate_backfill_recipe_style_id", boom)
        monkeypatch.setattr(color_mod, "migrate_backfill_recipe_color_srm", fake_color)

        # Must not raise — the app stays up even if a backfill fails.
        await run_deferred_backfills()

        # style_id blew up, so color_srm never ran this boot; it retries next boot.
        assert ran_after == []
