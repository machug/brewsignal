"""Tests for Kalman filter sensor fusion."""

import pytest
from backend.ml.sensor_fusion.kalman import TiltKalmanFilter


class TestTiltKalmanFilter:
    """Tests for the Tilt Kalman filter."""

    def test_initialization(self):
        """Filter initializes with provided values."""
        kf = TiltKalmanFilter(initial_sg=1.050, initial_temp=68.0)

        assert kf.get_state()["sg_filtered"] == pytest.approx(1.050, abs=0.001)
        assert kf.get_state()["temp_filtered"] == pytest.approx(68.0, abs=0.1)

    def test_filters_noisy_readings(self, sample_readings):
        """Filter smooths out noisy readings."""
        kf = TiltKalmanFilter(initial_sg=1.050, initial_temp=68.0)

        results = []
        for reading in sample_readings:
            result = kf.update(
                sg=reading["sg"],
                temp=reading["temp"],
                rssi=reading["rssi"],
                dt_hours=reading["dt_hours"] if reading["dt_hours"] > 0 else 1/60,
            )
            results.append(result)

        # The anomalous reading (1.055) should be dampened
        sg_values = [r["sg_filtered"] for r in results]

        # Filtered values should be smoother (smaller std dev)
        raw_sg = [r["sg"] for r in sample_readings]
        import numpy as np
        assert np.std(sg_values) < np.std(raw_sg)

    def test_rssi_does_not_change_output(self):
        """Tilt noise does not depend on RSSI (tilt_ui-0hic), so RSSI is ignored."""
        a, b = TiltKalmanFilter(), TiltKalmanFilter()
        for i in range(10):
            ra = a.update(sg=1.050 - i * 1e-4, temp=19.0, rssi=-45, dt_hours=0.25)
            rb = b.update(sg=1.050 - i * 1e-4, temp=19.0, rssi=-95, dt_hours=0.25)
        assert ra == rb

    @pytest.mark.parametrize("dt", [5 / 60, 0.25])
    def test_single_spike_is_gated(self, dt):
        """A +5 point bubble spike on a flat trace moves the estimate under 2.5e-4;
        without the gate it moves it more."""
        moves = {}
        for gate in (3.0, 0):
            kf = TiltKalmanFilter(gate=gate)
            for _ in range(50):
                kf.update(sg=1.020, temp=19.0, dt_hours=dt)
            moves[gate] = kf.update(sg=1.025, temp=19.0, dt_hours=dt)["sg_filtered"] - 1.020
        assert abs(moves[3.0]) < 2.5e-4
        assert abs(moves[0]) > 2 * abs(moves[3.0])

    def test_real_step_is_followed(self):
        """A sudden 8 point drop that stays (batch 16, 16 Nov) is followed within
        1 h at 5 min readings, and does not overshoot by more than 1 point."""
        kf = TiltKalmanFilter()
        for _ in range(100):
            kf.update(sg=1.024, temp=18.0, dt_hours=5 / 60)
        outs = [kf.update(sg=1.016, temp=18.0, dt_hours=5 / 60)["sg_filtered"] for _ in range(36)]
        assert abs(outs[2] - 1.016) < 3e-4  # step accepted on the 3rd reading
        assert abs(outs[11] - 1.016) < 1e-3
        assert min(outs) > 1.016 - 1e-3

    def test_bad_seed_recovers(self):
        """load_history() seeds from the last stored reading; if it was a 2 point
        spike, good readings must take over within a few readings."""
        kf = TiltKalmanFilter()
        kf.reset(sg=1.022, temp=18.0)
        for _ in range(2):
            out = kf.update(sg=1.020, temp=18.0, dt_hours=5 / 60)
        assert abs(out["sg_filtered"] - 1.020) < 1e-4

    def test_nan_and_negative_dt_do_not_poison_state(self):
        kf = TiltKalmanFilter()
        for _ in range(10):
            kf.update(sg=1.020, temp=19.0, dt_hours=5 / 60)
        kf.update(sg=float("nan"), temp=19.0, dt_hours=5 / 60)
        kf.update(sg=1.020, temp=19.0, dt_hours=-1.0)
        out = kf.update(sg=1.020, temp=19.0, dt_hours=float("nan"))
        assert out["sg_filtered"] == pytest.approx(1.020, abs=1e-4)
        assert out["temp_filtered"] == pytest.approx(19.0, abs=0.1)
        assert 0 <= out["confidence"] <= 1

    def test_tracks_active_fermentation_without_lag(self):
        """Old filter lagged ~15 min on a 1 pt/h drop; new one stays within 1 pt."""
        kf = TiltKalmanFilter()
        for i in range(48):  # 12 h at 15 min, -1 pt/h
            out = kf.update(sg=1.060 - i * 0.00025, temp=19.0, dt_hours=0.25)
        assert abs(out["sg_filtered"] - (1.060 - 47 * 0.00025)) < 1e-4
        assert out["sg_rate"] == pytest.approx(-0.001, rel=0.1)

    def test_temperature_follows_step_quickly(self):
        """Old temp filter lagged ~2 h; a 2 C change should be followed within 1 h."""
        kf = TiltKalmanFilter()
        for _ in range(20):
            kf.update(sg=1.020, temp=18.0, dt_hours=0.25)
        for _ in range(4):
            out = kf.update(sg=1.020, temp=20.0, dt_hours=0.25)
        assert abs(out["temp_filtered"] - 20.0) < 0.3

    def test_recovers_after_gap(self):
        """Fermenting at -1 pt/h, then a 6 h gap in which it slowed to the end:
        the old filter carried the stale rate and erred by ~18e-4."""
        kf = TiltKalmanFilter()
        for i in range(36):  # 3 h at 5 min
            kf.update(sg=1.040 - i * 1e-3 / 12, temp=19.0, dt_hours=5 / 60)
        sg_after_gap = 1.040 - 35 * 1e-3 / 12 - 0.002  # only 2 pt in 6 h, not 6
        outs = [kf.update(sg=sg_after_gap, temp=19.0, dt_hours=dt)["sg_filtered"]
                for dt in (6.0, 5 / 60, 5 / 60, 5 / 60)]
        assert abs(outs[-1] - sg_after_gap) < 3e-4
        for _ in range(12):  # and stays near it: the stale slope fades
            out = kf.update(sg=sg_after_gap, temp=19.0, dt_hours=5 / 60)
        # q=1e-9 keeps the rate stiff, so ~1.6e-4 (under one Tilt step) lingers
        # for a few hours; the old filter was 18e-4 off here.
        assert abs(out["sg_filtered"] - sg_after_gap) < 2e-4

    def test_returns_sg_rate(self, sample_readings):
        """Filter estimates rate of SG change."""
        kf = TiltKalmanFilter(initial_sg=1.050, initial_temp=68.0)

        for reading in sample_readings:
            result = kf.update(
                sg=reading["sg"],
                temp=reading["temp"],
                rssi=reading["rssi"],
                dt_hours=max(reading["dt_hours"], 1/60),
            )

        # After several readings showing decline, rate should be negative
        assert result["sg_rate"] < 0

    def test_reset(self):
        """Reset reinitializes the filter state."""
        kf = TiltKalmanFilter(initial_sg=1.050, initial_temp=68.0)

        # Process some readings
        kf.update(sg=1.040, temp=70.0, rssi=-60, dt_hours=1.0)
        kf.update(sg=1.035, temp=71.0, rssi=-60, dt_hours=1.0)

        # Reset to new batch
        kf.reset(sg=1.060, temp=65.0)

        state = kf.get_state()
        assert state["sg_filtered"] == pytest.approx(1.060, abs=0.001)
        assert state["temp_filtered"] == pytest.approx(65.0, abs=0.1)


