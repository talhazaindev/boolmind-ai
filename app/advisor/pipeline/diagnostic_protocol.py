"""
Diagnostic Protocol — IssueTree and DiagnosticDepth.

The IssueTree is the structured output of the diagnostic reasoning process.
It is populated incrementally across turns. The DiagnosticDepth score (0-100)
measures how well the advisor understands the business problem.

Scoring bands:
  0-20:  Surface symptoms only. No root cause confirmed. Must keep discovering.
  21-40: Vertical + scale known. One symptom area identified.
  41-60: Root cause hypothesised. Impact partially quantified.
  61-80: Root cause confirmed. Constraint known. Solution space narrowing.
  81-100: Full diagnostic picture. Solution proposal and handoff appropriate.

The pipeline gates solution proposals behind diagnostic_depth >= 60.
The pipeline gates lead capture behind diagnostic_depth >= 40.

These gates are ADDITIVE to existing readiness gates — they do not replace them.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.advisor.pipeline.business_systems_models import BusinessSystemsState
    from app.advisor.types import SessionMetadata


class DiagnosticPhase(str, Enum):
    PROBLEM_IDENTIFICATION = "problem_identification"
    SCOPE_CHARACTERISATION = "scope_characterisation"
    ROOT_CAUSE_HYPOTHESIS = "root_cause_hypothesis"
    IMPACT_QUANTIFICATION = "impact_quantification"
    CONSTRAINT_DISCOVERY = "constraint_discovery"
    SOLUTION_READINESS = "solution_readiness"


@dataclass
class IssueTree:
    """
    A structured representation of the diagnosed business problem.

    Populated incrementally. Fields are None until confirmed by conversation
    evidence. The `open_branches` list drives question selection — the next
    question should address the first open branch.
    """

    goal: str | None = None
    primary_symptom: str | None = None
    root_cause_hypothesis: str | None = None
    root_cause_confirmed: bool = False
    impact_estimate: str | None = None
    constraint: str | None = None
    solution_category: str | None = None
    matched_archetype_id: str | None = None
    open_branches: list[str] = field(default_factory=list)
    resolved_branches: list[str] = field(default_factory=list)
    current_phase: DiagnosticPhase = DiagnosticPhase.PROBLEM_IDENTIFICATION


@dataclass
class DiagnosticDepth:
    """
    Cumulative score (0-100) measuring problem understanding depth.

    Each increment method is called by the pipeline when the corresponding
    signal is detected. Scores are additive and capped at 100.
    """

    score: int = 0

    @classmethod
    def from_session(cls, session_metadata: SessionMetadata) -> DiagnosticDepth:
        return cls(score=getattr(session_metadata, "diagnostic_depth", 0))

    def add_symptom_identified(self) -> None:
        """A specific symptom (not just 'things are hard') identified."""
        self.score = min(100, self.score + 10)

    def add_vertical_confirmed(self) -> None:
        """Vertical/industry confirmed by user (not just inferred)."""
        self.score = min(100, self.score + 8)

    def add_scale_confirmed(self) -> None:
        """Team size or volume confirmed."""
        self.score = min(100, self.score + 7)

    def add_root_cause_hypothesised(self) -> None:
        """A plausible root cause has been identified (not yet confirmed)."""
        self.score = min(100, self.score + 15)

    def add_root_cause_confirmed(self) -> None:
        """User confirmed or evidence strongly supports the root cause."""
        self.score = min(100, self.score + 20)

    def add_impact_quantified(self) -> None:
        """Business impact has a number or rough estimate."""
        self.score = min(100, self.score + 15)

    def add_constraint_discovered(self) -> None:
        """Why hasn't this been fixed before? Now known."""
        self.score = min(100, self.score + 10)

    def add_timeline_signal(self) -> None:
        """User indicated urgency or timeline (e.g. 'we need this before Q4')."""
        self.score = min(100, self.score + 15)

    @property
    def phase(self) -> DiagnosticPhase:
        if self.score < 20:
            return DiagnosticPhase.PROBLEM_IDENTIFICATION
        if self.score < 40:
            return DiagnosticPhase.SCOPE_CHARACTERISATION
        if self.score < 60:
            return DiagnosticPhase.ROOT_CAUSE_HYPOTHESIS
        if self.score < 75:
            return DiagnosticPhase.IMPACT_QUANTIFICATION
        if self.score < 90:
            return DiagnosticPhase.CONSTRAINT_DISCOVERY
        return DiagnosticPhase.SOLUTION_READINESS

    @property
    def solution_gated(self) -> bool:
        """True = too early to propose solutions. Stay in diagnostic mode."""
        return self.score < 60

    @property
    def lead_capture_gated(self) -> bool:
        """True = too early to ask for contact info."""
        return self.score < 40


