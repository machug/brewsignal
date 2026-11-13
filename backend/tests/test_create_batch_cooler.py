"""tilt_ui-xrq5.2: create_batch must save cooler_entity_id."""

import pytest


@pytest.mark.asyncio
async def test_create_batch_saves_cooler_entity(client):
    r = await client.post("/api/batches", json={
        "name": "Cooler Test", "temp_target": 19.0, "heater_entity_id": "switch.h", "cooler_entity_id": "switch.c",
    })
    assert r.status_code == 201
    assert r.json()["cooler_entity_id"] == "switch.c"
    got = await client.get(f"/api/batches/{r.json()['id']}")
    assert got.json()["cooler_entity_id"] == "switch.c"
