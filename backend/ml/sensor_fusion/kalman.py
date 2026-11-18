"""Kalman filter for Tilt hydrometer readings.

Two independent level+trend (constant-velocity) filters, one for SG and one
for temperature. Settings come from measured Tilt noise (tilt_ui-0hic):
- exact CV discretisation, Q = q * [[dt^3/3, dt^2/2], [dt^2/2, dt]]
- fixed measurement noise (RSSI does not predict Tilt noise; residual std is
  flat across RSSI bins, so the old RSSI multiplier only slowed the filter)
- 3-sigma Huber gating: an innovation beyond the gate scales the whole
  innovation variance by |z|/gate, so a single bubble spike moves the
  estimate at most about gate sigmas. After
  STEP_RUN gated innovations in a row with the same sign the change is
  treated as real (a step, not a spike): the filter restarts at the new
  level with an unknown rate.
"""

import numpy as np


STEP_RUN = 3


class _CV:
    """Level + trend filter for one signal. Time unit is hours."""

    def __init__(
        self, level: float, q: float, r: float, p0_level: float, p0_rate: float, gate: float
    ):
        if not (np.isfinite([q, r, p0_level, p0_rate, gate]).all()
                and r > 0 and q >= 0 and p0_level > 0 and p0_rate >= 0):
            raise ValueError("Kalman noise must be finite and positive")
        self.q = q
        self.r = r
        self.p0_level = p0_level
        self.p0_rate = p0_rate
        self.gate = gate  # <= 0 disables gating
        self.x = np.array([level, 0.0])
        self.P = np.diag([p0_level, p0_rate ** 2])
        # Seed from the first finite reading, not a default (cold start used
        # to show a 50+ C filtered temperature for hours; tilt_ui-89af).
        self.seeded = False
        self._run = 0  # signed count of same-sign gated innovations

    def seed(self, level: float, wide: bool, r: float | None = None) -> None:
        """Start from one value. wide=True for a stored value (load_history
        seeds from the last reading, which may be a spike, so the next
        readings must win); wide=False for a live measurement.
        A non-finite value gives NaN output until a finite reading arrives."""
        self._run = 0
        level = np.nan if level is None else level
        self.seeded = bool(np.isfinite(level))
        p0 = self.p0_level if wide or not self.seeded else (r or self.r)
        self.x = np.array([float(level) if self.seeded else np.nan, 0.0])
        self.P = np.diag([p0, self.p0_rate ** 2])

    def step(self, z: float, dt: float, resolution: float = 0.0) -> None:
        """resolution: the sensor's reporting step; rounding adds step^2/12
        to the measurement variance (a standard Tilt's 0.001 SG ticks are 5x
        the Tilt Pro noise the base R was measured on)."""
        z = np.nan if z is None else z  # HTTP devices may send no temperature
        if not np.isfinite(resolution):
            resolution = 0.0
        r = self.r + resolution ** 2 / 12
        if not self.seeded:
            self.seed(z, wide=False, r=r)
            return
        if not np.isfinite(dt):
            return
        # Tiny floor (3.6 s): readings stamped with the same time must not
        # shrink the variance to zero and lock the gate
        dt = max(float(dt), 1e-3)
        F = np.array([[1.0, dt], [0.0, 1.0]])
        Q = self.q * np.array([[dt ** 3 / 3, dt ** 2 / 2], [dt ** 2 / 2, dt]])
        x = F @ self.x
        P = F @ self.P @ F.T + Q
        if not np.isfinite(z):
            # Missing value: time still passes, skip only the correction
            self.x, self.P = x, P
            return

        nu = z - x[0]
        S = P[0, 0] + r
        zn = abs(nu) / np.sqrt(S)
        if self.gate > 0 and zn > self.gate:
            sign = 1 if nu > 0 else -1
            self._run = self._run + sign if self._run * sign > 0 else sign
            if abs(self._run) >= STEP_RUN:
                # The model broke (Tilt moved, krausen fell, rate changed in a
                # gap): restart at the new level with an unknown rate (0, wide
                # variance) so the next readings set it. Keeping the old rate
                # left a stale slope after gaps.
                # ponytail: a 3-reading burst of spikes also counts as a step;
                # raise STEP_RUN if bursts show up in real data. Ramps faster
                # than ~6 C/h (or ~6 pt/h) restart every 3 readings and the
                # rate saw-tooths; sizing the rate variance to the jump fixed
                # that but turned spike bursts into big false rates.
                self.x = np.array([z, 0.0])
                self.P = np.diag([r, self.p0_rate ** 2])
                self._run = 0
                return
            # Huber: scale the whole innovation variance by zn/gate, so a spike
            # moves the estimate at most gate sigmas even when P >> R (after
            # a gap or right after seeding)
            r = S * zn / self.gate - P[0, 0]
        else:
            self._run = 0

        K = P[:, 0] / (P[0, 0] + r)
        self.x = x + K * nu
        self.P = P - np.outer(K, P[0, :])


