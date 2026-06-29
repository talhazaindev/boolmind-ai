"""Unit tests for hypothesis_question_engine — archetype-informed question selection."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.advisor.knowledge.ontology_loader import _load_archetypes
from app.advisor.pipeline.diagnostic_protocol import DiagnosticDepth, DiagnosticPhase, IssueTree
from app.advisor.pipeline.hypothesis_question_engine import (
    _PHASE_FALLBACK_QUESTIONS,
    select_hypothesis_question,
)
from app.advisor.pipeline.question_ledger import normalize_question_fingerprint
from app.advisor.pipeline.turn_pipeline import TurnPipeline
from app.advisor.types import SessionMetadata


def _archetype_by_id(archetype_id: str):
    for arch in _load_archetypes():
        if arch.id == archetype_id:
            return arch
    raise KeyError(archetype_id)


def test_phase_fallback_problem_identification() -> None:
    depth = DiagnosticDepth(score=0)
    assert depth.phase == DiagnosticPhase.PROBLEM_IDENTIFICATION

    q = select_hypothesis_question(
        matched_scored=[],
        issue_tree=IssueTree(),
        depth=depth,
        already_asked=set(),
    )
    expected = _PHASE_FALLBACK_QUESTIONS[DiagnosticPhase.PROBLEM_IDENTIFICATION][0]
    assert q == expected


def test_lead_leakage_discriminating_question() -> None:
    lead_leakage = _archetype_by_id("lead_leakage")
    q = select_hypothesis_question(
        matched_scored=[(0.72, lead_leakage)],
        issue_tree=IssueTree(),
        depth=DiagnosticDepth(score=0),
        already_asked=set(),
    )
    assert q == lead_leakage.discriminating_question
    assert "new lead comes in today" in (q or "").lower()


def test_dedup_skips_asked_question() -> None:
    lead_leakage = _archetype_by_id("lead_leakage")
    asked_fp = normalize_question_fingerprint(lead_leakage.discriminating_question)

    q = select_hypothesis_question(
        matched_scored=[(0.72, lead_leakage)],
        issue_tree=IssueTree(),
        depth=DiagnosticDepth(score=60),
        already_asked={asked_fp},
    )
    assert q != lead_leakage.discriminating_question
    assert q is not None
    impact_candidates = _PHASE_FALLBACK_QUESTIONS[DiagnosticPhase.IMPACT_QUANTIFICATION]
    assert q in impact_candidates


def test_empty_matches_returns_non_none_fallback() -> None:
    q = select_hypothesis_question(
        matched_scored=[],
        issue_tree=IssueTree(),
        depth=DiagnosticDepth(score=0),
        already_asked=set(),
    )
    assert q is not None


def test_never_raises_on_bad_input() -> None:
    assert select_hypothesis_question([], IssueTree(), DiagnosticDepth(), set()) is not None

    class _BadDepth:
        @property
        def score(self) -> int:
            raise RuntimeError("bad depth")

        @property
        def phase(self) -> DiagnosticPhase:
            return DiagnosticPhase.PROBLEM_IDENTIFICATION

    assert select_hypothesis_question([], IssueTree(), _BadDepth(), set()) is None  # type: ignore[arg-type]


def test_multi_archetype_picks_highest_similarity() -> None:
    lead_leakage = _archetype_by_id("lead_leakage")
    no_sales = _archetype_by_id("no_sales_visibility")

    q = select_hypothesis_question(
        matched_scored=[(0.55, no_sales), (0.62, lead_leakage)],
        issue_tree=IssueTree(),
        depth=DiagnosticDepth(score=40),
        already_asked=set(),
    )
    assert q == lead_leakage.discriminating_question


def test_high_confidence_single_match_uses_discriminating_question() -> None:
    lead_leakage = _archetype_by_id("lead_leakage")
    q = select_hypothesis_question(
        matched_scored=[(0.70, lead_leakage)],
        issue_tree=IssueTree(),
        depth=DiagnosticDepth(score=20),
        already_asked=set(),
    )
    assert q == lead_leakage.discriminating_question


def test_root_cause_confirmed_shifts_to_impact() -> None:
    lead_leakage = _archetype_by_id("lead_leakage")
    q = select_hypothesis_question(
        matched_scored=[(0.72, lead_leakage)],
        issue_tree=IssueTree(root_cause_confirmed=True),
        depth=DiagnosticDepth(score=75),
        already_asked=set(),
    )
    impact_candidates = _PHASE_FALLBACK_QUESTIONS[DiagnosticPhase.CONSTRAINT_DISCOVERY]
    assert q in impact_candidates


@patch("app.advisor.knowledge.ontology_loader.embed_query", side_effect=RuntimeError("embed down"))
def test_turn_pipeline_first_question_uses_phase_fallback(_mock_embed: object) -> None:
    import app.advisor.knowledge.ontology_loader as loader_mod

    loader_mod._cache_loaded = False
    loader_mod._archetypes = []
    loader_mod._archetype_embeddings = []

    result = TurnPipeline.run(SessionMetadata(), "hello", [])
    q = (result.snapshot.required_question or "").lower()
    assert q
    assert "friction" in q or "business problem" in q or "frustrating week" in q
    assert not q.startswith("what tools do you use")
