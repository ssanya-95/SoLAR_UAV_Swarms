from __future__ import annotations

import argparse
from dataclasses import dataclass, field, replace
import json
import os
from pathlib import Path
import sys
from typing import Callable

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib-codex")

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from slar_sim import AODVRouter, GPSRRouter, SLARGeoRouter, SLARRouter, SimulationConfig, SimulationLoop, build_random_nodes
from slar_sim.optimization import simplex_weight_grid
from scripts.analysis_common import paired_ttest, run_router_experiment, summarize_rows, write_csv


@dataclass(frozen=True)
class ScenarioSpec:
    name: str
    family: str
    num_nodes: int = 20
    steps: int = 100
    flows: int = 20
    arrival_window: int = 20
    config_overrides: dict[str, object] = field(default_factory=dict)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a Globecom-style SLAR evaluation suite.")
    parser.add_argument("--grid-step", type=float, default=0.1, help="Weight simplex step used during tuning.")
    parser.add_argument("--train-seeds", type=int, default=8, help="Number of train seeds for weight tuning.")
    parser.add_argument("--test-seeds", type=int, default=12, help="Number of held-out test seeds.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "analysis" / "globecom_eval",
        help="Directory where tables, figures, and reports will be written.",
    )
    return parser.parse_args()


def build_scenarios() -> list[ScenarioSpec]:
    return [
        ScenarioSpec(name="base", family="base"),
        ScenarioSpec(name="density_low", family="density", num_nodes=12),
        ScenarioSpec(name="density_high", family="density", num_nodes=28),
        ScenarioSpec(name="traffic_light", family="traffic", flows=10, arrival_window=10),
        ScenarioSpec(name="traffic_heavy", family="traffic", flows=30, arrival_window=30),
        ScenarioSpec(name="mobility_low", family="mobility", config_overrides={"min_speed_mps": 5.0, "max_speed_mps": 10.0}),
        ScenarioSpec(name="mobility_high", family="mobility", config_overrides={"min_speed_mps": 10.0, "max_speed_mps": 20.0}),
        ScenarioSpec(name="shadowing_light", family="channel", config_overrides={"shadowing_std_db": 6.0}),
        ScenarioSpec(name="shadowing_heavy", family="channel", config_overrides={"shadowing_std_db": 10.0}),
        ScenarioSpec(name="range_short", family="channel", config_overrides={"communication_range_m": 45.0}),
        ScenarioSpec(name="range_long", family="channel", config_overrides={"communication_range_m": 55.0}),
    ]


def make_config(base_config: SimulationConfig, scenario: ScenarioSpec) -> SimulationConfig:
    return replace(base_config, **scenario.config_overrides)
def tune_weights(
    base_config: SimulationConfig,
    scenarios: list[ScenarioSpec],
    train_seeds: list[int],
    grid_step: float,
) -> tuple[tuple[float, float, float], list[dict[str, float]]]:
    tuning_rows: list[dict[str, float]] = []
    for weights in simplex_weight_grid(step=grid_step):
        all_rows: list[dict[str, float | int | str]] = []
        for scenario in scenarios:
            all_rows.extend(
                run_router_experiment(
                    base_config=base_config,
                    router_factory=lambda config, weights=weights: SLARRouter(config, weights=weights),
                    seeds=train_seeds,
                    num_nodes=scenario.num_nodes,
                    num_steps=scenario.steps,
                    flows=scenario.flows,
                    arrival_window=scenario.arrival_window,
                    config_overrides=scenario.config_overrides,
                    extra_row_data={"scenario": scenario.name, "family": scenario.family},
                    schedule_key=scenario.name,
                )
            )
        summary = summarize_rows(all_rows)
        tuning_rows.append(
            {
                "w_geo": weights[0],
                "w_link": weights[1],
                "w_ld": weights[2],
                "train_avg_pdr": summary["packet_delivery_ratio"]["mean"],
                "train_avg_latency": summary["avg_delivery_latency_steps"]["mean"],
                "train_avg_attempts": summary["transmission_attempts"]["mean"],
                "train_avg_success_rate": summary["avg_success_rate"]["mean"],
            }
        )

    ranked = sorted(
        tuning_rows,
        key=lambda row: (
            -row["train_avg_pdr"],
            -row["train_avg_success_rate"],
            row["train_avg_latency"],
            row["train_avg_attempts"],
        ),
    )
    best = ranked[0]
    return (best["w_geo"], best["w_link"], best["w_ld"]), ranked


