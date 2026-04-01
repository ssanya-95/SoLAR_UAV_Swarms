from __future__ import annotations

import argparse
import json
import numpy as np

from slar_sim import AODVRouter, GPSRRouter, Router, SLARGeoRouter, SLARRouter, SimulationConfig, SimulationLoop, build_random_nodes


def build_router(name: str, config: SimulationConfig) -> Router:
    if name == "gpsr":
        return GPSRRouter(config)
    if name == "aodv":
        return AODVRouter(config)
    if name == "slar":
        return SLARRouter(config)
    if name == "slar-geo":
        return SLARGeoRouter(config)
    raise ValueError(f"Unsupported router: {name}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the SLAR UAV-swarm simulation.")
    parser.add_argument("--router", choices=["gpsr", "aodv", "slar", "slar-geo"], default="slar")
    parser.add_argument("--nodes", type=int, default=12)
    parser.add_argument("--steps", type=int, default=100)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--flows", type=int, default=8, help="Number of packets injected at step 0.")
    args = parser.parse_args()

    config = SimulationConfig()
    nodes = build_random_nodes(num_nodes=args.nodes, config=config, seed=args.seed)
    router = build_router(args.router, config)
    simulation = SimulationLoop(config=config, nodes=nodes, router=router, seed=args.seed)

    flow_rng = np.random.default_rng(args.seed + 1)
    for _ in range(args.flows):
        src, dst = flow_rng.choice(args.nodes, size=2, replace=False)
        simulation.inject_packet(src=int(src), dst=int(dst))

    metrics = simulation.run(num_steps=args.steps)
    print(json.dumps(metrics.as_dict(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
