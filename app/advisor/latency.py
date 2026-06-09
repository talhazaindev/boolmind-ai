"""Latency audit helpers (Phase 4)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LatencyTracker:
    marks: dict[str, float] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)

    def mark(self, name: str) -> None:
        self.marks[name] = time.perf_counter()

    def elapsed_ms(self, start: str, end: str) -> float:
        if start not in self.marks or end not in self.marks:
            return 0.0
        return (self.marks[end] - self.marks[start]) * 1000

    def record(self, namespace: str, first_token_ms: float, full_ms: float) -> None:
        self.events.append(
            {
                "namespace": namespace,
                "first_token_ms": round(first_token_ms, 1),
                "full_response_ms": round(full_ms, 1),
            }
        )

    def p95(self, field_name: str) -> float:
        vals = sorted(e.get(field_name, 0) for e in self.events)
        if not vals:
            return 0.0
        idx = int(len(vals) * 0.95) - 1
        return vals[max(0, idx)]
