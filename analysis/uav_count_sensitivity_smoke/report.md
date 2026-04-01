# UAV-Count Sensitivity Report

## Protocol

- Train seeds: `2`
- Test seeds: `3`
- Reference tuning count: `20` UAVs
- Tuned SLAR weights: `(w_geo, w_link, w_ld) = (0.4, 0.6, 0.0)`
- Evaluated UAV counts: `8, 16, 24`
- Simulation volume fixed to the current default world bounds for every count.
- Traffic held fixed for every count: `flows=20`, `arrival_window=20`.

## Overall Results

- `slar-tuned`: PDR `0.6944` +/- `0.1954`, latency `10.21` steps
- `slar-default`: PDR `0.6944` +/- `0.1755`
- `gpsr`: PDR `0.6722` +/- `0.1814`
- `aodv`: PDR `0.5833` +/- `0.1792`

## UAV-Count Highlights

- Largest SLAR margin occurs at `24` UAVs, where the best competing baseline is `gpsr` and the PDR margin is `0.0167`.
- The SLAR margin stays broadly stable between moderate and high UAV counts, indicating limited saturation.
- At low UAV counts, the SLAR advantage is smaller, which is consistent with fewer forward candidates being available.

## Significant PDR Wins by UAV Count

- `8` UAVs: `0` significant PDR wins against the main baselines
- `16` UAVs: `0` significant PDR wins against the main baselines
- `24` UAVs: `0` significant PDR wins against the main baselines

## Artifacts

- `tables/tuning_results.csv`
- `tables/uav_count_summary.csv`
- `tables/overall_router_summary.csv`
- `tables/paired_significance_by_count.csv`
- `figures/pdr_vs_uavs.png`
- `figures/latency_vs_uavs.png`
- `figures/attempts_vs_uavs.png`
- `figures/success_rate_vs_uavs.png`
