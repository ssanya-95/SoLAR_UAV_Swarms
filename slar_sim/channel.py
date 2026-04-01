from __future__ import annotations

import math

import numpy as np
from scipy.stats import ncx2

from .config import SimulationConfig


class ChannelModel:
    """Stochastic channel model from Section 2."""

    def __init__(self, config: SimulationConfig, num_nodes: int, rng: np.random.Generator) -> None:
        self.config = config
        self.num_nodes = num_nodes
        self.rng = rng
        self.shadowing_db = np.zeros((num_nodes, num_nodes), dtype=float)
        self._initialize_shadowing()

    def _initialize_shadowing(self) -> None:
        upper = np.triu(
            self.rng.normal(0.0, self.config.shadowing_std_db, size=(self.num_nodes, self.num_nodes)),
            k=1,
        )
        self.shadowing_db = upper + upper.T

    def step_shadowing(self) -> None:
        # Section 2.1 requires temporally correlated log-normal shadowing.
        rho = self.config.shadowing_correlation
        innovation_std = self.config.shadowing_std_db * math.sqrt(1.0 - (rho ** 2))
        innovation = np.triu(
            self.rng.normal(0.0, innovation_std, size=(self.num_nodes, self.num_nodes)),
            k=1,
        )
        previous = np.triu(self.shadowing_db, k=1)
        upper = (rho * previous) + innovation
        self.shadowing_db = upper + upper.T

    def distance_matrix(self, positions: np.ndarray) -> np.ndarray:
        deltas = positions[:, None, :] - positions[None, :, :]
        return np.linalg.norm(deltas, axis=-1)

    def adjacency_matrix(self, distances: np.ndarray) -> np.ndarray:
        adjacency = distances <= self.config.communication_range_m
        np.fill_diagonal(adjacency, False)
        return adjacency

    def snr_db_matrix(self, distances: np.ndarray) -> np.ndarray:
        clipped_distances = np.maximum(distances, 1.0)

        # Eq. (1): log-distance path-loss with temporally correlated shadowing.
        snr_db = (
            self.config.p_tx_dbm
            - self.config.pl0_db
            - (10.0 * self.config.path_loss_exponent * np.log10(clipped_distances))
            - self.shadowing_db
            - self.config.noise_floor_dbm
        )
        np.fill_diagonal(snr_db, 0.0)
        return snr_db

    def link_success_probability_matrix(self, distances: np.ndarray) -> np.ndarray:
        snr_db = self.snr_db_matrix(distances)
        snr_linear = np.power(10.0, snr_db / 10.0)

        # Eq. (2): Q1(a, b) = P[chi'^2_2(a^2) > b^2].
        a_squared = 2.0 * self.config.rician_k_linear
        b_squared = (
            2.0
            * self.config.gamma_threshold_linear
            * (self.config.rician_k_linear + 1.0)
            / np.maximum(snr_linear, 1e-12)
        )
        probabilities = ncx2.sf(b_squared, df=2, nc=a_squared)
        probabilities = np.clip(probabilities, 0.0, 1.0)
        np.fill_diagonal(probabilities, 0.0)
        return probabilities

    def sample_link_success(self, src: int, dst: int, link_prob_matrix: np.ndarray) -> bool:
        return bool(self.rng.random() <= link_prob_matrix[src, dst])
