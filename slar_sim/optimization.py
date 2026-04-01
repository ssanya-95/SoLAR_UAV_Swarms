from __future__ import annotations

from collections.abc import Callable

from .simulation import SimulationLoop


def simplex_weight_grid(step: float = 0.1) -> list[tuple[float, float, float]]:
    if step <= 0.0 or step > 1.0:
        raise ValueError("step must lie in (0, 1].")

    weights: list[tuple[float, float, float]] = []
    index_limit = int(round(1.0 / step))
    for geo_idx in range(index_limit + 1):
        for link_idx in range(index_limit + 1 - geo_idx):
            ld_idx = index_limit - geo_idx - link_idx
            weights.append((geo_idx * step, link_idx * step, ld_idx * step))
    return weights


def grid_search_slar_weights(
    simulation_factory: Callable[[tuple[float, float, float]], SimulationLoop],
    num_steps: int,
    step: float = 0.1,
) -> tuple[tuple[float, float, float], float, list[tuple[tuple[float, float, float], float]]]:
    best_weights: tuple[float, float, float] | None = None
    best_pdr = -1.0
    results: list[tuple[tuple[float, float, float], float]] = []

    for weights in simplex_weight_grid(step=step):
        simulation = simulation_factory(weights)
        metrics = simulation.run(num_steps=num_steps)
        pdr = metrics.packet_delivery_ratio
        results.append((weights, pdr))

        if pdr > best_pdr:
            best_pdr = pdr
            best_weights = weights

    if best_weights is None:
        raise RuntimeError("Weight search did not evaluate any candidates.")
    return best_weights, best_pdr, results
