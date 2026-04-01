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