def test_pipeline_passes_config_to_filter():
    """MLConfig kalman_* values must reach the filter."""
    from backend.ml.config import MLConfig
    from backend.ml.pipeline import MLPipeline

    cfg = MLConfig(kalman_measurement_noise_sg=9e-8, kalman_process_noise_temp=0.07)
    kf = MLPipeline(config=cfg).kalman_filter
    assert kf.sg.r == 9e-8
    assert kf.temp.q == 0.07


def test_first_reading_is_one_measurement_not_gospel():
    """A spike right after the first reading is still gated, gives no false
    rate, and the first stored row has a normal confidence."""
    kf = TiltKalmanFilter()
    first = kf.update(sg=1.020, temp=19.0, dt_hours=5 / 60)
    assert first["confidence"] > 0.9
    out = kf.update(sg=1.025, temp=19.0, dt_hours=5 / 60)
    assert abs(out["sg_filtered"] - 1.020) < 1e-3  # gate caps it near 3 sigma
    for _ in range(3):
        out = kf.update(sg=1.020, temp=19.0, dt_hours=5 / 60)
    assert abs(out["sg_filtered"] - 1.020) < 3e-4


def test_nan_on_seed_waits_for_finite_reading():
    kf = TiltKalmanFilter()
    kf.update(sg=float("nan"), temp=float("nan"), dt_hours=5 / 60)
    out = kf.update(sg=1.030, temp=18.0, dt_hours=5 / 60)
    assert out["sg_filtered"] == pytest.approx(1.030, abs=1e-6)
    kf.reset(sg=float("nan"), temp=18.0)  # load_history ending on a NaN
    out = kf.update(sg=1.029, temp=18.0, dt_hours=5 / 60)
    assert out["sg_filtered"] == pytest.approx(1.029, abs=1e-6)


