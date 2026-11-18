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

    def test_single_spike_is_gated(self):
        """A +5 point bubble spike on a flat trace moves the estimate under 2.5e-4."""
        kf = TiltKalmanFilter()
        for _ in range(50):
            kf.update(sg=1.020, temp=19.0, dt_hours=0.25)
        out = kf.update(sg=1.025, temp=19.0, dt_hours=0.25)
        assert abs(out["sg_filtered"] - 1.020) < 2.5e-4

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
        """Fermenting at -0.5 pt/h, then a 6 h gap: the first reading after it lands close."""
        kf = TiltKalmanFilter()
        for i in range(40):
            kf.update(sg=1.050 - i * 0.000125, temp=19.0, dt_hours=0.25)
        sg_after_gap = 1.050 - 39 * 0.000125 - 6 * 0.0005
        out = kf.update(sg=sg_after_gap, temp=19.0, dt_hours=6.0)
        assert abs(out["sg_filtered"] - sg_after_gap) < 1e-4

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
