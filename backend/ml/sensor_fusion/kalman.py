"""Kalman filter for Tilt hydrometer readings.

Two independent level+trend (constant-velocity) filters, one for SG and one
for temperature. Settings come from measured Tilt noise (tilt_ui-0hic):
- exact CV discretisation, Q = q * [[dt^3/3, dt^2/2], [dt^2/2, dt]]
- fixed measurement noise (RSSI does not predict Tilt noise; residual std is
  flat across RSSI bins, so the old RSSI multiplier only slowed the filter)
- 3-sigma Huber gating: an innovation beyond the gate inflates R by
  |z|/gate, so a single bubble spike moves the estimate far less.
"""

import numpy as np


class _CV:
    """Level + trend filter for one signal. Time unit is hours."""

    def __init__(self, level: float, q: float, r: float, p0_rate: float, gate: float):
        self.q = q
        self.r = r
        self.p0_rate = p0_rate
        self.gate = gate
        self.seed(level)

    def seed(self, level: float) -> None:
        self.x = np.array([level, 0.0])
        self.P = np.diag([self.r, self.p0_rate ** 2])

    def step(self, z: float, dt: float) -> None:
        F = np.array([[1.0, dt], [0.0, 1.0]])
        Q = self.q * np.array([[dt ** 3 / 3, dt ** 2 / 2], [dt ** 2 / 2, dt]])
        x = F @ self.x
        P = F @ self.P @ F.T + Q

        nu = z - x[0]
        r = self.r
        zn = abs(nu) / np.sqrt(P[0, 0] + r)
        if zn > self.gate:
            r *= zn / self.gate

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
            gate: innovation gate in standard deviations
        """
        self.sg = _CV(initial_sg, process_noise_sg, measurement_noise_sg, 1e-3, gate)
        self.temp = _CV(initial_temp, process_noise_temp, measurement_noise_temp, 1.0, gate)
        # Seed from the first reading, not a default (cold start used to show
        # a 50+ C filtered temperature for hours; tilt_ui-89af).
        self._seeded = False

    def update(
        self,
        sg: float,
        temp: float,
        rssi: float | None = None,
        dt_hours: float = 1 / 60,
    ) -> dict:
        """Process a new reading and return filtered values.

        Args:
            sg: Calibrated specific gravity
            temp: Calibrated temperature (C)
            rssi: Ignored; kept so callers need not change
            dt_hours: Time since last reading in hours

        Returns:
            sg_filtered, sg_rate (SG/h), temp_filtered, temp_rate (C/h), confidence
        """
        if not self._seeded:
            self.sg.seed(sg)
            self.temp.seed(temp)
            self._seeded = True
        else:
            self.sg.step(sg, dt_hours)
            self.temp.step(temp, dt_hours)
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
        self.sg.seed(sg)
        self.temp.seed(temp)
        self._seeded = True