def test_nan_reading_still_advances_time():
    """A gap ending in a NaN must not leave the next valid reading 6 points behind."""
    kf = TiltKalmanFilter()
    for i in range(36):
        kf.update(sg=1.040 - i * 1e-3 / 12, temp=19.0, dt_hours=5 / 60)
    kf.update(sg=float("nan"), temp=19.0, dt_hours=6.0)
    target = 1.040 - 35 * 1e-3 / 12 - 0.006
    out = kf.update(sg=target, temp=19.0, dt_hours=5 / 60)
    assert abs(out["sg_filtered"] - target) < 5e-4


def test_step_gives_no_big_false_rate():
    kf = TiltKalmanFilter()
    for _ in range(100):
        kf.update(sg=1.024, temp=18.0, dt_hours=5 / 60)
    for _ in range(4):
        out = kf.update(sg=1.019, temp=18.0, dt_hours=5 / 60)
    assert abs(out["sg_rate"]) < 2e-4  # under 0.2 pt/h, not a big false rate


def test_config_rejects_non_positive_noise():
    from pydantic import ValidationError
    from backend.ml.config import MLConfig
    with pytest.raises(ValidationError):
        MLConfig(kalman_measurement_noise_sg=0)


def _flat(kf, sg=1.024, temp=18.0, n=100):
    for _ in range(n):
        kf.update(sg=sg, temp=temp, dt_hours=5 / 60)


def test_alternating_spikes_never_become_a_step():
    kf = TiltKalmanFilter()
    _flat(kf)
    for i in range(6):
        out = kf.update(sg=1.024 + (0.005 if i % 2 == 0 else -0.005), temp=18.0, dt_hours=5 / 60)
    assert abs(out["sg_filtered"] - 1.024) < 1e-3
    assert abs(out["sg_rate"]) < 1e-3


def test_three_spike_burst_is_a_known_limit():
    """Three +5 pt readings in a row count as a step (ponytail limit); the line
    comes back within 3 good readings and no false rate stays."""
    kf = TiltKalmanFilter()
    _flat(kf)
    for _ in range(3):
        kf.update(sg=1.029, temp=18.0, dt_hours=5 / 60)
    for _ in range(3):
        out = kf.update(sg=1.024, temp=18.0, dt_hours=5 / 60)
    assert abs(out["sg_filtered"] - 1.024) < 3e-4
    assert abs(out["sg_rate"]) < 2e-4


