from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class SimulationConfig:
    """Global constants for the SLAR simulation framework."""

    # Section 2.2 constants from the proposal.
    p_tx_dbm: float = 18.0
    path_loss_exponent: float = 2.8
    shadowing_std_db: float = 8.0
    noise_floor_dbm: float = -90.0
    gamma_threshold_db: float = 12.0
    rician_k_db: float = 6.0

    # Carrier constants used in PL0 from Eq. (1).
    carrier_frequency_hz: float = 5.8e9
    light_speed_mps: float = 3.0e8

    # Time and mobility.
    dt_s: float = 0.1
    min_speed_mps: float = 5.0
    max_speed_mps: float = 20.0
    mobility_accel_std_mps2: float = 1.0
    world_bounds_m: tuple[float, float, float] = (150.0, 150.0, 60.0)

    # Kalman filter and link-duration parameters from Section 3.
    kalman_process_noise_std_m: float = 0.5
    kalman_measurement_noise_std_m: float = 1.0
    link_duration_horizon_steps: int = 5

    # Routing constants from Section 4.
    aodv_cache_steps: int = 20
    default_packet_ttl: int = 30

    # The paper uses a communication range R qualitatively but does not tabulate
    # a single numeric value. 50 m is exposed as a configurable default because
    # the grey-zone discussion centers on roughly 25-50 m.
    communication_range_m: float = 50.0

    # The proposal requires temporally correlated shadowing but does not fix the
    # correlation coefficient. rho is therefore configurable.
    shadowing_correlation: float = 0.9

    # Default SLAR weights. Section 5 suggests tuning them via grid search.
    slar_weights: tuple[float, float, float] = (1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0)

    # Initial covariance scale for each UAV Kalman filter.
    initial_state_covariance: float = 10.0

    def __post_init__(self) -> None:
        if self.dt_s <= 0.0:
            raise ValueError("dt_s must be positive.")
        if self.min_speed_mps <= 0.0 or self.max_speed_mps < self.min_speed_mps:
            raise ValueError("Invalid speed bounds.")
        if self.link_duration_horizon_steps <= 0:
            raise ValueError("link_duration_horizon_steps must be positive.")
        if self.communication_range_m <= 0.0:
            raise ValueError("communication_range_m must be positive.")
        if not 0.0 <= self.shadowing_correlation < 1.0:
            raise ValueError("shadowing_correlation must lie in [0, 1).")
        if self.default_packet_ttl <= 0:
            raise ValueError("default_packet_ttl must be positive.")
        self.validate_slar_weights(self.slar_weights)

    @property
    def pl0_db(self) -> float:
        # Free-space path loss at 1 m used in Eq. (1).
        return 20.0 * math.log10((4.0 * math.pi * self.carrier_frequency_hz) / self.light_speed_mps)

    @property
    def rician_k_linear(self) -> float:
        return 10.0 ** (self.rician_k_db / 10.0)

    @property
    def gamma_threshold_linear(self) -> float:
        return 10.0 ** (self.gamma_threshold_db / 10.0)

    def validate_slar_weights(self, weights: tuple[float, float, float]) -> None:
        if len(weights) != 3:
            raise ValueError("SLAR weights must contain three values.")
        if any(weight < 0.0 for weight in weights):
            raise ValueError("SLAR weights must be non-negative.")
        if not math.isclose(sum(weights), 1.0, rel_tol=1e-9, abs_tol=1e-9):
            raise ValueError("SLAR weights must sum to 1.0.")
