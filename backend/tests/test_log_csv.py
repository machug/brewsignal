"""Regression: /log.csv referenced a removed Tilt model and crashed."""

from sqlalchemy.ext.asyncio import async_sessionmaker

import backend.main as main_module


async def test_log_csv_export_streams(client, test_db, monkeypatch):
    # download_log() uses main.async_session_factory directly (not get_db);
    # bind it to the test database's engine.
    monkeypatch.setattr(
        main_module, "async_session_factory", async_sessionmaker(test_db.bind, expire_on_commit=False)
    )
    r = await client.get("/log.csv")
    assert r.status_code == 200
    assert r.text.splitlines()[0].startswith("timestamp")