class TiltKalmanFilter:
    """Kalman filter for Tilt SG and temperature (Celsius).

    State per signal: [value, rate per hour].
    """

    def __init__(
        self,
        initial_sg: float = 1.050,
        initial_temp: float = 20.0,
        process_noise_sg: float = 1e-9,
        process_noise_temp: float = 0.05,
        measurement_noise_sg: float = 4e-8,
        measurement_noise_temp: float = 0.0225,
        gate: float = 3.0,
    ):
        """Initialize the filter.

        Args:
            initial_sg: Starting SG; replaced by the first measurement unless
                reset() seeded the filter explicitly
            initial_temp: Starting temperature (C); same rule as initial_sg
            process_noise_sg: q for SG, units SG^2/h^3
            process_noise_temp: q for temperature, units C^2/h^3
            measurement_noise_sg: SG measurement variance (sigma 2e-4)
            measurement_noise_temp: temperature measurement variance (sigma 0.15 C)
            gate: innovation gate in standard deviations; <= 0 disables it
        """
        self.sg = _CV(initial_sg, process_noise_sg, measurement_noise_sg, 1e-4, 1e-3, gate)
        self.temp = _CV(initial_temp, process_noise_temp, measurement_noise_temp, 1.0, 1.0, gate)

    def update(
        self,
        sg: float,
        temp: float,
        rssi: float | None = None,
        dt_hours: float = 1 / 60,
        sg_resolution: float = 0.0,
        temp_resolution: float = 0.0,
    ) -> dict:
        """Process a new reading and return filtered values.

        Args:
            sg: Calibrated specific gravity
            temp: Calibrated temperature (C)
            rssi: Ignored; kept so callers need not change
            dt_hours: Time since last reading in hours
            sg_resolution, temp_resolution: sensor reporting step (0 = fine)

        Returns:
            sg_filtered, sg_rate (SG/h), temp_filtered, temp_rate (C/h), confidence
        """
        self.sg.step(sg, dt_hours, sg_resolution)
        self.temp.step(temp, dt_hours, temp_resolution)
        return self.get_state()

    def _calculate_confidence(self) -> float:
        """Map SG standard deviation to 0-1 (1e-4 SG -> 0.99)."""
        return float(np.clip(1.0 - np.sqrt(self.sg.P[0, 0]) * 100, 0, 1))

    def get_state(self) -> dict:
        """Current filter state without processing a reading."""
        return {
            "sg_filtered": float(self.sg.x[0]),
            "sg_rate": float(self.sg.x[1]),
            "temp_filtered": float(self.temp.x[0]),
            "temp_rate": float(self.temp.x[1]),
            "confidence": self._calculate_confidence(),
        }

    def reset(self, sg: float, temp: float) -> None:
        """Reset filter state for a new batch or after a history reload."""
        self.sg.seed(sg, wide=True)
        self.temp.seed(temp, wide=True)
