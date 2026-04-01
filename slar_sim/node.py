from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
import math
from typing import Deque

import numpy as np

from .config import SimulationConfig
from .kalman import KalmanFilter6D
from .packet import Packet


@dataclass
class UAVNode:
    node_id: int
    position: np.ndarray
    velocity: np.ndarray
    kalman_filter: KalmanFilter6D
    queue: Deque[Packet] = field(default_factory=deque)
    last_measurement: np.ndarray | None = None

    @classmethod
    def from_state(
        cls,
        node_id: int,
        position: np.ndarray,
        velocity: np.ndarray,
        config: SimulationConfig,
    ) -> "UAVNode":
        position = np.asarray(position, dtype=float)
        velocity = np.asarray(velocity, dtype=float)
        kalman_filter = KalmanFilter6D(config=config, initial_position=position, initial_velocity=velocity)
        return cls(node_id=node_id, position=position.copy(), velocity=velocity.copy(), kalman_filter=kalman_filter)

    @property
    def estimated_position(self) -> np.ndarray:
        return self.kalman_filter.position

    @property
    def estimated_velocity(self) -> np.ndarray:
        return self.kalman_filter.velocity

    def enqueue(self, packet: Packet) -> None:
        self.queue.append(packet)

    def advance_true_state(self, rng: np.random.Generator, config: SimulationConfig) -> None:
        acceleration = rng.normal(0.0, config.mobility_accel_std_mps2, size=3)
        self.velocity = self.velocity + (acceleration * config.dt_s)

        speed = np.linalg.norm(self.velocity)
        if speed < config.min_speed_mps:
            self.velocity = self._rescale_velocity(config.min_speed_mps, rng)
        elif speed > config.max_speed_mps:
            self.velocity = self.velocity * (config.max_speed_mps / speed)

        next_position = self.position + (self.velocity * config.dt_s)

        # Reflective boundaries keep the swarm inside the simulation volume.
        bounded = np.asarray(config.world_bounds_m, dtype=float)
        for axis in range(3):
            if next_position[axis] < 0.0 or next_position[axis] > bounded[axis]:
                self.velocity[axis] *= -1.0
                next_position[axis] = np.clip(next_position[axis], 0.0, bounded[axis])

        self.position = next_position

    def sense_and_update_filter(self, rng: np.random.Generator, config: SimulationConfig) -> None:
        measurement = self.position + rng.normal(0.0, config.kalman_measurement_noise_std_m, size=3)
        self.last_measurement = measurement
        self.kalman_filter.step(measurement)

    def _rescale_velocity(self, target_speed: float, rng: np.random.Generator) -> np.ndarray:
        norm = np.linalg.norm(self.velocity)
        if math.isclose(norm, 0.0):
            direction = rng.normal(0.0, 1.0, size=3)
            direction_norm = np.linalg.norm(direction)
            if math.isclose(direction_norm, 0.0):
                direction = np.array([1.0, 0.0, 0.0], dtype=float)
            else:
                direction = direction / direction_norm
            return direction * target_speed
        return self.velocity * (target_speed / norm)
