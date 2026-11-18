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
        assert abs(outs[11] - 1.016) < 1e-3
        assert min(outs) > 1.016 - 1e-3

    def test_bad_seed_recovers(self):
        """load_history() seeds from the last stored reading; if it was a 2 point
        spike, good readings must take over within a few readings."""
        kf = TiltKalmanFilter()
        kf.reset(sg=1.022, temp=18.0)
        for _ in range(6):  # 30 min at 5 min readings
            out = kf.update(sg=1.020, temp=18.0, dt_hours=5 / 60)
        assert abs(out["sg_filtered"] - 1.020) < 3e-4

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
