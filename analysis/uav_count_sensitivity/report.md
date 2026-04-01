# UAV-Count Sensitivity Report

## Protocol

- Train seeds: `8`
- Test seeds: `12`
- Reference tuning count: `20` UAVs
- Tuned SLAR weights: `(w_geo, w_link, w_ld) = (0.2, 0.8, 0.0)`
- Evaluated UAV counts: `8, 12, 16, 20, 24, 28, 32`
- Simulation volume fixed to the current default world bounds for every count.
- Traffic held fixed for every count: `flows=20`, `arrival_window=20`.

## Overall Results

- `slar-tuned`: PDR `0.7464` +/- `0.0582`, latency `9.63` steps
- `slar-default`: PDR `0.7393` +/- `0.0578`
- `gpsr`: PDR `0.7155` +/- `0.0574`
- `aodv`: PDR `0.6744` +/- `0.0651`

## UAV-Count Highlights

- Largest SLAR margin occurs at `16` UAVs, where the best competing baseline is `gpsr` and the PDR margin is `0.0875`.
- The SLAR margin stays broadly stable between moderate and high UAV counts, indicating limited saturation.
- At low UAV counts, the SLAR advantage is smaller, which is consistent with fewer forward candidates being available.

## Significant PDR Wins by UAV Count

- `8` UAVs: `1` significant PDR wins against the main baselines
- `12` UAVs: `1` significant PDR wins against the main baselines
- `16` UAVs: `3` significant PDR wins against the main baselines
- `20` UAVs: `0` significant PDR wins against the main baselines
- `24` UAVs: `0` significant PDR wins against the main baselines
- `28` UAVs: `2` significant PDR wins against the main baselines
- `32` UAVs: `0` significant PDR wins against the main baselines

## Artifacts

- `tables/tuning_results.csv`
- `tables/uav_count_summary.csv`
- `tables/overall_router_summary.csv`
- `tables/paired_significance_by_count.csv`
- `figures/pdr_vs_uavs.png`
- `figures/latency_vs_uavs.png`
- `figures/attempts_vs_uavs.png`
- `figures/success_rate_vs_uavs.png`
