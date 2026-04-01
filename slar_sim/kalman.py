from __future__ import annotations

import numpy as np

from .config import SimulationConfig


class KalmanFilter6D:
    """Constant-velocity Kalman filter from Section 3."""

    def __init__(
        self,
        config: SimulationConfig,
        initial_position: np.ndarray,
        initial_velocity: np.ndarray | None = None,
    ) -> None:
        self.config = config
        velocity = np.zeros(3, dtype=float) if initial_velocity is None else np.asarray(initial_velocity, dtype=float)

        self.state = np.zeros(6, dtype=float)
        self.state[:3] = np.asarray(initial_position, dtype=float)
        self.state[3:] = velocity

        dt = config.dt_s
        identity3 = np.eye(3)

        # Eq. (5): constant-velocity state transition.
        self.F = np.block(
            [
                [identity3, dt * identity3],
                [np.zeros((3, 3)), identity3],
            ]
        )

        # Section 3.2: Q = sigma_q^2 I6.
        self.Q = (config.kalman_process_noise_std_m ** 2) * np.eye(6)

        # Section 3.3: H = [I3 03].
        self.H = np.hstack([identity3, np.zeros((3, 3))])

        # Section 3.3: R = sigma_r^2 I3.
        self.R = (config.kalman_measurement_noise_std_m ** 2) * np.eye(3)
        self.I = np.eye(6)

        self.covariance = config.initial_state_covariance * np.eye(6)

    @property
    def position(self) -> np.ndarray:
        return self.state[:3].copy()

    @property
    def velocity(self) -> np.ndarray:
        return self.state[3:].copy()

    def predict(self) -> None:
        # Eq. (6): predicted mean.
        self.state = self.F @ self.state
        # Eq. (7): predicted covariance.
        self.covariance = self.F @ self.covariance @ self.F.T + self.Q

    def update(self, measurement: np.ndarray) -> None:
        measurement = np.asarray(measurement, dtype=float)

        # Eq. (8): innovation covariance.
        innovation_covariance = self.H @ self.covariance @ self.H.T + self.R
        # Eq. (9): Kalman gain.
        kalman_gain = self.covariance @ self.H.T @ np.linalg.inv(innovation_covariance)
        innovation = measurement - (self.H @ self.state)

        # Eq. (10): posterior mean.
        self.state = self.state + kalman_gain @ innovation
        # Eq. (11): posterior covariance.
        self.covariance = (self.I - kalman_gain @ self.H) @ self.covariance

    def step(self, measurement: np.ndarray) -> None:
        self.predict()
        self.update(measurement)

    def project_position(self, horizon_step: int) -> np.ndarray:
        # Eq. (12): linear future position projection.
        return self.position + (horizon_step * self.config.dt_s * self.velocity)
