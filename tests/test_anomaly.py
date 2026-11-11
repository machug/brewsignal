"""Tests for fermentation anomaly detection (tilt_ui-zbhm)."""

import numpy as np

from backend.ml.anomaly.detector import FermentationAnomalyDetector

STEP = 5 / 60  # 5-minute storage cadence


def logistic_curve(hours, og=1.056, fg=1.014, lag=14.0, peak=0.0007):
    """Logistic fermentation: lag, then up to ``peak`` SG/h, then FG."""
    k = 4 * peak / (og - fg)
    return fg + (og - fg) / (1 + np.exp(k * (hours - lag - (og - fg) / (2 * peak))))


def feed(detector, hours, sgs):
    return [detector.check_reading(float(s), float(h)) for h, s in zip(hours, sgs)]


def test_normal_fermentation_raises_no_flags():
    """Lag, peak and slowdown with bubble noise: zero anomalies (old rules: ~82%)."""
    rng = np.random.default_rng(1)
    hours = np.arange(0, 168, STEP)
    sgs = logistic_curve(hours) + rng.normal(0, 1.2e-4, len(hours))
    results = feed(FermentationAnomalyDetector(), hours, sgs)
    assert not any(r["is_anomaly"] for r in results)


def test_lag_phase_flat_gravity_is_not_flagged():
    hours = np.arange(0, 14, STEP)
    results = feed(FermentationAnomalyDetector(), hours, np.full(len(hours), 1.050))
    assert not any(r["is_anomaly"] for r in results)


def test_single_outlier_is_not_a_step():
    hours = np.arange(0, 6, STEP)
    sgs = np.full(len(hours), 1.030)
    sgs[40] += 0.005
    results = feed(FermentationAnomalyDetector(), hours, sgs)
    assert not any(r["is_anomaly"] for r in results)


def test_step_change_flagged_once_per_event():
    """Hydrometer lifted: -2.5 pt level shift is flagged once, about 30 min later."""
    hours = np.arange(0, 6, STEP)
    sgs = np.where(hours < 3, 1.0205, 1.0180)
    results = feed(FermentationAnomalyDetector(), hours, sgs)
    flagged = [(h, r["reason"]) for h, r in zip(hours, results) if r["is_anomaly"]]
    assert len(flagged) == 1
    assert flagged[0][1] == "step_change_down"
    assert 3.0 < flagged[0][0] <= 3.6


def test_dry_hop_step_up_flagged():
    hours = np.arange(0, 8, STEP)
    sgs = logistic_curve(hours + 150) + np.where(hours >= 4, 0.0015, 0.0)
    results = feed(FermentationAnomalyDetector(), hours, sgs)
    assert [r["reason"] for r in results if r["is_anomaly"]] == ["step_change_up"]


def test_slope_12h_needs_full_window_then_matches_trend():
    det = FermentationAnomalyDetector()
    hours = np.arange(0, 13, STEP)
    results = feed(det, hours, 1.050 - 0.0002 * hours)
    assert results[0]["sg_slope_12h"] is None
    assert results[-1]["sg_slope_12h"] is not None
    assert abs(results[-1]["sg_slope_12h"] - (-0.0002)) < 1e-7


def test_history_is_bounded():
    det = FermentationAnomalyDetector()
    feed(det, np.arange(0, 100, STEP), np.full(int(100 / STEP), 1.040))
    assert det.time_history[-1] - det.time_history[0] <= 13.0 + STEP


def test_reset_clears_history():
    det = FermentationAnomalyDetector()
    feed(det, np.arange(0, 13, STEP), np.full(int(13 / STEP), 1.040))
    det.reset()
    assert det.check_reading(1.050, 0.0)["sg_slope_12h"] is None