@dataclass
class BssDiagnosticSignals:
    """Derived diagnostic signals from a BusinessSystemsState pass."""

    symptom_identified: bool = False
    root_cause_hypothesised: bool = False
    root_cause_confirmed: bool = False
    impact_quantified: bool = False
    constraint_discovered: bool = False


def bss_diagnostic_signals(
    bss: BusinessSystemsState,
    meta: SessionMetadata,
) -> BssDiagnosticSignals:
    """Map BSS output fields to diagnostic increment signals."""
    symptoms = [n for n in bss.causal_graph.nodes if n.kind == "symptom"]
    symptom_identified = bool(symptoms) or bool(meta.pain_point)

    root_causes = bss.confidence.root_causes
    root_cause_hypothesised = bool(root_causes)
    root_cause_confirmed = (
        bss.confidence.validation_ready or bss.confidence.top_confidence > 0.75
    )

    impact_quantified = bool(bss.economic_drivers) or bool(bss.opportunity_ranking)
    constraint_discovered = bool(bss.constraint_profile.constraints)

    return BssDiagnosticSignals(
        symptom_identified=symptom_identified,
        root_cause_hypothesised=root_cause_hypothesised,
        root_cause_confirmed=root_cause_confirmed,
        impact_quantified=impact_quantified,
        constraint_discovered=constraint_discovered,
    )


def issue_tree_from_session(meta: SessionMetadata) -> IssueTree:
    """Deserialize IssueTree from session metadata dict."""
    raw = getattr(meta, "issue_tree", None) or {}
    if not raw:
        return IssueTree()

    phase_raw = raw.get("current_phase", DiagnosticPhase.PROBLEM_IDENTIFICATION.value)
    try:
        phase = DiagnosticPhase(phase_raw)
    except ValueError:
        phase = DiagnosticPhase.PROBLEM_IDENTIFICATION

    return IssueTree(
        goal=raw.get("goal"),
        primary_symptom=raw.get("primary_symptom"),
        root_cause_hypothesis=raw.get("root_cause_hypothesis"),
        root_cause_confirmed=bool(raw.get("root_cause_confirmed", False)),
        impact_estimate=raw.get("impact_estimate"),
        constraint=raw.get("constraint"),
        solution_category=raw.get("solution_category"),
        matched_archetype_id=raw.get("matched_archetype_id"),
        open_branches=list(raw.get("open_branches") or []),
        resolved_branches=list(raw.get("resolved_branches") or []),
        current_phase=phase,
    )


def issue_tree_to_dict(tree: IssueTree) -> dict[str, Any]:
    """Serialize IssueTree for session metadata persistence."""
    data = asdict(tree)
    data["current_phase"] = tree.current_phase.value
    return data


def _append_resolved(resolved: list[str], entry: str) -> None:
    if entry not in resolved:
        resolved.append(entry)


