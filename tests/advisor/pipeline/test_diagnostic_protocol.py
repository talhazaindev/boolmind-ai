"""Unit tests for diagnostic_protocol — IssueTree and DiagnosticDepth."""

from __future__ import annotations

from app.advisor.pipeline.business_systems_models import (
    BusinessSystemsState,
    CausalGraph,
    CausalNode,
    ConfidenceState,
    Constraint,
    ConstraintProfile,
    OpportunityCostAssessment,
    RootCauseConfidence,
)
from app.advisor.pipeline.diagnostic_protocol import (
    BssDiagnosticSignals,
    DiagnosticDepth,
    DiagnosticPhase,
    IssueTree,
    bss_diagnostic_signals,
    issue_tree_from_session,
    issue_tree_to_dict,
    select_question_from_issue_tree,
    update_issue_tree,
)
from app.advisor.types import SessionMetadata


def test_diagnostic_depth_starts_at_zero() -> None:
    depth = DiagnosticDepth()
    assert depth.score == 0


def test_increments_cap_at_100() -> None:
    depth = DiagnosticDepth()
    depth.add_symptom_identified()
    depth.add_vertical_confirmed()
    depth.add_scale_confirmed()
    depth.add_root_cause_hypothesised()
    depth.add_root_cause_confirmed()
    depth.add_impact_quantified()
    depth.add_constraint_discovered()
    depth.add_timeline_signal()
    assert depth.score <= 100


def test_solution_gated_threshold() -> None:
    assert DiagnosticDepth(score=59).solution_gated is True
    assert DiagnosticDepth(score=60).solution_gated is False


def test_lead_capture_gated_threshold() -> None:
    assert DiagnosticDepth(score=39).lead_capture_gated is True
    assert DiagnosticDepth(score=40).lead_capture_gated is False


def test_phase_bands() -> None:
    assert DiagnosticDepth(score=0).phase == DiagnosticPhase.PROBLEM_IDENTIFICATION
    assert DiagnosticDepth(score=20).phase == DiagnosticPhase.SCOPE_CHARACTERISATION
    assert DiagnosticDepth(score=40).phase == DiagnosticPhase.ROOT_CAUSE_HYPOTHESIS
    assert DiagnosticDepth(score=60).phase == DiagnosticPhase.IMPACT_QUANTIFICATION
    assert DiagnosticDepth(score=75).phase == DiagnosticPhase.CONSTRAINT_DISCOVERY
    assert DiagnosticDepth(score=90).phase == DiagnosticPhase.SOLUTION_READINESS


def test_issue_tree_roundtrip() -> None:
    tree = IssueTree(
        goal="increase revenue",
        primary_symptom="inventory stockouts",
        open_branches=["confirm root cause"],
        resolved_branches=["vertical=retail"],
        current_phase=DiagnosticPhase.SCOPE_CHARACTERISATION,
    )
    meta = SessionMetadata(issue_tree=issue_tree_to_dict(tree))
    restored = issue_tree_from_session(meta)
    assert restored.goal == "increase revenue"
    assert restored.primary_symptom == "inventory stockouts"
    assert restored.open_branches == ["confirm root cause"]
    assert restored.resolved_branches == ["vertical=retail"]
    assert restored.current_phase == DiagnosticPhase.SCOPE_CHARACTERISATION


def test_update_issue_tree_open_branches() -> None:
    bss = BusinessSystemsState()
    meta = SessionMetadata(pain_point="stockouts")
    tree = update_issue_tree(IssueTree(), bss, meta, "we run out of stock often")
    assert any("vertical" in b.lower() or "industry" in b.lower() for b in tree.open_branches)
    assert tree.primary_symptom == "stockouts"


def test_bss_diagnostic_signals_mapping() -> None:
    bss = BusinessSystemsState(
        causal_graph=CausalGraph(
            nodes=[
                CausalNode(id="s1", kind="symptom", label="delivery delays"),
            ]
        ),
        confidence=ConfidenceState(
            root_causes=[
                RootCauseConfidence(cause_id="c1", label="manual routing", confidence=0.8),
            ],
            top_confidence=0.8,
            validation_ready=True,
        ),
        economic_drivers=["revenue_growth"],
        constraint_profile=ConstraintProfile(
            constraints=[
                Constraint(
                    type="ORGANIZATIONAL",
                    description="no dedicated ops team",
                )
            ]
        ),
        opportunity_ranking=[
            OpportunityCostAssessment(issue_id="i1", label="lost revenue", business_impact_score=0.7),
        ],
    )
    meta = SessionMetadata(pain_point="delays")
    signals = bss_diagnostic_signals(bss, meta)
    assert isinstance(signals, BssDiagnosticSignals)
    assert signals.symptom_identified is True
    assert signals.root_cause_hypothesised is True
    assert signals.root_cause_confirmed is True
    assert signals.impact_quantified is True
    assert signals.constraint_discovered is True


def test_select_question_from_issue_tree() -> None:
    tree = IssueTree(open_branches=["confirm industry/vertical"])
    question = select_question_from_issue_tree(tree)
    assert question is not None
    assert "?" in question

    tree_q = IssueTree(open_branches=["What workflow is slowest today?"])
    assert select_question_from_issue_tree(tree_q) == "What workflow is slowest today?"
