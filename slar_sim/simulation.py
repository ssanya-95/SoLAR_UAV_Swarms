from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np

from .channel import ChannelModel
from .config import SimulationConfig
from .node import UAVNode
from .packet import Packet
from .routing import Router


@dataclass(frozen=True)
class SimulationSnapshot:
    step_index: int
    positions: np.ndarray
    estimated_positions: np.ndarray
    estimated_velocities: np.ndarray
    distance_matrix: np.ndarray
    adjacency_matrix: np.ndarray
    link_prob_matrix: np.ndarray
    link_duration_matrix: np.ndarray


@dataclass
class SimulationMetrics:
    generated_packets: int = 0
    delivered_packets: int = 0
    dropped_packets: int = 0
    transmission_attempts: int = 0
    transmission_successes: int = 0
    total_delivery_latency_steps: int = 0
    total_delivered_hops: int = 0
    total_queue_occupancy: int = 0
    queue_samples: int = 0
    peak_total_queue_length: int = 0

    @property
    def packet_delivery_ratio(self) -> float:
        if self.generated_packets == 0:
            return 0.0
        return self.delivered_packets / self.generated_packets

    @property
    def avg_delivery_latency_steps(self) -> float:
        if self.delivered_packets == 0:
            return 0.0
        return self.total_delivery_latency_steps / self.delivered_packets

    @property
    def avg_hops_per_delivered(self) -> float:
        if self.delivered_packets == 0:
            return 0.0
        return self.total_delivered_hops / self.delivered_packets

    @property
    def avg_total_queue_length(self) -> float:
        if self.queue_samples == 0:
            return 0.0
        return self.total_queue_occupancy / self.queue_samples

    @property
    def avg_success_rate(self) -> float:
        if self.transmission_attempts == 0:
            return 0.0
        return self.transmission_successes / self.transmission_attempts

    def as_dict(self) -> dict[str, float | int]:
        return {
            "generated_packets": self.generated_packets,
            "delivered_packets": self.delivered_packets,
            "dropped_packets": self.dropped_packets,
            "transmission_attempts": self.transmission_attempts,
            "transmission_successes": self.transmission_successes,
            "packet_delivery_ratio": self.packet_delivery_ratio,
            "avg_delivery_latency_steps": self.avg_delivery_latency_steps,
            "avg_hops_per_delivered": self.avg_hops_per_delivered,
            "avg_total_queue_length": self.avg_total_queue_length,
            "avg_success_rate": self.avg_success_rate,
            "peak_total_queue_length": self.peak_total_queue_length,
        }


