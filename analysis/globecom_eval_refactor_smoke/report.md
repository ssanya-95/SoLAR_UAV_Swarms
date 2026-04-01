# Globecom Evaluation Report

## Protocol

- Train seeds: `1`
- Test seeds: `1`
- Tuning scenarios: `base, traffic_heavy, mobility_high, shadowing_heavy`
- Tuned SLAR weights: `(w_geo, w_link, w_ld) = (0.4, 0.6, 0.0)`

## Overall Results

- `slar-tuned`: PDR `0.8803` +/- `0.0874`, latency `9.65` steps
- `slar-default`: PDR `0.8621` +/- `0.0945`
- `gpsr`: PDR `0.8409` +/- `0.1039`
- `aodv`: PDR `0.8530` +/- `0.1244`

## Interpretation

- Tuned SLAR records `0` significant PDR wins against `slar-default`, `gpsr`, and `aodv` across the scenario matrix.
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
