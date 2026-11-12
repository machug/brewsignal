"""Assistant read-only temperature control tool (tilt_ui-y67b)."""

from datetime import datetime, timedelta, timezone

import pytest

from backend.models import Batch, ControlEvent
from backend.services.llm.tools.fermentation import get_temperature_control


@pytest.mark.asyncio
async def test_reports_target_band_and_recent_switches(test_db):
    batch = Batch(name="APA", status="fermenting", heater_entity_id="switch.beer_heater",
                  temp_target=20.0, temp_hysteresis=0.6)
    test_db.add(batch)
    await test_db.flush()
    now = datetime.now(timezone.utc)
    for i, action in enumerate(["heat_off", "heat_on"]):
        test_db.add(ControlEvent(batch_id=batch.id, action=action, wort_temp=19.2 + i * 0.6,
                                 target_temp=20.0, timestamp=now - timedelta(minutes=10 * (2 - i))))
    await test_db.commit()

    out = await get_temperature_control(test_db, batch.id)

    assert out["found"] is True
    assert out["target_temp"] == 20.0 and out["hysteresis"] == 0.6
    assert out["heater_entity"] == "switch.beer_heater"
    assert [e["action"] for e in out["recent_switches"]] == ["heat_on", "heat_off"]  # newest first


@pytest.mark.asyncio
async def test_unknown_batch(test_db):
    assert (await get_temperature_control(test_db, 9999))["found"] is False
