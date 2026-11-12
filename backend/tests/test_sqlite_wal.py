"""tilt_ui-en7s: SQLite connections use WAL and wait for locks instead of failing."""
import pytest
from sqlalchemy import text

from backend.database import DATABASE_URL, engine


@pytest.mark.asyncio
async def test_sqlite_connections_use_wal_and_busy_timeout():
    if not DATABASE_URL.startswith("sqlite"):
        pytest.skip("SQLite only")
    async with engine.connect() as conn:
        mode = (await conn.execute(text("PRAGMA journal_mode"))).scalar()
        timeout = (await conn.execute(text("PRAGMA busy_timeout"))).scalar()
    assert mode == "wal"
    assert timeout == 30000
