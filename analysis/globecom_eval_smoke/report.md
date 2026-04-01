# Globecom Evaluation Report

## Protocol

- Train seeds: `2`
- Test seeds: `3`
- Tuning scenarios: `base, traffic_heavy, mobility_high, shadowing_heavy`
- Tuned SLAR weights: `(w_geo, w_link, w_ld) = (0.4, 0.6, 0.0)`

## Overall Results

- `slar-tuned`: PDR `0.8116` +/- `0.0715`, latency `7.43` steps
- `slar-default`: PDR `0.7995` +/- `0.0649`
- `gpsr`: PDR `0.8076` +/- `0.0676`
- `aodv`: PDR `0.7641` +/- `0.0853`

## Interpretation

- Tuned SLAR records `1` significant PDR wins against `slar-default`, `gpsr`, and `aodv` across the scenario matrix.
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
