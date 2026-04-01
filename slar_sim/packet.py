from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Packet:
    packet_id: int
    src: int
    dst: int
    ttl: int
    created_step: int
    hops: int = 0
    delivered_step: int | None = None

    def decrement_ttl(self) -> bool:
        self.ttl -= 1
        return self.ttl <= 0
