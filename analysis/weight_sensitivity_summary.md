# SLAR Weight Sensitivity Summary

Experiment:

- Grid step: `0.1`
- Nodes: `20`
- Steps per run: `100`
- Seeds: `20`
- Packets per seed: `20`
- Arrival window: first `20` steps

Baseline averages:

- `gpsr`: PDR `0.7150`, attempts `123.35`, success rate `0.3932`
- `aodv`: PDR `0.7225`, attempts `126.50`, success rate `0.3885`
- `slar-geo`: PDR `0.7150`, attempts `123.35`, success rate `0.3932`
- `slar-default (1/3,1/3,1/3)`: PDR `0.7825`, attempts `112.85`, success rate `0.4843`

Best weight combinations:

1. `(w_geo, w_link, w_ld) = (0.3, 0.4, 0.3)` with PDR `0.7900`
2. `(0.2, 0.3, 0.5)` with PDR `0.7900`
3. `(0.1, 0.9, 0.0)` with PDR `0.7875`
4. `(0.3, 0.5, 0.2)` with PDR `0.7875`
5. `(0.4, 0.6, 0.0)` with PDR `0.7850`

Observed trends:

- The strongest region is not geo-dominant. Good settings consistently put substantial mass on `w_link`.
- Moderate `w_ld` helps when paired with a non-trivial `w_link`; the best tied configuration is `(0.2, 0.3, 0.5)`.
- Purely geographic settings collapse back toward GPSR performance, as expected.
- The best tuned SLAR setting improves on the best baseline (`slar-default`) by `0.0075` absolute PDR.
- Several strong settings also reduce transmission attempts relative to the baselines, which means they are not buying PDR at the cost of excessive retries.

Artifacts:

- Full machine-readable output: `analysis/weight_sensitivity_full.json`
- Ranked table: `analysis/weight_sensitivity_full.csv`
