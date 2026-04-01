# SLAR UAV Swarm Simulator

This package implements the routing framework described in `Globecom_proposal (3).pdf`:

- Section 2 channel model with log-distance path loss, temporally correlated log-normal shadowing, and Rician link success probability via `scipy.stats.ncx2`.
- Section 3 Kalman filter with a 6D constant-velocity state and normalized link duration prediction.
- Section 4 GPSR and AODV baselines.
- Section 5 SLAR scoring with the mandatory positive geographic-progress gate.

## Layout

- `slar_sim/config.py`: constants and derived channel terms.
- `slar_sim/channel.py`: Eq. (1) and Eq. (2).
- `slar_sim/kalman.py`: Eq. (3) through Eq. (12).
- `slar_sim/routing.py`: Eq. (15) through Eq. (18) and the SLAR score.
- `slar_sim/simulation.py`: packet queues, TTL handling, mobility, and the simulation loop.
- `slar_sim/optimization.py`: simple weight-grid search utility for Section 5.
- `scripts/weight_sensitivity.py`: reproducible sensitivity analysis across SLAR weight combinations.
- `main.py`: small runnable example.

## Run

```bash
python3 main.py --router slar --nodes 12 --steps 100 --seed 7
```

```bash
python3 scripts/weight_sensitivity.py --grid-step 0.1 --nodes 20 --steps 100 --seeds 20 --flows 20
```

```bash
python3 scripts/globecom_evaluation.py --grid-step 0.1 --train-seeds 8 --test-seeds 12
```

```bash
python3 scripts/uav_count_sensitivity.py --grid-step 0.1 --train-seeds 8 --test-seeds 12 --uav-counts 8,12,16,20,24,28,32
```

## Notes

- The proposal does not tabulate a single numeric communication range `R`, so the framework exposes `communication_range_m` as a configuration parameter with a default of `50.0` m.
- The proposal requires temporally correlated shadowing but does not specify a correlation coefficient, so `shadowing_correlation` is configurable and defaults to `0.9`.
