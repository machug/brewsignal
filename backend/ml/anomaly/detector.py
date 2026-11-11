"""Anomaly detection for fermentation data (tilt_ui-zbhm).

Two explainable rules, tuned in the Nov 2026 research (sensing-anomaly.md):

- Step change: the last N raw readings all sit more than ``step_threshold``
  above (or all below) the line fitted to the readings just before them. That
  is a persistent level shift (dry hop, hydrometer lifted or moved), not
  bubble noise, which flips sign from reading to reading. Flagged once per
  event.
- 12 h slope: least-squares slope of the filtered SG over the trailing
  ``slope_window_hours``. Reported, not flagged here: whether a flat slope is
  a stall depends on the batch OG/FG, which alert_service knows.

The old rules (instant rate thresholds, OG = first filtered reading, no
lag-phase guard) flagged ~82% of normal readings and were removed.
"""

from typing import Optional

import numpy as np


class FermentationAnomalyDetector:
    """Rule-based step-change detector plus trailing-slope estimate."""

    def __init__(
        self,
        slope_window_hours: float = 12.0,
        step_threshold: float = 0.001,  # 1 gravity point
        step_count: int = 6,  # ~30 min at the 5-min storage cadence
        baseline_hours: float = 2.0,
        min_baseline_readings: int = 6,
    ):
        self.slope_window_hours = slope_window_hours
        self.step_threshold = step_threshold
        self.step_count = step_count
        self.baseline_hours = baseline_hours
        self.min_baseline_readings = min_baseline_readings
        self.reset()

    def reset(self) -> None:
        """Reset detector state for a new batch."""
        self.time_history: list[float] = []
        self.sg_history: list[float] = []  # filtered SG
        self.raw_history: list[float] = []
        self._step_active = False

    def check_reading(
        self,
        sg: float,
        time_hours: float,
        raw_sg: Optional[float] = None,
    ) -> dict:
        """Check one reading.

        Args:
            sg: Filtered specific gravity
            time_hours: Hours since fermentation start
            raw_sg: Unfiltered SG for step detection (defaults to ``sg``)

        Returns:
            is_anomaly, reason ("normal" / "step_change_up" / "step_change_down"),
            sg_slope_12h (SG/hour, None until the window is covered).
        """
        self.time_history.append(time_hours)
        self.sg_history.append(sg)
        self.raw_history.append(sg if raw_sg is None else raw_sg)
        self._trim()

        reason = self._check_step()
        return {
            "is_anomaly": reason != "normal",
            "reason": reason,
            "sg_slope_12h": self._slope_12h(),
        }

    def _trim(self) -> None:
        """Keep only what the longest window needs (bounded memory)."""
        keep_hours = max(self.slope_window_hours, self.baseline_hours) + 1.0
        cutoff = self.time_history[-1] - keep_hours
        drop = 0
        while drop < len(self.time_history) and self.time_history[drop] < cutoff:
            drop += 1
        if drop:
            del self.time_history[:drop]
            del self.sg_history[:drop]
            del self.raw_history[:drop]

    def _slope_12h(self) -> Optional[float]:
        t = np.array(self.time_history)
        if len(t) < 3 or t[-1] - t[0] < self.slope_window_hours:
            return None
        window = t >= t[-1] - self.slope_window_hours
        return float(np.polyfit(t[window], np.array(self.sg_history)[window], 1)[0])

    def _check_step(self) -> str:
        n = self.step_count
        if len(self.raw_history) < n + self.min_baseline_readings:
            return "normal"
        t = np.array(self.time_history)
        z = np.array(self.raw_history)
        recent_t, recent_z = t[-n:], z[-n:]
        base = (t[:-n] >= recent_t[0] - self.baseline_hours)
        base_t, base_z = t[:-n][base], z[:-n][base]
        if len(base_t) < self.min_baseline_readings or base_t[-1] - base_t[0] <= 0:
            return "normal"
        slope, intercept = np.polyfit(base_t, base_z, 1)
        resid = recent_z - (slope * recent_t + intercept)

        if np.all(resid > self.step_threshold):
            direction = "step_change_up"
        elif np.all(resid < -self.step_threshold):
            direction = "step_change_down"
        else:
            self._step_active = False
            return "normal"
        if self._step_active:
            return "normal"  # already flagged this event
        self._step_active = True
        return direction
