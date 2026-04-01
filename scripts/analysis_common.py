from __future__ import annotations

import csv
from dataclasses import replace
import math
from pathlib import Path
from typing import Any, Callable, Mapping

import numpy as np
from scipy import stats

from slar_sim import SimulationConfig, SimulationLoop, build_random_nodes


DEFAULT_METRIC_NAMES = [
    "packet_delivery_ratio",
    "avg_delivery_latency_steps",
    "avg_hops_per_delivered",
    "avg_total_queue_length",
    "transmission_attempts",
    "transmission_successes",
    "avg_success_rate",
]


def build_packet_schedule(
    num_nodes: int,
    flows: int,
    arrival_window: int,
    seed: int,
) -> dict[int, list[tuple[int, int, int | None]]]:
    rng = np.random.default_rng(seed)
    schedule: dict[int, list[tuple[int, int, int | None]]] = {}
    for _ in range(flows):
        src, dst = rng.choice(num_nodes, size=2, replace=False)
        step = int(rng.integers(0, max(arrival_window, 1)))
        schedule.setdefault(step, []).append((int(src), int(dst), None))
    return schedule


def stable_seed_offset(identifier: str) -> int:
    return sum((index + 1) * ord(character) for index, character in enumerate(identifier))


def run_router_experiment(
    *,
    base_config: SimulationConfig,
    router_factory: Callable[[SimulationConfig], object],
    seeds: list[int],
    num_nodes: int,
    num_steps: int,
    flows: int,
    arrival_window: int,
    config_overrides: Mapping[str, object] | None = None,
    extra_row_data: Mapping[str, object] | None = None,
    schedule_key: str,
) -> list[dict[str, float | int | str | object]]:
    config = replace(base_config, **dict(config_overrides or {}))
    offset = stable_seed_offset(schedule_key)
    rows: list[dict[str, float | int | str | object]] = []

    for seed in seeds:
        schedule = build_packet_schedule(
            num_nodes=num_nodes,
            flows=flows,
            arrival_window=arrival_window,
            seed=(seed * 10_000) + offset,
        )
        nodes = build_random_nodes(num_nodes=num_nodes, config=config, seed=seed)
        simulation = SimulationLoop(config=config, nodes=nodes, router=router_factory(config), seed=seed)
        metrics = simulation.run(num_steps=num_steps, packet_schedule=schedule).as_dict()
        rows.append(
            {
                **dict(extra_row_data or {}),
                "seed": seed,
                **metrics,
            }
        )

    return rows


def summarize_metric(values: list[float]) -> dict[str, float]:
    array = np.asarray(values, dtype=float)
    sample_count = int(array.size)
    mean_value = float(array.mean()) if sample_count else 0.0
    std_value = float(array.std(ddof=1)) if sample_count > 1 else 0.0
    if sample_count > 1:
        ci_half_width = float(stats.t.ppf(0.975, sample_count - 1) * std_value / math.sqrt(sample_count))
    else:
        ci_half_width = 0.0
    return {
        "mean": mean_value,
        "std": std_value,
        "ci95_half_width": ci_half_width,
        "samples": sample_count,
    }


def summarize_rows(
    rows: list[dict[str, float | int | str | object]],
    metric_names: list[str] | None = None,
) -> dict[str, dict[str, float]]:
    names = DEFAULT_METRIC_NAMES if metric_names is None else metric_names
    return {
        metric_name: summarize_metric([float(row[metric_name]) for row in rows])
        for metric_name in names
    }


def paired_ttest(tuned_values: list[float], baseline_values: list[float]) -> dict[str, float]:
    differences = np.asarray(tuned_values, dtype=float) - np.asarray(baseline_values, dtype=float)
    if np.allclose(differences, 0.0):
        return {"mean_diff": 0.0, "t_stat": 0.0, "p_value": 1.0, "effect_size_dz": 0.0}
    t_stat, p_value = stats.ttest_rel(tuned_values, baseline_values)
    std_diff = float(np.std(differences, ddof=1)) if differences.size > 1 else 0.0
    effect_size = 0.0 if math.isclose(std_diff, 0.0) else float(np.mean(differences) / std_diff)
    return {
        "mean_diff": float(np.mean(differences)),
        "t_stat": float(t_stat),
        "p_value": float(p_value),
        "effect_size_dz": effect_size,
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
