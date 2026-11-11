"""Regression: /log.csv referenced a removed Tilt model and crashed."""
async def test_log_csv_export_streams(client):
    r = await client.get("/log.csv")
    assert r.status_code == 200
    assert r.text.splitlines()[0].startswith("timestamp")
