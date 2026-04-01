from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys
from statistics import mean

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from slar_sim import AODVRouter, GPSRRouter, SLARGeoRouter, SLARRouter, SimulationConfig, SimulationLoop, build_random_nodes
from slar_sim.optimization import simplex_weight_grid


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run SLAR weight sensitivity analysis.")
    parser.add_argument("--grid-step", type=float, default=0.1, help="Simplex grid step for SLAR weights.")
    parser.add_argument("--nodes", type=int, default=20, help="Number of UAV nodes.")
    parser.add_argument("--steps", type=int, default=100, help="Number of simulation steps per run.")
    parser.add_argument("--seeds", type=int, default=20, help="Number of random seeds to average over.")
    parser.add_argument("--flows", type=int, default=20, help="Number of packets generated per seed.")
    parser.add_argument(
        "--arrival-window",
        type=int,
        default=20,
        help="Packets are injected uniformly over the first N steps.",
    )
    parser.add_argument(
        "--output-prefix",
        type=Path,
        default=REPO_ROOT / "analysis" / "weight_sensitivity",
        help="Prefix for JSON and CSV output files.",
    )
    return parser.parse_args()


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


def summarize_runs(runs: list[dict[str, float | int]]) -> dict[str, float]:
    attempts = mean(float(run["transmission_attempts"]) for run in runs)
    successes = mean(float(run["transmission_successes"]) for run in runs)
    return {
        "avg_pdr": mean(float(run["packet_delivery_ratio"]) for run in runs),
        "avg_delivered": mean(float(run["delivered_packets"]) for run in runs),
        "avg_dropped": mean(float(run["dropped_packets"]) for run in runs),
        "avg_attempts": attempts,
        "avg_successes": successes,
        "avg_success_rate": 0.0 if attempts == 0.0 else (successes / attempts),
    }


def evaluate_router(
    config: SimulationConfig,
    router_factory,
    num_nodes: int,
    num_steps: int,
    packet_schedules: dict[int, dict[int, list[tuple[int, int, int | None]]]],
) -> dict[str, float]:
    runs: list[dict[str, float | int]] = []
    for seed, schedule in packet_schedules.items():
        nodes = build_random_nodes(num_nodes=num_nodes, config=config, seed=seed)
        simulation = SimulationLoop(config=config, nodes=nodes, router=router_factory(), seed=seed)
        metrics = simulation.run(num_steps=num_steps, packet_schedule=schedule)
        runs.append(metrics.as_dict())
    return summarize_runs(runs)


def main() -> None:
    args = parse_args()
    config = SimulationConfig()

    packet_schedules = {
        seed: build_packet_schedule(
            num_nodes=args.nodes,
            flows=args.flows,
            arrival_window=args.arrival_window,
            seed=seed + 10_000,
        )
        for seed in range(args.seeds)
    }

    baseline_factories = {
        "gpsr": lambda: GPSRRouter(config),
        "aodv": lambda: AODVRouter(config),
        "slar-geo": lambda: SLARGeoRouter(config),
        "slar-default": lambda: SLARRouter(config),
    }
    baselines = {
        name: evaluate_router(
            config=config,
            router_factory=factory,
            num_nodes=args.nodes,
            num_steps=args.steps,
            packet_schedules=packet_schedules,
        )
        for name, factory in baseline_factories.items()
    }
    best_baseline_name = max(baselines, key=lambda name: baselines[name]["avg_pdr"])
    best_baseline_pdr = baselines[best_baseline_name]["avg_pdr"]

    weight_rows: list[dict[str, float]] = []
    for weights in simplex_weight_grid(step=args.grid_step):
        summary = evaluate_router(
            config=config,
            router_factory=lambda weights=weights: SLARRouter(config, weights=weights),
            num_nodes=args.nodes,
            num_steps=args.steps,
            packet_schedules=packet_schedules,
        )
        weight_rows.append(
            {
                "w_geo": weights[0],
                "w_link": weights[1],
                "w_ld": weights[2],
                **summary,
                "delta_pdr_vs_best_baseline": summary["avg_pdr"] - best_baseline_pdr,
            }
        )

    ranked_rows = sorted(
        weight_rows,
        key=lambda row: (-row["avg_pdr"], -row["avg_success_rate"], row["avg_attempts"]),
    )
    best_row = ranked_rows[0]

    args.output_prefix.parent.mkdir(parents=True, exist_ok=True)
    json_path = args.output_prefix.with_suffix(".json")
    csv_path = args.output_prefix.with_suffix(".csv")

    payload = {
        "experiment": {
            "grid_step": args.grid_step,
            "nodes": args.nodes,
            "steps": args.steps,
            "seeds": args.seeds,
            "flows": args.flows,
            "arrival_window": args.arrival_window,
        },
        "baselines": baselines,
        "best_baseline_name": best_baseline_name,
        "best_baseline_pdr": best_baseline_pdr,
        "best_slar": best_row,
        "top_10_slar_weights": ranked_rows[:10],
        "all_slar_weights": ranked_rows,
    }

    with json_path.open("w", encoding="utf-8") as json_file:
        json.dump(payload, json_file, indent=2, sort_keys=True)

    with csv_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=[
                "w_geo",
                "w_link",
                "w_ld",
                "avg_pdr",
                "avg_delivered",
                "avg_dropped",
                "avg_attempts",
                "avg_successes",
                "avg_success_rate",
                "delta_pdr_vs_best_baseline",
            ],
        )
        writer.writeheader()
        writer.writerows(ranked_rows)

    print(json.dumps(payload, indent=2, sort_keys=True))
    print()
    print(f"Saved JSON results to {json_path}")
    print(f"Saved CSV results to {csv_path}")


if __name__ == "__main__":
    main()
