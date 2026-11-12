"""ML state must not leak across batches or cold starts (tilt_ui-89af)."""

from backend.ml.pipeline_manager import MLPipelineManager
from backend.ml.sensor_fusion.kalman import TiltKalmanFilter


def _feed(mgr, batch_id, sg, temp, n=20, t0=0.0):
    out = None
    for i in range(n):
        out = mgr.process_reading(device_id="BLUE", batch_id=batch_id, sg=sg, temp=temp,
                                  rssi=-60, time_hours=t0 + i * 5 / 60)
    return out


def test_kalman_cold_start_seeds_from_first_reading():
    """Used to start at 68 (F) against C inputs and show a hot filtered temp for hours."""
    out = TiltKalmanFilter().update(sg=1.048, temp=19.4, rssi=-60, dt_hours=5 / 60)
    assert abs(out["temp_filtered"] - 19.4) < 0.1
    assert abs(out["sg_filtered"] - 1.048) < 0.0005


def test_new_batch_on_same_device_starts_fresh():
    mgr = MLPipelineManager()
    _feed(mgr, batch_id=15, sg=1.012, temp=4.0)  # old batch: finished, cold crashed
    out = _feed(mgr, batch_id=16, sg=1.050, temp=19.0, n=1)  # first reading of the new batch
    assert abs(out["sg_filtered"] - 1.050) < 0.0005
    assert abs(out["temp_filtered"] - 19.0) < 0.1
    assert len(mgr.pipelines["BLUE"].sg_history) == 1


def test_same_batch_keeps_state():
    mgr = MLPipelineManager()
    _feed(mgr, batch_id=16, sg=1.050, temp=19.0)
    _feed(mgr, batch_id=16, sg=1.050, temp=19.0, n=1, t0=2.0)
    assert len(mgr.pipelines["BLUE"].sg_history) == 21


def test_device_state_for_other_batch_is_none():
    """Batch page must not show another batch's predictions; None triggers a reload."""
    mgr = MLPipelineManager()
    _feed(mgr, batch_id=16, sg=1.050, temp=19.0)
    assert mgr.get_device_state("BLUE", batch_id=15) is None
    assert mgr.get_device_state("BLUE", batch_id=16) is not None
