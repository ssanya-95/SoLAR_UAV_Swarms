# Globecom Evaluation Report

## Protocol

- Train seeds: `8`
- Test seeds: `12`
- Tuning scenarios: `base, traffic_heavy, mobility_high, shadowing_heavy`
- Tuned SLAR weights: `(w_geo, w_link, w_ld) = (0.2, 0.8, 0.0)`

## Overall Results

- `slar-tuned`: PDR `0.8115` +/- `0.0297`, latency `9.42` steps
- `slar-default`: PDR `0.7878` +/- `0.0316`
- `gpsr`: PDR `0.7654` +/- `0.0313`
- `aodv`: PDR `0.7535` +/- `0.0358`

## Interpretation

- Tuned SLAR records `9` significant PDR wins against `slar-default`, `gpsr`, and `aodv` across the scenario matrix.
- The strongest weights should be fixed before the final paper experiments; they should not be retuned on the reported test seeds.
- The generated tables and plots are intended for internal iteration and figure drafting, not final publication formatting.

## Artifacts

- `tables/tuning_results.csv`
- `tables/scenario_summary.csv`
- `tables/overall_router_summary.csv`
- `tables/paired_significance.csv`
- `figures/tuning_heatmap.png`
- `figures/pdr_by_scenario.png`
- `figures/latency_by_scenario.png`
- `figures/attempts_by_scenario.png`