def test_temperature_step_gives_no_false_rate():
    kf = TiltKalmanFilter()
    _flat(kf, temp=18.0)
    for _ in range(4):
        out = kf.update(sg=1.024, temp=23.0, dt_hours=5 / 60)
    assert abs(out["temp_filtered"] - 23.0) < 0.3
    assert abs(out["temp_rate"]) < 0.5


def test_early_spike_gives_no_false_rate():
    kf = TiltKalmanFilter()
    kf.update(sg=1.020, temp=19.0, dt_hours=5 / 60)
    kf.update(sg=1.025, temp=19.0, dt_hours=5 / 60)
    for _ in range(12):  # 1 h
        out = kf.update(sg=1.020, temp=19.0, dt_hours=5 / 60)
    assert abs(out["sg_rate"]) < 5e-4  # measured: 1.7 pt/h peak, 0.45 at 1 h
    assert abs(out["sg_filtered"] - 1.020) < 2e-4


def test_fast_ramp_rate_is_learned():
    """Crash cooling at 6 C/h: the rate converges instead of freezing."""
    kf = TiltKalmanFilter()
    _flat(kf, temp=18.0)
    for i in range(1, 25):
        out = kf.update(sg=1.024, temp=18.0 - 6.0 * i / 12, dt_hours=5 / 60)
    assert out["temp_rate"] == pytest.approx(-6.0, rel=0.15)
    assert abs(out["temp_filtered"] - (18.0 - 12.0)) < 0.3


def test_noise_must_be_positive():
    with pytest.raises(ValueError):
        TiltKalmanFilter(measurement_noise_sg=0)


def test_angle_sensors_get_their_own_sg_noise():
    """iSpindel/GravityMon are noisier than a Tilt; a 1e-3 noisy flat trace must
    not keep tripping the step rule."""
    import numpy as np
    from backend.ml.pipeline_manager import MLPipelineManager

    mgr = MLPipelineManager()
    rng = np.random.default_rng(1)
    worst = 0.0
    for i in range(2000):
        out = mgr.process_reading(device_id="ISP", batch_id=1, sg=1.020 + rng.normal(0, 1e-3),
                                  temp=19.0, rssi=-70, time_hours=i * 5 / 60, device_type="ispindel")
        if i > 50:
            worst = max(worst, abs(out["sg_filtered"] - 1.020))
    assert mgr.pipelines["ISP"].kalman_filter.sg.r == mgr.config.kalman_measurement_noise_sg_angle
    assert worst < 1e-3

    mgr.process_reading(device_id="ISP", batch_id=1, sg=1.020, temp=19.0, rssi=-70,
                        time_hours=200.0, device_type="tilt")
    assert mgr.pipelines["ISP"].kalman_filter.sg.r == mgr.config.kalman_measurement_noise_sg


def test_standard_tilt_ticks_do_not_trip_steps():
    """A standard Tilt reports 0.001 SG: a slow 0.2 pt/h drop arrives as
    single ticks. With the resolution passed in, no tick counts as a step
    and the rate stays close to the truth."""
    kf = TiltKalmanFilter()
    runs = []
    for i in range(12 * 48):  # 48 h at 5 min
        true = 1.030 - 0.0002 * i / 12
        kf.update(sg=round(true, 3), temp=19.0, dt_hours=5 / 60, sg_resolution=0.001)
        runs.append(abs(kf.sg._run))
    out = kf.get_state()
    assert max(runs) < 2  # a step needs 3 gated readings in a row
    assert out["sg_rate"] == pytest.approx(-0.0002, abs=1e-4)
    assert abs(out["sg_filtered"] - true) < 6e-4


def test_spike_after_gap_is_still_bounded():
    """After a 12 h gap P >> R; the gate must scale the whole innovation
    variance or a single 85 C glitch drags the temperature far up."""
    kf = TiltKalmanFilter()
    for _ in range(50):
        kf.update(sg=1.020, temp=19.0, dt_hours=5 / 60)
    out = kf.update(sg=1.020, temp=85.0, dt_hours=12.0)
    # 12 h without data: temp sigma is ~6 C, so the gate allows up to ~3 sigma
    # (it was 44-85 C when only R was scaled)
    assert out["temp_filtered"] < 40.0


