"""One prediction path (tilt_ui-3kbr): predict_batch is what the API, the assistant and the chart show."""

import math
from datetime import datetime, timedelta, timezone

import pytest

from backend.ml.pipeline import MLPipeline
from backend.ml.pipeline_manager import MLPipelineManager
from backend.models import Batch, Reading, Recipe


def test_live_history_holds_the_measurement_not_the_filter_output():
    pipe = MLPipeline()
    for i, sg in enumerate((1.050, 1.049, 1.047)):
        pipe.process_reading(sg=sg, temp=19.0, rssi=-60, time_hours=i / 12)
    assert pipe.sg_history == [1.050, 1.049, 1.047]


@pytest.mark.asyncio
async def test_predict_batch_headline_is_the_blended_estimate(test_db):
    recipe = Recipe(name="APA", og=1.050, fg=1.011)
    test_db.add(recipe)
    await test_db.flush()
    start = datetime.now(timezone.utc) - timedelta(hours=72)
    batch = Batch(name="APA", status="fermenting", device_id="BLUE", recipe_id=recipe.id, start_time=start)
    test_db.add(batch)
    await test_db.flush()
    for h in range(72):  # exponential decay towards 1.011
        sg = 1.011 + 0.039 * math.exp(-0.03 * h)
        test_db.add(Reading(batch_id=batch.id, device_id="BLUE", sg_calibrated=sg,
                            temp_calibrated=19.0, timestamp=start + timedelta(hours=h)))
    await test_db.flush()
    batch.recipe = recipe

    mgr = MLPipelineManager()
    out = await mgr.predict_batch(test_db, batch)

    raw = mgr.get_device_state("BLUE", expected_fg=1.011, batch_id=batch.id)["predictions"]
    assert out["available"] and out["hours_to_completion"] == raw["blended_hours_to_completion"]
    assert out["curve_hours_to_completion"] == raw["hours_to_completion"]
    assert out["num_readings"] == 72


@pytest.mark.asyncio
async def test_predict_batch_without_device(test_db):
    batch = Batch(name="B", status="fermenting")
    test_db.add(batch)
    await test_db.flush()
    batch.recipe = None
    assert await MLPipelineManager().predict_batch(test_db, batch) == {"available": False, "error": "No device linked"}