def _build_open_branches(
    tree: IssueTree,
    bss: BusinessSystemsState,
    meta: SessionMetadata,
) -> list[str]:
    """Compute diagnostic gaps that still need exploration."""
    branches: list[str] = []

    vertical = meta.active_business_vertical or meta.industry
    if not vertical:
        branches.append("confirm industry/vertical")

    if not meta.data_context and not any(
        line.key in ("employee_count", "scale") for line in meta.business_memory_lines
    ):
        branches.append("confirm team size or operational volume")

    if not tree.primary_symptom and not meta.pain_point:
        branches.append("identify specific symptom or pain point")

    root_causes = bss.confidence.root_causes
    if bss.confidence.competing_within_margin and len(root_causes) >= 2:
        a, b = root_causes[0].label, root_causes[1].label
        branches.append(f"confirm root cause: {a} vs {b}")
    elif root_causes and not tree.root_cause_confirmed:
        branches.append(f"confirm root cause is {root_causes[0].label}")

    if not tree.impact_estimate and not bss.opportunity_ranking:
        branches.append("quantify business impact")

    if not tree.constraint and not bss.constraint_profile.constraints:
        branches.append("understand what has blocked a fix before")

    if bss.narrative_state.competing_cause and not tree.root_cause_confirmed:
        comp = bss.narrative_state.competing_cause
        top = bss.narrative_state.top_cause
        branch = f"confirm root cause is {top} vs {comp}"
        if branch not in branches:
            branches.append(branch)

    return branches


def update_issue_tree(
    tree: IssueTree,
    bss: BusinessSystemsState,
    meta: SessionMetadata,
    message: str,
    *,
    matched_archetype_id: str | None = None,
) -> IssueTree:
    """Incrementally update IssueTree from BSS output and session metadata."""
    del message  # reserved for future turn-specific branch logic

    goal = meta.primary_goal or meta.goals
    if goal:
        tree.goal = goal

    symptoms = [n for n in bss.causal_graph.nodes if n.kind == "symptom"]
    if symptoms:
        tree.primary_symptom = symptoms[0].label
    elif meta.pain_point and not tree.primary_symptom:
        tree.primary_symptom = meta.pain_point

    if bss.confidence.root_causes:
        tree.root_cause_hypothesis = bss.confidence.root_causes[0].label

    tree.root_cause_confirmed = bss.confidence.validation_ready

    if bss.opportunity_ranking:
        top = bss.opportunity_ranking[0]
        tree.impact_estimate = top.label
        if top.business_impact_score > 0:
            tree.impact_estimate = f"{top.label} (impact score {top.business_impact_score:.2f})"
    elif bss.economic_drivers and not tree.impact_estimate:
        tree.impact_estimate = bss.economic_drivers[0].replace("_", " ")

    if bss.constraint_profile.constraints:
        tree.constraint = bss.constraint_profile.constraints[0].description
    elif bss.narrative_state.constraint_summary and not tree.constraint:
        tree.constraint = bss.narrative_state.constraint_summary

    if meta.solution_category:
        tree.solution_category = meta.solution_category

    if matched_archetype_id:
        tree.matched_archetype_id = matched_archetype_id

    vertical = meta.active_business_vertical or meta.industry
    if vertical:
        _append_resolved(tree.resolved_branches, f"vertical={vertical}")
    if meta.data_context:
        _append_resolved(tree.resolved_branches, f"scale={meta.data_context}")
    if tree.primary_symptom:
        _append_resolved(tree.resolved_branches, f"symptom={tree.primary_symptom}")
    if tree.root_cause_confirmed and tree.root_cause_hypothesis:
        _append_resolved(
            tree.resolved_branches,
            f"root_cause_confirmed={tree.root_cause_hypothesis}",
        )

    tree.open_branches = _build_open_branches(tree, bss, meta)

    return tree


def select_question_from_issue_tree(tree: IssueTree) -> str | None:
    """Return the first open branch as a consultative question."""
    if not tree.open_branches:
        return None

    branch = tree.open_branches[0].strip()
    if not branch:
        return None

    if branch.endswith("?"):
        return branch

    lower = branch.lower()
    if lower.startswith("confirm "):
        subject = branch[8:]
        return f"Can you help me confirm whether {subject}?"

    if lower.startswith("understand "):
        subject = branch[11:]
        return f"What can you tell me about {subject}?"

    if lower.startswith("identify "):
        subject = branch[9:]
        return f"Could you help me {branch}?"

    if lower.startswith("quantify "):
        subject = branch[9:]
        return f"Do you have a rough sense of {subject}?"

    return f"Could you tell me more about {branch}?"