def plot_tuning_heatmap(tuning_rows: list[dict[str, float]], output_path: Path) -> None:
    step = min({round(row["w_geo"], 10) for row in tuning_rows if row["w_geo"] > 0.0} or {1.0})
    index_limit = int(round(1.0 / step))
    matrix = np.full((index_limit + 1, index_limit + 1), np.nan)

    for row in tuning_rows:
        geo_idx = int(round(row["w_geo"] / step))
        link_idx = int(round(row["w_link"] / step))
        matrix[geo_idx, link_idx] = row["train_avg_pdr"]

    plt.figure(figsize=(8, 6))
    image = plt.imshow(matrix, origin="lower", aspect="auto", cmap="viridis")
    plt.colorbar(image, label="Train Average PDR")
    ticks = np.arange(index_limit + 1)
    tick_labels = [f"{tick * step:.1f}" for tick in ticks]
    plt.xticks(ticks, tick_labels)
    plt.yticks(ticks, tick_labels)
    plt.xlabel("w_link")
    plt.ylabel("w_geo")
    plt.title("SLAR Weight-Tuning Heatmap")
    plt.tight_layout()
    plt.savefig(output_path, dpi=200)
    plt.close()


def plot_metric_by_scenario(
    scenario_summary_rows: list[dict[str, object]],
    routers: list[str],
    metric_prefix: str,
    ylabel: str,
    title: str,
    output_path: Path,
) -> None:
    scenario_names = list(dict.fromkeys(row["scenario"] for row in scenario_summary_rows))
    x_positions = np.arange(len(scenario_names))
    width = 0.8 / len(routers)

    plt.figure(figsize=(15, 6))
    for router_index, router_name in enumerate(routers):
        means = []
        errors = []
        for scenario_name in scenario_names:
            row = next(
                item
                for item in scenario_summary_rows
                if item["scenario"] == scenario_name and item["router"] == router_name
            )
            means.append(float(row[f"{metric_prefix}_mean"]))
            errors.append(float(row[f"{metric_prefix}_ci95"]))
        offset = (router_index - (len(routers) - 1) / 2.0) * width
        plt.bar(x_positions + offset, means, width=width, yerr=errors, capsize=3, label=router_name)

    plt.xticks(x_positions, scenario_names, rotation=35, ha="right")
    plt.ylabel(ylabel)
    plt.title(title)
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_path, dpi=200)
    plt.close()


