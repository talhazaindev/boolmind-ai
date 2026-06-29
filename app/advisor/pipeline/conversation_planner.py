"""
Conversation Planner — multi-turn lookahead for diagnostic sequencing.

Runs at the start of each turn (before L2-L8) and produces a TurnPlan
that guides question selection for this turn and primes the next 2 turns.

The planner is DETERMINISTIC — no LLM call, no external service.
It operates on the current session state and information gaps.

Information gap priority (in order):
  1. No vertical identified → ask industry question this turn
  2. No scale identified → ask team size this turn
  3. No primary symptom confirmed → ask problem area this turn
  4. Symptom known, root cause unknown → ask discriminating question this turn
  5. Root cause known, impact unknown → ask impact question this turn
  6. Impact known, constraint unknown → ask constraint question this turn
  7. All above known → shift to solution readiness / solutioning

User patience model:
  - message_count 1-3: Pure discovery. No solution hints. No lead capture.
  - message_count 4-7: Hypothesis testing. Can reference similar patterns.
  - message_count 8+: Solutioning allowed if depth >= 60. Lead capture if depth >= 40.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.advisor.knowledge.ontology_schema import BusinessArchetype
from app.advisor.pipeline.diagnostic_protocol import (
    DiagnosticDepth,
    DiagnosticPhase,
    issue_tree_from_session,
)
from app.advisor.types import SessionMetadata


@dataclass
class TurnPlan:
    """
    Output of ConversationPlanner for a single turn.

    Attributes:
        this_turn_priority: What information gap to address this turn.
        next_turn_hints: What to prepare for turns N+1 and N+2.
        allow_case_reference: Whether to include a case_hook in the LLM prompt.
        allow_solution_hint: Whether to allow the LLM to mention solution direction.
        patience_level: 'early', 'mid', 'late' — controls LLM tone instructions.
        force_discovery_mode: True = override router to DISCOVERY regardless of readiness.
    """

    this_turn_priority: str
    next_turn_hints: list[str] = field(default_factory=list)
    allow_case_reference: bool = False
    allow_solution_hint: bool = False
    patience_level: str = "early"  # 'early' | 'mid' | 'late'
    force_discovery_mode: bool = False


def _has_vertical(meta: SessionMetadata) -> bool:
    return bool(meta.active_business_vertical or meta.industry)


def _has_scale(meta: SessionMetadata) -> bool:
    if meta.data_context:
        return True
    return any(
        line.key in ("employee_count", "scale") for line in meta.business_memory_lines
    )


def _has_primary_symptom(meta: SessionMetadata) -> bool:
    if meta.pain_point:
        return True
    tree = issue_tree_from_session(meta)
    return bool(tree.primary_symptom)


def _default_turn_plan() -> TurnPlan:
    return TurnPlan(
        this_turn_priority="identify_vertical",
        next_turn_hints=["identify_scale", "identify_primary_symptom"],
        force_discovery_mode=True,
    )


class ConversationPlanner:
    """Deterministic multi-turn diagnostic sequencer."""

    def plan(
        self,
        session_metadata: SessionMetadata,
        depth: DiagnosticDepth,
        matched_archetypes: list[BusinessArchetype],
        message_count: int,
    ) -> TurnPlan:
        """
        Produce a TurnPlan for the current turn.

        Args:
            session_metadata: Full session state.
            depth: Current DiagnosticDepth.
            matched_archetypes: Archetypes matched this turn.
            message_count: Number of messages in this conversation so far.
        """
        try:
            return self._plan_impl(
                session_metadata,
                depth,
                matched_archetypes,
                message_count,
            )
        except Exception:
            return _default_turn_plan()

    def _plan_impl(
        self,
        session_metadata: SessionMetadata,
        depth: DiagnosticDepth,
        matched_archetypes: list[BusinessArchetype],
        message_count: int,
    ) -> TurnPlan:
        if message_count <= 3:
            patience = "early"
        elif message_count <= 7:
            patience = "mid"
        else:
            patience = "late"

        gap = self._identify_primary_gap(session_metadata, depth)
        next_hints = self._project_next_gaps(session_metadata, depth, gap)

        allow_case = patience in ("mid", "late") and len(matched_archetypes) > 0
        allow_solution = not depth.solution_gated and patience == "late"
        force_discovery = patience == "early" or depth.solution_gated

        return TurnPlan(
            this_turn_priority=gap,
            next_turn_hints=next_hints,
            allow_case_reference=allow_case,
            allow_solution_hint=allow_solution,
            patience_level=patience,
            force_discovery_mode=force_discovery,
        )

    def _identify_primary_gap(
        self,
        session_metadata: SessionMetadata,
        depth: DiagnosticDepth,
    ) -> str:
        if not _has_vertical(session_metadata):
            return "identify_vertical"
        if not _has_scale(session_metadata):
            return "identify_scale"
        if not _has_primary_symptom(session_metadata):
            return "identify_primary_symptom"
        if depth.phase == DiagnosticPhase.ROOT_CAUSE_HYPOTHESIS:
            return "confirm_root_cause"
        if depth.phase == DiagnosticPhase.IMPACT_QUANTIFICATION:
            return "quantify_impact"
        if depth.phase == DiagnosticPhase.CONSTRAINT_DISCOVERY:
            return "discover_constraint"
        return "solution_readiness"

    def _project_next_gaps(
        self,
        session_metadata: SessionMetadata,
        depth: DiagnosticDepth,
        current_gap: str,
    ) -> list[str]:
        del session_metadata, depth
        gap_sequence = [
            "identify_vertical",
            "identify_scale",
            "identify_primary_symptom",
            "confirm_root_cause",
            "quantify_impact",
            "discover_constraint",
            "solution_readiness",
        ]
        try:
            idx = gap_sequence.index(current_gap)
            return gap_sequence[idx + 1 : idx + 3]
        except (ValueError, IndexError):
            return []
