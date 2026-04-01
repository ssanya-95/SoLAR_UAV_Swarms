from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib-codex")

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from slar_sim import AODVRouter, GPSRRouter, SLARGeoRouter, SLARRouter, SimulationConfig
from slar_sim.optimization import simplex_weight_grid
from scripts.analysis_common import paired_ttest, run_router_experiment, summarize_rows, write_csv


ROUTER_COLORS = {
    "slar-tuned": "#0F766E",
    "slar-default": "#2563EB",
    "gpsr": "#7C3AED",
    "aodv": "#6B7280",
    "slar-geo": "#94A3B8",
}

MAIN_PLOT_ROUTERS = ["slar-tuned", "slar-default", "gpsr", "aodv"]
SIGNIFICANCE_BASELINES = ["slar-default", "gpsr", "aodv", "slar-geo"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run UAV-count sensitivity analysis for SLAR.")
    parser.add_argument("--grid-step", type=float, default=0.1, help="Weight simplex step used during tuning.")
    parser.add_argument("--train-seeds", type=int, default=8, help="Number of train seeds for weight tuning.")
    parser.add_argument("--test-seeds", type=int, default=12, help="Number of held-out test seeds.")
    parser.add_argument(
        "--uav-counts",
        type=str,
        default="8,12,16,20,24,28,32",
        help="Comma-separated UAV counts to evaluate.",
    )
    parser.add_argument("--reference-count", type=int, default=20, help="UAV count used for one-time SLAR tuning.")
    parser.add_argument("--steps", type=int, default=100, help="Number of simulation steps per run.")
    parser.add_argument("--flows", type=int, default=20, help="Fixed number of generated packets at every UAV count.")
    parser.add_argument(
        "--arrival-window",
        type=int,
        default=20,
        help="Packets are injected uniformly over the first N steps at every UAV count.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "analysis" / "uav_count_sensitivity",
        help="Directory where tables, figures, and reports will be written.",
    )
    return parser.parse_args()


def parse_uav_counts(counts_text: str) -> list[int]:
    counts = [int(item.strip()) for item in counts_text.split(",") if item.strip()]
    if not counts:
        raise ValueError("At least one UAV count must be provided.")
    if any(count <= 1 for count in counts):
        raise ValueError("All UAV counts must be greater than 1.")
    return sorted(set(counts))


def build_tuning_scenarios(reference_count: int, steps: int) -> list[dict[str, object]]:
    return [
        {
            "name": "base",
            "num_nodes": reference_count,
            "steps": steps,
            "flows": 20,
            "arrival_window": 20,
            "config_overrides": {},
        },
        {
            "name": "traffic_heavy",
            "num_nodes": reference_count,
            "steps": steps,
            "flows": 30,
            "arrival_window": 30,
            "config_overrides": {},
        },
        {
            "name": "mobility_high",
            "num_nodes": reference_count,
            "steps": steps,
            "flows": 20,
            "arrival_window": 20,
            "config_overrides": {"min_speed_mps": 10.0, "max_speed_mps": 20.0},
        },
        {
            "name": "shadowing_heavy",
            "num_nodes": reference_count,
            "steps": steps,
            "flows": 20,
            "arrival_window": 20,
            "config_overrides": {"shadowing_std_db": 10.0},
        },
    ]


def tune_weights(
    *,
    base_config: SimulationConfig,
    reference_count: int,
    steps: int,
    train_seeds: list[int],
    grid_step: float,
) -> tuple[tuple[float, float, float], list[dict[str, float]]]:
    tuning_rows: list[dict[str, float]] = []
    tuning_scenarios = build_tuning_scenarios(reference_count=reference_count, steps=steps)

    for weights in simplex_weight_grid(step=grid_step):
        all_rows: list[dict[str, object]] = []
        for scenario in tuning_scenarios:
            all_rows.extend(
                run_router_experiment(
                    base_config=base_config,
                    router_factory=lambda config, weights=weights: SLARRouter(config, weights=weights),
                    seeds=train_seeds,
                    num_nodes=int(scenario["num_nodes"]),
                    num_steps=int(scenario["steps"]),
                    flows=int(scenario["flows"]),
                    arrival_window=int(scenario["arrival_window"]),
                    config_overrides=dict(scenario["config_overrides"]),
                    extra_row_data={"scenario": scenario["name"]},
                    schedule_key=str(scenario["name"]),
                )
            )

        summary = summarize_rows(all_rows)
        tuning_rows.append(
            {
                "w_geo": weights[0],
                "w_link": weights[1],
                "w_ld": weights[2],
                "train_avg_pdr": summary["packet_delivery_ratio"]["mean"],
                "train_avg_success_rate": summary["avg_success_rate"]["mean"],
                "train_avg_latency": summary["avg_delivery_latency_steps"]["mean"],
                "train_avg_attempts": summary["transmission_attempts"]["mean"],
            }
        )

    ranked_rows = sorted(
        tuning_rows,
        key=lambda row: (
            -row["train_avg_pdr"],
            -row["train_avg_success_rate"],
            row["train_avg_latency"],
            row["train_avg_attempts"],
        ),
    )
    best = ranked_rows[0]
    return (best["w_geo"], best["w_link"], best["w_ld"]), ranked_rows


def summarize_router_rows(rows: list[dict[str, object]]) -> dict[str, float]:
    summary = summarize_rows(rows)
    return {
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


def plot_metric_vs_uavs(
    summary_rows: list[dict[str, object]],
    *,
    routers: list[str],
    metric_prefix: str,
    ylabel: str,
    title: str,
    output_path: Path,
) -> None:
    uav_counts = sorted({int(row["uav_count"]) for row in summary_rows})

    plt.figure(figsize=(8.5, 5.4))
    for router_name in routers:
        router_rows = [row for row in summary_rows if row["router"] == router_name]
        means = []
        errors = []
        for uav_count in uav_counts:
            row = next(item for item in router_rows if int(item["uav_count"]) == uav_count)
            means.append(float(row[f"{metric_prefix}_mean"]))
            errors.append(float(row[f"{metric_prefix}_ci95"]))

        plt.errorbar(
            uav_counts,
            means,
            yerr=errors,
            marker="o",
            linewidth=2.0,
            markersize=5.5,
            capsize=4,
            color=ROUTER_COLORS[router_name],
            label=router_name,
        )

    plt.xlabel("Number of UAVs")
    plt.ylabel(ylabel)
    plt.title(title)
    plt.xticks(uav_counts)
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_path, dpi=220)
    plt.close()


def overall_summary_rows(raw_rows: list[dict[str, object]], router_names: list[str]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for router_name in router_names:
        summary = summarize_router_rows([row for row in raw_rows if row["router"] == router_name])
        rows.append({"router": router_name, **summary})
    return sorted(rows, key=lambda row: (-float(row["packet_delivery_ratio_mean"]), float(row["avg_delivery_latency_steps_mean"])))


def build_report(
    *,
    tuned_weights: tuple[float, float, float],
    reference_count: int,
    train_seed_count: int,
    test_seed_count: int,
    uav_counts: list[int],
    overall_rows: list[dict[str, object]],
    uav_count_summary_rows: list[dict[str, object]],
    significance_rows: list[dict[str, object]],
    output_path: Path,
) -> None:
    tuned_overall = next(row for row in overall_rows if row["router"] == "slar-tuned")
    default_overall = next(row for row in overall_rows if row["router"] == "slar-default")
    gpsr_overall = next(row for row in overall_rows if row["router"] == "gpsr")
    aodv_overall = next(row for row in overall_rows if row["router"] == "aodv")

    count_to_margin: dict[int, float] = {}
    count_to_best_baseline: dict[int, str] = {}
    for uav_count in uav_counts:
        tuned_row = next(
            row for row in uav_count_summary_rows
            if int(row["uav_count"]) == uav_count and row["router"] == "slar-tuned"
        )
        baselines = [
            row for row in uav_count_summary_rows
            if int(row["uav_count"]) == uav_count and row["router"] in {"slar-default", "gpsr", "aodv"}
        ]
        best_baseline = max(baselines, key=lambda row: float(row["packet_delivery_ratio_mean"]))
        count_to_margin[uav_count] = float(tuned_row["packet_delivery_ratio_mean"]) - float(best_baseline["packet_delivery_ratio_mean"])
        count_to_best_baseline[uav_count] = str(best_baseline["router"])

    largest_margin_count = max(count_to_margin, key=lambda count: count_to_margin[count])
    low_density_counts = uav_counts[:2] if len(uav_counts) >= 2 else uav_counts
    high_density_counts = uav_counts[-3:] if len(uav_counts) >= 3 else uav_counts
    low_density_mean_margin = sum(count_to_margin[count] for count in low_density_counts) / len(low_density_counts)
    high_density_mean_margin = sum(count_to_margin[count] for count in high_density_counts) / len(high_density_counts)

    if high_density_mean_margin <= low_density_mean_margin - 0.01:
        saturation_text = "The SLAR margin declines at the highest UAV counts, suggesting partial saturation in dense swarms."
    elif high_density_mean_margin >= low_density_mean_margin + 0.01:
        saturation_text = "The SLAR margin remains strong or improves at the highest UAV counts, so gains do not appear to saturate yet."
    else:
        saturation_text = "The SLAR margin stays broadly stable between moderate and high UAV counts, indicating limited saturation."

    if low_density_mean_margin < max(count_to_margin.values()) - 0.01:
        low_density_text = "At low UAV counts, the SLAR advantage is smaller, which is consistent with fewer forward candidates being available."
    else:
        low_density_text = "Low-density operation does not erase the SLAR advantage in the current simulator."

    pdr_wins_by_count: list[str] = []
    for uav_count in uav_counts:
        wins = sum(
            1
            for row in significance_rows
            if int(row["uav_count"]) == uav_count
            and row["baseline"] in {"slar-default", "gpsr", "aodv"}
            and row["metric"] == "packet_delivery_ratio"
            and bool(row["significant_p_lt_0_05"])
            and float(row["mean_diff"]) > 0.0
        )
        pdr_wins_by_count.append(f"- `{uav_count}` UAVs: `{wins}` significant PDR wins against the main baselines")

    lines = [
        "# UAV-Count Sensitivity Report",
        "",
        "## Protocol",
        "",
        f"- Train seeds: `{train_seed_count}`",
        f"- Test seeds: `{test_seed_count}`",
        f"- Reference tuning count: `{reference_count}` UAVs",
        f"- Tuned SLAR weights: `(w_geo, w_link, w_ld) = ({tuned_weights[0]:.1f}, {tuned_weights[1]:.1f}, {tuned_weights[2]:.1f})`",
        f"- Evaluated UAV counts: `{', '.join(str(count) for count in uav_counts)}`",
        "- Simulation volume fixed to the current default world bounds for every count.",
        "- Traffic held fixed for every count: `flows=20`, `arrival_window=20`.",
        "",
        "## Overall Results",
        "",
        f"- `slar-tuned`: PDR `{tuned_overall['packet_delivery_ratio_mean']:.4f}` +/- `{tuned_overall['packet_delivery_ratio_ci95']:.4f}`, latency `{tuned_overall['avg_delivery_latency_steps_mean']:.2f}` steps",
        f"- `slar-default`: PDR `{default_overall['packet_delivery_ratio_mean']:.4f}` +/- `{default_overall['packet_delivery_ratio_ci95']:.4f}`",
        f"- `gpsr`: PDR `{gpsr_overall['packet_delivery_ratio_mean']:.4f}` +/- `{gpsr_overall['packet_delivery_ratio_ci95']:.4f}`",
        f"- `aodv`: PDR `{aodv_overall['packet_delivery_ratio_mean']:.4f}` +/- `{aodv_overall['packet_delivery_ratio_ci95']:.4f}`",
        "",
        "## UAV-Count Highlights",
        "",
        f"- Largest SLAR margin occurs at `{largest_margin_count}` UAVs, where the best competing baseline is `{count_to_best_baseline[largest_margin_count]}` and the PDR margin is `{count_to_margin[largest_margin_count]:.4f}`.",
        f"- {saturation_text}",
        f"- {low_density_text}",
        "",
        "## Significant PDR Wins by UAV Count",
        "",
        *pdr_wins_by_count,
        "",
        "## Artifacts",
        "",
        "- `tables/tuning_results.csv`",
        "- `tables/uav_count_summary.csv`",
        "- `tables/overall_router_summary.csv`",
        "- `tables/paired_significance_by_count.csv`",
        "- `figures/pdr_vs_uavs.png`",
        "- `figures/latency_vs_uavs.png`",
        "- `figures/attempts_vs_uavs.png`",
        "- `figures/success_rate_vs_uavs.png`",
    ]
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    uav_counts = parse_uav_counts(args.uav_counts)
    output_dir = args.output_dir
    figures_dir = output_dir / "figures"
    tables_dir = output_dir / "tables"
    output_dir.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)
    tables_dir.mkdir(parents=True, exist_ok=True)

    base_config = SimulationConfig()
    train_seeds = list(range(args.train_seeds))
    test_seeds = list(range(args.train_seeds, args.train_seeds + args.test_seeds))

    tuned_weights, tuning_rows = tune_weights(
        base_config=base_config,
        reference_count=args.reference_count,
        steps=args.steps,
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

    raw_by_count_router: dict[tuple[int, str], list[dict[str, object]]] = {}
    for uav_count in uav_counts:
        for router_name, factory in router_factories.items():
            rows = run_router_experiment(
                base_config=base_config,
                router_factory=factory,
                seeds=test_seeds,
                num_nodes=uav_count,
                num_steps=args.steps,
                flows=args.flows,
                arrival_window=args.arrival_window,
                config_overrides={},
                extra_row_data={"uav_count": uav_count},
                schedule_key=f"uav_count_{uav_count}",
            )
            raw_by_count_router[(uav_count, router_name)] = rows

    raw_rows: list[dict[str, object]] = []
    for (uav_count, router_name), rows in raw_by_count_router.items():
        del uav_count
        for row in rows:
            raw_rows.append({**row, "router": router_name})

    uav_count_summary_rows: list[dict[str, object]] = []
    significance_rows: list[dict[str, object]] = []
    for uav_count in uav_counts:
        for router_name in router_factories:
            summary_row = summarize_router_rows(raw_by_count_router[(uav_count, router_name)])
            uav_count_summary_rows.append(
                {
                    "uav_count": uav_count,
                    "router": router_name,
                    **summary_row,
                }
            )

        tuned_rows = raw_by_count_router[(uav_count, "slar-tuned")]
        for baseline_name in SIGNIFICANCE_BASELINES:
            baseline_rows = raw_by_count_router[(uav_count, baseline_name)]
            for metric_name in ("packet_delivery_ratio", "avg_delivery_latency_steps", "transmission_attempts", "avg_success_rate"):
                significance = paired_ttest(
                    tuned_values=[float(row[metric_name]) for row in tuned_rows],
                    baseline_values=[float(row[metric_name]) for row in baseline_rows],
                )
                significance_rows.append(
                    {
                        "uav_count": uav_count,
                        "baseline": baseline_name,
                        "metric": metric_name,
                        **significance,
                        "significant_p_lt_0_05": significance["p_value"] < 0.05,
                    }
                )

    uav_count_summary_rows = sorted(
        uav_count_summary_rows,
        key=lambda row: (int(row["uav_count"]), str(row["router"])),
    )
    overall_rows = overall_summary_rows(raw_rows, list(router_factories.keys()))

    plot_metric_vs_uavs(
        uav_count_summary_rows,
        routers=MAIN_PLOT_ROUTERS,
        metric_prefix="packet_delivery_ratio",
        ylabel="Packet Delivery Ratio",
        title="PDR vs Number of UAVs",
        output_path=figures_dir / "pdr_vs_uavs.png",
    )
    plot_metric_vs_uavs(
        uav_count_summary_rows,
        routers=MAIN_PLOT_ROUTERS,
        metric_prefix="avg_delivery_latency_steps",
        ylabel="Average Delivery Latency (steps)",
        title="Latency vs Number of UAVs",
        output_path=figures_dir / "latency_vs_uavs.png",
    )
    plot_metric_vs_uavs(
        uav_count_summary_rows,
        routers=MAIN_PLOT_ROUTERS,
        metric_prefix="transmission_attempts",
        ylabel="Transmission Attempts",
        title="Transmission Attempts vs Number of UAVs",
        output_path=figures_dir / "attempts_vs_uavs.png",
    )
    plot_metric_vs_uavs(
        uav_count_summary_rows,
        routers=MAIN_PLOT_ROUTERS,
        metric_prefix="avg_success_rate",
        ylabel="Average Success Rate",
        title="Success Rate vs Number of UAVs",
        output_path=figures_dir / "success_rate_vs_uavs.png",
    )

    write_csv(tables_dir / "tuning_results.csv", tuning_rows)
    write_csv(tables_dir / "raw_per_seed_results.csv", raw_rows)
    write_csv(tables_dir / "uav_count_summary.csv", uav_count_summary_rows)
    write_csv(tables_dir / "overall_router_summary.csv", overall_rows)
    write_csv(tables_dir / "paired_significance_by_count.csv", significance_rows)

    ordered_results = []
    for uav_count in uav_counts:
        ordered_results.append(
            {
                "uav_count": uav_count,
                "routers": [
                    row
                    for row in uav_count_summary_rows
                    if int(row["uav_count"]) == uav_count
                ],
            }
        )

    summary_payload = {
        "experiment": {
            "grid_step": args.grid_step,
            "train_seed_count": len(train_seeds),
            "test_seed_count": len(test_seeds),
            "reference_count": args.reference_count,
            "uav_counts": uav_counts,
            "steps": args.steps,
            "flows": args.flows,
            "arrival_window": args.arrival_window,
        },
        "fixed_assumptions": {
            "world_bounds_policy": "fixed default world bounds for every UAV count",
            "traffic_policy": "fixed flows and arrival window for every UAV count",
            "weight_policy": "tune once at reference count and freeze across the sweep",
        },
        "tuning_protocol": {
            "reference_count": args.reference_count,
            "scenarios": ["base", "traffic_heavy", "mobility_high", "shadowing_heavy"],
        },
        "tuned_weights": {
            "w_geo": tuned_weights[0],
            "w_link": tuned_weights[1],
            "w_ld": tuned_weights[2],
        },
        "uav_count_results": ordered_results,
        "overall_ranking": overall_rows,
        "top_10_tuning_rows": tuning_rows[:10],
    }
    with (output_dir / "summary.json").open("w", encoding="utf-8") as summary_file:
        json.dump(summary_payload, summary_file, indent=2, sort_keys=True)

    build_report(
        tuned_weights=tuned_weights,
        reference_count=args.reference_count,
        train_seed_count=len(train_seeds),
        test_seed_count=len(test_seeds),
        uav_counts=uav_counts,
        overall_rows=overall_rows,
        uav_count_summary_rows=uav_count_summary_rows,
        significance_rows=significance_rows,
        output_path=output_dir / "report.md",
    )

    print(json.dumps(summary_payload, indent=2, sort_keys=True))
    print()
    print(f"Saved UAV-count sensitivity artifacts to {output_dir}")


if __name__ == "__main__":
    main()