def test_non_finite_seed_outputs_nan():
    import math
    kf = TiltKalmanFilter()
    assert math.isnan(kf.update(sg=float("inf"), temp=19.0, dt_hours=5 / 60)["sg_filtered"])
    kf.update(sg=1.030, temp=19.0, dt_hours=5 / 60)
    kf.reset(sg=float("nan"), temp=19.0)
    assert math.isnan(kf.get_state()["sg_filtered"])


def test_infinite_noise_rejected():
    from pydantic import ValidationError
    from backend.ml.config import MLConfig
    with pytest.raises(ValueError):
        TiltKalmanFilter(measurement_noise_sg=float("inf"))
    with pytest.raises(ValidationError):
        MLConfig(kalman_measurement_noise_sg=float("inf"))


@pytest.mark.parametrize("sg,temp_f,expected", [
    (1.0488, 68.6, 0.0001),  # Tilt Pro
    (1.048, 68.0, 0.001),    # standard Tilt
    (1.048, 68.6, 0.0001),   # Pro landing on a whole SG step
])
def test_tilt_reading_resolution(sg, temp_f, expected):
    from datetime import datetime, timezone
    from backend.scanner import TiltReading
    r = TiltReading(color="BLUE", mac="x", temp_f=temp_f, sg=sg, rssi=-60,
                    timestamp=datetime.now(timezone.utc))
    assert r.resolution[0] == expected


def test_reload_sets_angle_noise_from_readings():
    """reload_from_database picks the SG noise from the batch's last reading."""
    import asyncio
    from datetime import datetime, timezone
    from unittest.mock import AsyncMock, MagicMock
    from backend.ml.pipeline_manager import MLPipelineManager

    from backend.models import Reading
    rd = MagicMock(spec=Reading, sg_calibrated=1.020, temp_calibrated=19.0, device_type="ispindel",
                   timestamp=datetime(2026, 11, 1, tzinfo=timezone.utc))
    res = MagicMock()
    res.scalars.return_value.all.return_value = [rd]
    res.scalar_one_or_none.return_value = datetime(2026, 11, 1, tzinfo=timezone.utc)
    db = MagicMock(execute=AsyncMock(return_value=res))
    mgr = MLPipelineManager()
    asyncio.run(mgr.reload_from_database("ISP", 1, db))
    assert mgr.pipelines["ISP"].kalman_filter.sg.r == mgr.config.kalman_measurement_noise_sg_angle


def test_none_temperature_does_not_break_sg():
    kf = TiltKalmanFilter()
    kf.update(sg=1.020, temp=19.0, dt_hours=5 / 60)
    out = kf.update(sg=1.019, temp=None, dt_hours=5 / 60)
    assert out["sg_filtered"] < 1.020


def test_manager_turns_nan_into_none():
    from backend.ml.pipeline_manager import MLPipelineManager
    out = MLPipelineManager().process_reading(device_id="X", batch_id=1, sg=float("nan"),
                                              temp=19.0, rssi=-60, time_hours=0.0)
    assert out.get("sg_filtered") is None  # skipped, not NaN


def test_sub_minute_readings_give_true_rate():
    """No 1-minute dt floor: 30 s readings falling 1 pt/h report 1 pt/h."""
    from backend.ml.pipeline import MLPipeline
    p = MLPipeline()
    for i in range(240):  # 2 h at 30 s
        out = p.process_reading(sg=1.040 - 0.001 * i / 120, temp=19.0, rssi=-60, time_hours=i / 120)
    assert out["kalman"]["sg_rate"] == pytest.approx(-0.001, rel=0.15)


@pytest.mark.parametrize("sg,temp_f,expected", [
    (1.0488, 68.6, (0.0001, 0.1 * 5 / 9)),
    (1.048, 68.0, (0.001, 5 / 9)),
])
def test_tilt_resolution_both_steps(sg, temp_f, expected):
    from backend.scanner import tilt_resolution
    assert tilt_resolution(sg, temp_f) == pytest.approx(expected)


