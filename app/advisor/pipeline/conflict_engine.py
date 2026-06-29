"""L3 — conflict detection on frozen state before mutation."""

from __future__ import annotations

import re

from app.advisor.orchestrator.hypothesis_conflict import (
    _memory_vertical,
    _summarize_prior_facts,
    _verticals_in_text,
)
from app.advisor.orchestrator.signals.v1 import _VERTICAL_SIGNALS
from app.advisor.pipeline.types import ConflictRecord, ConflictReport, ExtractedFacts
from app.advisor.types import ScoredMemoryLine, SessionMetadata

_EMPLOYEE_RE = re.compile(r"(\d[\d,]*)\s*(employees|staff|people)", re.I)


def _prior_vertical(meta: SessionMetadata, memory_lines: list[ScoredMemoryLine]) -> str | None:
    return meta.active_business_vertical or _memory_vertical(memory_lines) or meta.industry


def _prior_employee_count(
    memory_lines: list[ScoredMemoryLine],
) -> int | None:
    for line in memory_lines:
        if line.key == "employee_count" and line.confidence >= 0.5:
            try:
                return int(re.sub(r"[^\d]", "", line.value))
            except ValueError:
                continue
    return None


def _prior_systems(memory_lines: list[ScoredMemoryLine]) -> set[str]:
    systems: set[str] = set()
    for line in memory_lines:
        if line.key.startswith("system_") and line.confidence >= 0.5:
            systems.add(line.value.lower())
    return systems


def _prior_automation_manual(memory_lines: list[ScoredMemoryLine]) -> str | None:
    for line in memory_lines:
        if line.key == "planning_method" and "manual" in line.value.lower():
            return "manual"
        if line.key == "automation_level" and line.confidence >= 0.5:
            return line.value
    return None


def detect_conflicts(
    frozen_meta: SessionMetadata,
    memory_lines: list[ScoredMemoryLine],
    facts: ExtractedFacts,
    message: str,
) -> ConflictReport:
    """Compare proposed facts against frozen state — never uses post-extraction meta."""
    records: list[ConflictRecord] = []

    prior_v = _prior_vertical(frozen_meta, memory_lines)
    new_verticals = _verticals_in_text(message)
    if facts.proposed_vertical:
        new_verticals.add(facts.proposed_vertical)

    if prior_v and new_verticals and prior_v not in new_verticals:
        conflicting = new_verticals - {prior_v}
        if conflicting:
            new_v = next(iter(conflicting))
            prior_facts = _summarize_prior_facts(memory_lines, frozen_meta)
            records.append(
                ConflictRecord(
                    kind="vertical_switch",
                    prior_value=prior_v,
                    new_value=new_v,
                    severity="hard",
                    clarification_question=(
                        f"Earlier you described a {prior_v} operation ({prior_facts}). "
                        f"Now you've mentioned being a {new_v} business. "
                        f"Are these separate business units, or should I update my understanding?"
                    ),
                    affected_keys=["industry", "active_business_vertical", "business_vertical"],
                )
            )

    prior_emp = _prior_employee_count(memory_lines)
    if prior_emp and facts.proposed_employee_count:
        ratio = max(prior_emp, facts.proposed_employee_count) / max(
            min(prior_emp, facts.proposed_employee_count), 1
        )
        if ratio >= 5:
            records.append(
                ConflictRecord(
                    kind="scale_mismatch",
                    prior_value=str(prior_emp),
                    new_value=str(facts.proposed_employee_count),
                    severity="hard",
                    clarification_question=(
                        f"Earlier you mentioned {prior_emp} employees, "
                        f"but now {facts.proposed_employee_count}. "
                        f"Which figure reflects the operation we're discussing?"
                    ),
                    affected_keys=["employee_count", "scale"],
                )
            )

    prior_auto = _prior_automation_manual(memory_lines)
    if prior_auto == "manual" and facts.claims_fully_automated:
        records.append(
            ConflictRecord(
                kind="automation_claim_vs_manual",
                prior_value="manual",
                new_value="fully_automated",
                severity="soft",
                clarification_question=(
                    "You mentioned manual processes earlier — has automation been "
                    "introduced since, or are some steps still manual?"
                ),
                affected_keys=["planning_method", "automation_level"],
            )
        )

    prior_systems = _prior_systems(memory_lines)
    new_systems = {s.lower() for s in facts.proposed_systems}
    if prior_systems and new_systems and not prior_systems & new_systems:
        records.append(
            ConflictRecord(
                kind="system_switch",
                prior_value=", ".join(sorted(prior_systems)),
                new_value=", ".join(sorted(new_systems)),
                severity="soft",
                clarification_question=(
                    f"You mentioned {', '.join(prior_systems)} before, "
                    f"but now {', '.join(new_systems)}. "
                    f"Are you migrating systems or discussing a different unit?"
                ),
                affected_keys=["system_context"],
            )
        )

    hard = [r for r in records if r.severity == "hard"]
    clarification = hard[0].clarification_question if hard else (
        records[0].clarification_question if records else None
    )
    return ConflictReport(
        is_conflicted=bool(records),
        records=records,
        clarification_question=clarification,
        blocks_vertical_update=bool(hard),
    )