class SimulationLoop:
    def __init__(
        self,
        config: SimulationConfig,
        nodes: Iterable[UAVNode],
        router: Router,
        seed: int | None = None,
    ) -> None:
        self.config = config
        self.nodes = {node.node_id: node for node in nodes}
        self.router = router
        self.step_index = 0
        self.packet_counter = 0
        self.metrics = SimulationMetrics()
        self.rng = np.random.default_rng(seed)

        self._validate_node_ids()
        self.channel = ChannelModel(config=config, num_nodes=len(self.nodes), rng=self.rng)

    def inject_packet(self, src: int, dst: int, ttl: int | None = None) -> Packet:
        if src == dst:
            raise ValueError("src and dst must be different.")
        packet = Packet(
            packet_id=self.packet_counter,
            src=src,
            dst=dst,
            ttl=self.config.default_packet_ttl if ttl is None else ttl,
            created_step=self.step_index,
        )
        self.packet_counter += 1
        self.metrics.generated_packets += 1
        self.nodes[src].enqueue(packet)
        return packet

    def build_snapshot(self) -> SimulationSnapshot:
        ordered_nodes = [self.nodes[index] for index in sorted(self.nodes)]
        positions = np.vstack([node.position for node in ordered_nodes])
        estimated_positions = np.vstack([node.estimated_position for node in ordered_nodes])
        estimated_velocities = np.vstack([node.estimated_velocity for node in ordered_nodes])

        distances = self.channel.distance_matrix(positions)
        adjacency = self.channel.adjacency_matrix(distances)
        link_probabilities = self.channel.link_success_probability_matrix(distances)
        link_duration = compute_link_duration_matrix(
            estimated_positions=estimated_positions,
            estimated_velocities=estimated_velocities,
            config=self.config,
        )

        return SimulationSnapshot(
            step_index=self.step_index,
            positions=positions,
            estimated_positions=estimated_positions,
            estimated_velocities=estimated_velocities,
            distance_matrix=distances,
            adjacency_matrix=adjacency,
            link_prob_matrix=link_probabilities,
            link_duration_matrix=link_duration,
        )

    def step(self) -> SimulationSnapshot:
        for node in self._ordered_nodes():
            node.advance_true_state(rng=self.rng, config=self.config)

        self.channel.step_shadowing()

        for node in self._ordered_nodes():
            node.sense_and_update_filter(rng=self.rng, config=self.config)

        snapshot = self.build_snapshot()

        starting_packet_ids = {
            packet.packet_id
            for node in self._ordered_nodes()
            for packet in node.queue
        }
        forwarded_packet_ids: set[int] = set()
        starting_heads = [
            (node.node_id, node.queue[0].packet_id)
            for node in self._ordered_nodes()
            if node.queue
        ]

        for node_id, head_packet_id in starting_heads:
            node = self.nodes[node_id]
            if not node.queue or node.queue[0].packet_id != head_packet_id:
                continue

            packet = node.queue[0]
            if packet.dst == node_id:
                node.queue.popleft()
                packet.delivered_step = self.step_index
                forwarded_packet_ids.add(packet.packet_id)
                self.metrics.delivered_packets += 1
                self.metrics.total_delivery_latency_steps += packet.delivered_step - packet.created_step
                self.metrics.total_delivered_hops += packet.hops
                continue

            next_hop = self.router.select_next_hop(node_id, packet, snapshot, self.step_index)
            if next_hop is None:
                continue

            self.metrics.transmission_attempts += 1
            success = False
            if snapshot.adjacency_matrix[node_id, next_hop]:
                success = self.channel.sample_link_success(node_id, next_hop, snapshot.link_prob_matrix)

            self.router.on_transmission_result(
                current_node=node_id,
                next_hop=next_hop,
                packet=packet,
                success=success,
                step_index=self.step_index,
            )

            if not success:
                continue

            popped = node.queue.popleft()
            if popped.packet_id != packet.packet_id:
                raise RuntimeError("Queue head changed unexpectedly during transmission.")

            packet.hops += 1
            forwarded_packet_ids.add(packet.packet_id)
            self.metrics.transmission_successes += 1

            if next_hop == packet.dst:
                packet.delivered_step = self.step_index
                self.metrics.delivered_packets += 1
                self.metrics.total_delivery_latency_steps += packet.delivered_step - packet.created_step
                self.metrics.total_delivered_hops += packet.hops
            else:
                self.nodes[next_hop].enqueue(packet)

        self._decrement_ttl_for_queued_packets(
            starting_packet_ids=starting_packet_ids,
            forwarded_packet_ids=forwarded_packet_ids,
        )
        self._sample_queue_occupancy()
        self.step_index += 1
        return snapshot

    def run(
        self,
        num_steps: int,
        packet_schedule: dict[int, list[tuple[int, int, int | None]]] | None = None,
    ) -> SimulationMetrics:
        schedule = packet_schedule or {}
        for _ in range(num_steps):
            for src, dst, ttl in schedule.get(self.step_index, []):
                self.inject_packet(src=src, dst=dst, ttl=ttl)
            self.step()
        return self.metrics

    def _decrement_ttl_for_queued_packets(
        self,
        starting_packet_ids: set[int],
        forwarded_packet_ids: set[int],
    ) -> None:
        age_ids = starting_packet_ids - forwarded_packet_ids
        for node in self._ordered_nodes():
            retained_packets = []
            while node.queue:
                packet = node.queue.popleft()
                if packet.packet_id in age_ids and packet.decrement_ttl():
                    self.metrics.dropped_packets += 1
                    continue
                retained_packets.append(packet)
            for packet in retained_packets:
                node.queue.append(packet)

    def _ordered_nodes(self) -> list[UAVNode]:
        return [self.nodes[index] for index in sorted(self.nodes)]

    def _sample_queue_occupancy(self) -> None:
        total_queue_length = sum(len(node.queue) for node in self._ordered_nodes())
        self.metrics.total_queue_occupancy += total_queue_length
        self.metrics.queue_samples += 1
        self.metrics.peak_total_queue_length = max(self.metrics.peak_total_queue_length, total_queue_length)

    def _validate_node_ids(self) -> None:
        expected = list(range(len(self.nodes)))
        actual = sorted(self.nodes)
        if actual != expected:
            raise ValueError(f"Node IDs must be contiguous starting at 0. Found {actual}.")


def compute_link_duration_matrix(
    estimated_positions: np.ndarray,
    estimated_velocities: np.ndarray,
    config: SimulationConfig,
) -> np.ndarray:
    num_nodes = estimated_positions.shape[0]
    horizon = config.link_duration_horizon_steps
    link_duration_steps = np.full((num_nodes, num_nodes), horizon, dtype=int)

    for horizon_step in range(1, horizon + 1):
        # Eq. (12): constant-velocity projection over k future steps.
        projected_positions = estimated_positions + (horizon_step * config.dt_s * estimated_velocities)
        deltas = projected_positions[:, None, :] - projected_positions[None, :, :]
        projected_distances = np.linalg.norm(deltas, axis=-1)

        # Eq. (13): first horizon step where the distance exceeds R, minus one.
        breaking_now = (projected_distances > config.communication_range_m) & (link_duration_steps == horizon)
        link_duration_steps[breaking_now] = horizon_step - 1

    # Eq. (14): normalize LD by H.
    normalized = link_duration_steps.astype(float) / float(horizon)
    np.fill_diagonal(normalized, 0.0)
    return normalized


def build_random_nodes(
    num_nodes: int,
    config: SimulationConfig,
    seed: int | None = None,
) -> list[UAVNode]:
    rng = np.random.default_rng(seed)
    bounds = np.asarray(config.world_bounds_m, dtype=float)

    positions = rng.uniform(low=0.0, high=1.0, size=(num_nodes, 3)) * bounds
    directions = rng.normal(0.0, 1.0, size=(num_nodes, 3))
    direction_norms = np.linalg.norm(directions, axis=1, keepdims=True)
    direction_norms[direction_norms == 0.0] = 1.0
    directions = directions / direction_norms

    speeds = rng.uniform(config.min_speed_mps, config.max_speed_mps, size=(num_nodes, 1))
    velocities = directions * speeds

    return [
        UAVNode.from_state(
            node_id=node_id,
            position=positions[node_id],
            velocity=velocities[node_id],
            config=config,
        )
        for node_id in range(num_nodes)
    ]