def test_http_tilt_passes_resolution():
    from backend.ingest.base import HydrometerReading, TemperatureUnit
    from backend.services.ingest_manager import IngestManager
    from datetime import datetime, timezone
    r = HydrometerReading(device_id="BLUE", device_type="tilt", timestamp=datetime.now(timezone.utc),
                          gravity=1.048, temperature=20.0,
                          gravity_raw=1.048, temperature_raw=68.0,
                          temperature_unit=TemperatureUnit.FAHRENHEIT)
    assert IngestManager._sensor_resolution(r) == {"sg_resolution": 0.001, "temp_resolution": pytest.approx(5 / 9)}
    r.device_type = "ispindel"
    assert IngestManager._sensor_resolution(r) == {}


def test_missing_gravity_is_skipped_by_pipeline():
    """A reading with no gravity must not reach prediction history (fits
    failed on a None) and the next reading's dt spans the gap."""
    from backend.ml.pipeline import MLPipeline
    p = MLPipeline()
    for i in range(12):
        p.process_reading(sg=1.040 - i * 1e-4, temp=19.0, rssi=-60, time_hours=i / 12)
    out = p.process_reading(sg=None, temp=19.0, rssi=-60, time_hours=1.0)
    assert out["kalman"] is None
    assert None not in p.sg_history and len(p.sg_history) == 12


@pytest.mark.parametrize("sg,temp_f,unit,expected", [
    (1.048, None, "f", 0.001),     # no temperature: SG alone
    (1.0483, None, "f", 0.0001),
    (1.048, 20.56, "c", 0.001),    # Celsius: SG alone, not fooled by decimals
    (float("nan"), 68.0, "f", 0.001),
])
def test_http_tilt_resolution_edge_cases(sg, temp_f, unit, expected):
    from datetime import datetime, timezone
    from backend.ingest.base import HydrometerReading, TemperatureUnit
    from backend.services.ingest_manager import IngestManager
    r = HydrometerReading(device_id="BLUE", device_type="tilt", timestamp=datetime.now(timezone.utc),
                          gravity_raw=sg, temperature_raw=temp_f,
                          temperature_unit=TemperatureUnit.FAHRENHEIT if unit == "f" else TemperatureUnit.CELSIUS)
    assert IngestManager._sensor_resolution(r)["sg_resolution"] == expected


def test_same_timestamp_readings_do_not_lock_filter():
    kf = TiltKalmanFilter()
    for _ in range(500):
        kf.update(sg=1.020, temp=19.0, dt_hours=0.0)
    for _ in range(12):
        out = kf.update(sg=1.019, temp=19.0, dt_hours=5 / 60)
    assert abs(out["sg_filtered"] - 1.019) < 3e-4


def test_fast_crash_cool_is_learned_without_sawtooth():
    """-6 C/h at 5 min (fast fridge crash): the rate is learned and stays.
    Faster ramps saw-tooth: known limit, see kalman.py."""
    kf = TiltKalmanFilter()
    for _ in range(50):
        kf.update(sg=1.010, temp=20.0, dt_hours=5 / 60)
    rates = []
    for i in range(1, 25):
        rates.append(kf.update(sg=1.010, temp=20.0 - 6.0 * i / 12, dt_hours=5 / 60)["temp_rate"])
    assert all(r == pytest.approx(-6.0, rel=0.1) for r in rates[-12:])


def test_nonfinite_resolution_and_gate():
    kf = TiltKalmanFilter()
    kf.update(sg=1.020, temp=19.0, dt_hours=5 / 60)
    out = kf.update(sg=1.020, temp=19.0, dt_hours=5 / 60, sg_resolution=float("nan"))
    assert out["sg_filtered"] == pytest.approx(1.020, abs=1e-6)
    with pytest.raises(ValueError):
        TiltKalmanFilter(gate=float("nan"))
