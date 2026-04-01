from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import math
from typing import TYPE_CHECKING

import numpy as np

from .config import SimulationConfig
from .packet import Packet

if TYPE_CHECKING:
    from .simulation import SimulationSnapshot


class Router:
    def __init__(self, config: SimulationConfig) -> None:
        self.config = config

    def select_next_hop(
        self,
        current_node: int,
        packet: Packet,
        snapshot: "SimulationSnapshot",
        step_index: int,
    ) -> int | None:
        raise NotImplementedError

    def on_transmission_result(
        self,
        current_node: int,
        next_hop: int | None,
        packet: Packet,
        success: bool,
        step_index: int,
    ) -> None:
        return None

    @staticmethod
    def forward_candidates(current_node: int, dst: int, snapshot: "SimulationSnapshot") -> list[int]:
        current_distance = snapshot.distance_matrix[current_node, dst]
        candidates: list[int] = []
        for neighbor in np.flatnonzero(snapshot.adjacency_matrix[current_node]):
            if snapshot.distance_matrix[neighbor, dst] < current_distance:
                candidates.append(int(neighbor))
        return candidates


class GPSRRouter(Router):
    """Eq. (15)-(16): greedy forwarding with strictly positive progress."""

    def select_next_hop(
        self,
        current_node: int,
        packet: Packet,
        snapshot: "SimulationSnapshot",
        step_index: int,
    ) -> int | None:
        del step_index
        candidates = self.forward_candidates(current_node, packet.dst, snapshot)
        if not candidates:
            return None
        return min(candidates, key=lambda neighbor: snapshot.distance_matrix[neighbor, packet.dst])


@dataclass
class RouteCacheEntry:
    next_hop: int
    expires_at_step: int


class AODVRouter(Router):
    """Eq. (17)-(18): reactive BFS on the instantaneous unit-disk graph."""

    def __init__(self, config: SimulationConfig) -> None:
        super().__init__(config)
        self.route_cache: dict[tuple[int, int], RouteCacheEntry] = {}

    def select_next_hop(
        self,
        current_node: int,
        packet: Packet,
        snapshot: "SimulationSnapshot",
        step_index: int,
    ) -> int | None:
        key = (current_node, packet.dst)
        cached = self.route_cache.get(key)
        if cached is not None:
            if cached.expires_at_step > step_index and snapshot.adjacency_matrix[current_node, cached.next_hop]:
                return cached.next_hop
            self.route_cache.pop(key, None)

        next_hop = self._bfs_first_hop(current_node, packet.dst, snapshot.adjacency_matrix)
        if next_hop is None:
            return None

        self.route_cache[key] = RouteCacheEntry(
            next_hop=next_hop,
            expires_at_step=step_index + self.config.aodv_cache_steps,
        )
        return next_hop

    def on_transmission_result(
        self,
        current_node: int,
        next_hop: int | None,
        packet: Packet,
        success: bool,
        step_index: int,
    ) -> None:
        del step_index
        if success or next_hop is None:
            return
        key = (current_node, packet.dst)
        cached = self.route_cache.get(key)
        if cached is not None and cached.next_hop == next_hop:
            self.route_cache.pop(key, None)

    def _bfs_first_hop(self, src: int, dst: int, adjacency: np.ndarray) -> int | None:
        if src == dst:
            return dst

        visited = np.zeros(adjacency.shape[0], dtype=bool)
        parents: dict[int, int] = {}
        queue: deque[int] = deque([src])
        visited[src] = True

        while queue:
            node = queue.popleft()
            for neighbor in np.flatnonzero(adjacency[node]):
                neighbor = int(neighbor)
                if visited[neighbor]:
                    continue
                visited[neighbor] = True
                parents[neighbor] = node
                if neighbor == dst:
                    return self._reconstruct_first_hop(src, dst, parents)
                queue.append(neighbor)

        return None

    @staticmethod
    def _reconstruct_first_hop(src: int, dst: int, parents: dict[int, int]) -> int | None:
        node = dst
        while node in parents and parents[node] != src:
            node = parents[node]
        if node not in parents and node != dst:
            return None
        return node if node != dst or parents.get(node) == src else None


class SLARRouter(Router):
    """Section 5: geo-progress gate plus link-quality scoring."""

    def __init__(
        self,
        config: SimulationConfig,
        weights: tuple[float, float, float] | None = None,
    ) -> None:
        super().__init__(config)
        self.weights = weights if weights is not None else config.slar_weights
        self.config.validate_slar_weights(self.weights)

    def select_next_hop(
        self,
        current_node: int,
        packet: Packet,
        snapshot: "SimulationSnapshot",
        step_index: int,
    ) -> int | None:
        del step_index
        dst = packet.dst
        candidates = self.forward_candidates(current_node, dst, snapshot)
        if not candidates:
            return None

        current_distance = snapshot.distance_matrix[current_node, dst]
        raw_geo_scores: dict[int, float] = {}
        for neighbor in candidates:
            progress = current_distance - snapshot.distance_matrix[neighbor, dst]
            raw_geo_scores[neighbor] = progress / max(current_distance, 1e-12)

        geo_norm_scores = self._normalize_geo_scores(raw_geo_scores)
        w_geo, w_link, w_ld = self.weights

        best_neighbor: int | None = None
        best_tuple: tuple[float, float, float, float] | None = None
        for neighbor in candidates:
            link_score = float(snapshot.link_prob_matrix[current_node, neighbor])
            ld_score = float(snapshot.link_duration_matrix[current_node, neighbor])
            total_score = (w_geo * geo_norm_scores[neighbor]) + (w_link * link_score) + (w_ld * ld_score)

            # Tie-breakers preserve the intended preference order.
            candidate_tuple = (
                total_score,
                raw_geo_scores[neighbor],
                link_score,
                -float(neighbor),
            )
            if best_tuple is None or candidate_tuple > best_tuple:
                best_tuple = candidate_tuple
                best_neighbor = neighbor

        return best_neighbor

    @staticmethod
    def _normalize_geo_scores(raw_geo_scores: dict[int, float]) -> dict[int, float]:
        if len(raw_geo_scores) == 1:
            neighbor = next(iter(raw_geo_scores))
            return {neighbor: 1.0}

        minimum = min(raw_geo_scores.values())
        maximum = max(raw_geo_scores.values())
        if math.isclose(minimum, maximum):
            return {neighbor: 1.0 for neighbor in raw_geo_scores}
        return {
            neighbor: (score - minimum) / (maximum - minimum)
            for neighbor, score in raw_geo_scores.items()
        }


class SLARGeoRouter(SLARRouter):
    """Containment baseline from Section 4.3: SLAR with only the geo term."""

    def __init__(self, config: SimulationConfig) -> None:
        super().__init__(config=config, weights=(1.0, 0.0, 0.0))
