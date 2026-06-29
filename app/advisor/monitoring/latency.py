"""Latency audit helpers for advisor turns and tools."""

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


@dataclass
class TurnLatency:
    """Per-turn latency marks for eval, LLM rounds, tools, and synthesis."""

    marks: dict[str, float] = field(default_factory=dict)
    tool_rounds: int = 0
    llm_round_ms: list[float] = field(default_factory=list)
    tools: list[dict[str, Any]] = field(default_factory=list)
    synthesis_ms: float = 0.0

    def mark(self, name: str) -> None:
        self.marks[name] = time.perf_counter()

    def elapsed_ms(self, start: str, end: str) -> float:
        if start not in self.marks or end not in self.marks:
            return 0.0
        return round((self.marks[end] - self.marks[start]) * 1000, 1)

    def finish_llm_round(self, round_index: int) -> None:
        start_key = f"llm_r{round_index}_start"
        end_key = f"llm_r{round_index}_end"
        if start_key in self.marks and end_key in self.marks:
            self.llm_round_ms.append(self.elapsed_ms(start_key, end_key))

    def record_tool(self, name: str, duration_ms: float, *, parallel: bool = False) -> None:
        self.tools.append(
            {
                "tool": name,
                "duration_ms": round(duration_ms, 1),
                "parallel": parallel,
            }
        )

    def summary(self) -> dict[str, Any]:
        eval_ms = self.elapsed_ms("eval_start", "eval_end")
        llm_total = round(sum(self.llm_round_ms), 1)
        tools_total = round(sum(t["duration_ms"] for t in self.tools), 1)
        total_ms = self.elapsed_ms("turn_start", "turn_end")
        accounted = eval_ms + llm_total + tools_total + self.synthesis_ms
        overhead_ms = round(max(0.0, total_ms - accounted), 1)
        return {
            "eval_ms": eval_ms,
            "llm_rounds_ms": self.llm_round_ms,
            "llm_total_ms": llm_total,
            "tools": self.tools,
            "tools_total_ms": tools_total,
            "synthesis_ms": self.synthesis_ms,
            "overhead_ms": overhead_ms,
            "llm_first_token_ms": self.elapsed_ms("llm_r0_start", "first_token"),
            "tool_rounds": self.tool_rounds,
            "total_ms": total_ms,
        }