def main() -> None:
    args = parse_args()
    output_dir = args.output_dir
    figures_dir = output_dir / "figures"
    tables_dir = output_dir / "tables"
    output_dir.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)
    tables_dir.mkdir(parents=True, exist_ok=True)

    base_config = SimulationConfig()
    all_scenarios = build_scenarios()
    tuning_scenarios = [scenario for scenario in all_scenarios if scenario.name in {"base", "traffic_heavy", "mobility_high", "shadowing_heavy"}]

    train_seeds = list(range(args.train_seeds))
    test_seeds = list(range(args.train_seeds, args.train_seeds + args.test_seeds))

    tuned_weights, tuning_rows = tune_weights(
        base_config=base_config,
        scenarios=tuning_scenarios,
        train_seeds=train_seeds,
        grid_step=args.grid_step,
    )

    router_factories = {
        "gpsr": lambda config: GPSRRouter(config),
        "aodv": lambda config: AODVRouter(config),
        "slar-geo": lambda config: SLARGeoRouter(config),
        "slar-default": lambda config: SLARRouter(config),
        "slar-tuned": lambda config: SLARRouter(config, weights=tuned_weights),
    }

    raw_rows: list[dict[str, object]] = []
    scenario_summary_rows: list[dict[str, object]] = []
    significance_rows: list[dict[str, object]] = []

    raw_by_scenario_router: dict[tuple[str, str], list[dict[str, float | int | str]]] = {}
    for scenario in all_scenarios:
        for router_name, factory in router_factories.items():
            rows = run_router_experiment(
                base_config=base_config,
                router_factory=factory,
                seeds=test_seeds,
                num_nodes=scenario.num_nodes,
                num_steps=scenario.steps,
                flows=scenario.flows,
                arrival_window=scenario.arrival_window,
                config_overrides=scenario.config_overrides,
                extra_row_data={"scenario": scenario.name, "family": scenario.family},
                schedule_key=scenario.name,
            )
            raw_by_scenario_router[(scenario.name, router_name)] = rows

    # Expand the per-run rows with router labels after execution to keep the loop simple.
    raw_rows = []
    for (scenario_name, router_name), rows in raw_by_scenario_router.items():
        del scenario_name
        for row in rows:
            raw_rows.append({**row, "router": router_name})

    for scenario in all_scenarios:
        for router_name in router_factories:
            summary = summarize_rows(raw_by_scenario_router[(scenario.name, router_name)])
            scenario_summary_rows.append(
                {
                    "scenario": scenario.name,
                    "family": scenario.family,
                    "router": router_name,
                    "packet_delivery_ratio_mean": summary["packet_delivery_ratio"]["mean"],
                    "packet_delivery_ratio_ci95": summary["packet_delivery_ratio"]["ci95_half_width"],
                    "avg_delivery_latency_steps_mean": summary["avg_delivery_latency_steps"]["mean"],
                    "avg_delivery_latency_steps_ci95": summary["avg_delivery_latency_steps"]["ci95_half_width"],
                    "avg_hops_per_delivered_mean": summary["avg_hops_per_delivered"]["mean"],
                    "avg_hops_per_delivered_ci95": summary["avg_hops_per_delivered"]["ci95_half_width"],
                    "avg_total_queue_length_mean": summary["avg_total_queue_length"]["mean"],
                    "avg_total_queue_length_ci95": summary["avg_total_queue_length"]["ci95_half_width"],
                    "transmission_attempts_mean": summary["transmission_attempts"]["mean"],
                    "transmission_attempts_ci95": summary["transmission_attempts"]["ci95_half_width"],
                    "avg_success_rate_mean": summary["avg_success_rate"]["mean"],
                    "avg_success_rate_ci95": summary["avg_success_rate"]["ci95_half_width"],
                }
            )

        tuned_rows = raw_by_scenario_router[(scenario.name, "slar-tuned")]
        for baseline_name in ("slar-default", "gpsr", "aodv", "slar-geo"):
            baseline_rows = raw_by_scenario_router[(scenario.name, baseline_name)]
            for metric_name in ("packet_delivery_ratio", "avg_delivery_latency_steps", "transmission_attempts"):
                significance = paired_ttest(
                    tuned_values=[float(row[metric_name]) for row in tuned_rows],
                    baseline_values=[float(row[metric_name]) for row in baseline_rows],
                )
                significance_rows.append(
                    {
                        "scenario": scenario.name,
                        "family": scenario.family,
                        "baseline": baseline_name,
                        "metric": metric_name,
                        **significance,
                        "significant_p_lt_0_05": significance["p_value"] < 0.05,
                    }
                )

    overall_rows: list[dict[str, object]] = []
    for router_name in router_factories:
        router_rows = [row for row in raw_rows if row["router"] == router_name]
        summary = summarize_rows(router_rows)
        overall_rows.append(
            {
                "router": router_name,
                "packet_delivery_ratio_mean": summary["packet_delivery_ratio"]["mean"],
                "packet_delivery_ratio_ci95": summary["packet_delivery_ratio"]["ci95_half_width"],
                "avg_delivery_latency_steps_mean": summary["avg_delivery_latency_steps"]["mean"],
                "avg_delivery_latency_steps_ci95": summary["avg_delivery_latency_steps"]["ci95_half_width"],
                "avg_hops_per_delivered_mean": summary["avg_hops_per_delivered"]["mean"],
                "avg_hops_per_delivered_ci95": summary["avg_hops_per_delivered"]["ci95_half_width"],
                "avg_total_queue_length_mean": summary["avg_total_queue_length"]["mean"],
                "avg_total_queue_length_ci95": summary["avg_total_queue_length"]["ci95_half_width"],
                "transmission_attempts_mean": summary["transmission_attempts"]["mean"],
                "transmission_attempts_ci95": summary["transmission_attempts"]["ci95_half_width"],
                "avg_success_rate_mean": summary["avg_success_rate"]["mean"],
                "avg_success_rate_ci95": summary["avg_success_rate"]["ci95_half_width"],
            }
        )

    overall_rows = sorted(overall_rows, key=lambda row: (-float(row["packet_delivery_ratio_mean"]), float(row["avg_delivery_latency_steps_mean"])))

    plot_tuning_heatmap(tuning_rows=tuning_rows, output_path=figures_dir / "tuning_heatmap.png")
    plot_metric_by_scenario(
        scenario_summary_rows=scenario_summary_rows,
        routers=list(router_factories.keys()),
        metric_prefix="packet_delivery_ratio",
        ylabel="Packet Delivery Ratio",
        title="PDR Across Held-Out Scenario Families",
        output_path=figures_dir / "pdr_by_scenario.png",
    )
    plot_metric_by_scenario(
        scenario_summary_rows=scenario_summary_rows,
        routers=list(router_factories.keys()),
        metric_prefix="avg_delivery_latency_steps",
        ylabel="Average Delivery Latency (steps)",
        title="Latency Across Held-Out Scenario Families",
        output_path=figures_dir / "latency_by_scenario.png",
    )
    plot_metric_by_scenario(
        scenario_summary_rows=scenario_summary_rows,
        routers=list(router_factories.keys()),
        metric_prefix="transmission_attempts",
        ylabel="Transmission Attempts",
        title="Transmission Attempts Across Held-Out Scenario Families",
        output_path=figures_dir / "attempts_by_scenario.png",
    )

    write_csv(tables_dir / "tuning_results.csv", tuning_rows)
    write_csv(tables_dir / "raw_per_seed_results.csv", raw_rows)
    write_csv(tables_dir / "scenario_summary.csv", scenario_summary_rows)
    write_csv(tables_dir / "overall_router_summary.csv", overall_rows)
    write_csv(tables_dir / "paired_significance.csv", significance_rows)

    summary_payload = {
        "train_seed_count": len(train_seeds),
        "test_seed_count": len(test_seeds),
        "tuning_scenarios": [scenario.name for scenario in tuning_scenarios],
        "tuned_weights": {
            "w_geo": tuned_weights[0],
            "w_link": tuned_weights[1],
            "w_ld": tuned_weights[2],
        },
        "overall_ranking": overall_rows,
        "top_10_tuning_rows": tuning_rows[:10],
    }
    with (output_dir / "summary.json").open("w", encoding="utf-8") as summary_file:
        json.dump(summary_payload, summary_file, indent=2, sort_keys=True)

    tuned_overall = next(row for row in overall_rows if row["router"] == "slar-tuned")
    default_overall = next(row for row in overall_rows if row["router"] == "slar-default")
    gpsr_overall = next(row for row in overall_rows if row["router"] == "gpsr")
    aodv_overall = next(row for row in overall_rows if row["router"] == "aodv")
    significant_pdr_wins = sum(
        1
        for row in significance_rows
        if row["baseline"] in {"slar-default", "gpsr", "aodv"}
        and row["metric"] == "packet_delivery_ratio"
        and bool(row["significant_p_lt_0_05"])
        and float(row["mean_diff"]) > 0.0
    )

    report_lines = [
        "# Globecom Evaluation Report",
        "",
        "## Protocol",
        "",
        f"- Train seeds: `{len(train_seeds)}`",
        f"- Test seeds: `{len(test_seeds)}`",
        f"- Tuning scenarios: `{', '.join(scenario.name for scenario in tuning_scenarios)}`",
        f"- Tuned SLAR weights: `(w_geo, w_link, w_ld) = ({tuned_weights[0]:.1f}, {tuned_weights[1]:.1f}, {tuned_weights[2]:.1f})`",
        "",
        "## Overall Results",
        "",
        f"- `slar-tuned`: PDR `{tuned_overall['packet_delivery_ratio_mean']:.4f}` +/- `{tuned_overall['packet_delivery_ratio_ci95']:.4f}`, latency `{tuned_overall['avg_delivery_latency_steps_mean']:.2f}` steps",
        f"- `slar-default`: PDR `{default_overall['packet_delivery_ratio_mean']:.4f}` +/- `{default_overall['packet_delivery_ratio_ci95']:.4f}`",
        f"- `gpsr`: PDR `{gpsr_overall['packet_delivery_ratio_mean']:.4f}` +/- `{gpsr_overall['packet_delivery_ratio_ci95']:.4f}`",
        f"- `aodv`: PDR `{aodv_overall['packet_delivery_ratio_mean']:.4f}` +/- `{aodv_overall['packet_delivery_ratio_ci95']:.4f}`",
        "",
        "## Interpretation",
        "",
        f"- Tuned SLAR records `{significant_pdr_wins}` significant PDR wins against `slar-default`, `gpsr`, and `aodv` across the scenario matrix.",
        "- The strongest weights should be fixed before the final paper experiments; they should not be retuned on the reported test seeds.",
        "- The generated tables and plots are intended for internal iteration and figure drafting, not final publication formatting.",
        "",
        "## Artifacts",
        "",
        "- `tables/tuning_results.csv`",
        "- `tables/scenario_summary.csv`",
        "- `tables/overall_router_summary.csv`",
        "- `tables/paired_significance.csv`",
        "- `figures/tuning_heatmap.png`",
        "- `figures/pdr_by_scenario.png`",
        "- `figures/latency_by_scenario.png`",
        "- `figures/attempts_by_scenario.png`",
    ]
    (output_dir / "report.md").write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    print(json.dumps(summary_payload, indent=2, sort_keys=True))
    print()
    print(f"Saved evaluation artifacts to {output_dir}")


if __name__ == "__main__":
    main()
