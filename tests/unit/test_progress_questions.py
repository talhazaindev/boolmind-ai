"""Progress question generation — evidence-grounded, not scenario-specific."""

from __future__ import annotations

from app.advisor.pipeline.evidence_extractor import extract_fact_graph
from app.advisor.pipeline.progress_questions import (
    is_generic_template_question,
    select_best_progress_question,
)
from app.advisor.pipeline.turn_pipeline import TurnPipeline
from app.advisor.types import HypothesisSnapshot, SessionMetadata

LABOR_SERVICES_MESSAGE = (
    "We operate a 22-location veterinary services group. "
    "Revenue grew 31% over the last 12 months, but operating margins fell from 18% to 9%. "
    "Client complaints have increased noticeably, staff turnover is up, and appointment wait times "
    "have nearly doubled. We recently changed our compensation structure for veterinarians and "
    "opened six new locations. We're considering AI scheduling software because management "
    "believes scheduling may be the bottleneck."
)


def test_organizational_change_extracted() -> None:
    fg = extract_fact_graph(SessionMetadata(), HypothesisSnapshot(), message=LABOR_SERVICES_MESSAGE)
    changes = fg.facts_by_category("organizational_change")
    assert changes
    assert any("compensation" in c.normalized for c in changes)


def test_stated_hypothesis_not_stakeholder_theory() -> None:
    fg = extract_fact_graph(SessionMetadata(), HypothesisSnapshot(), message=LABOR_SERVICES_MESSAGE)
    beliefs = fg.facts_by_category("stated_hypothesis")
    theories = fg.facts_by_category("stakeholder_theory")
    assert beliefs
    assert not any("scheduling may be the bottleneck" in t.text for t in theories)


def test_progress_question_grounded_in_user_facts() -> None:
    fg = extract_fact_graph(SessionMetadata(), HypothesisSnapshot(), message=LABOR_SERVICES_MESSAGE)
    question, score = select_best_progress_question(fg)
    assert question
    assert score >= 0.65
    assert is_generic_template_question(question) is False
    q_lower = question.lower()
    assert "compensation" in q_lower or "changed" in q_lower
    assert any(term in q_lower for term in ("turnover", "margin", "complaint", "wait"))


def test_turn_pipeline_avoids_generic_handoffs_question() -> None:
    result = TurnPipeline.run(SessionMetadata(), LABOR_SERVICES_MESSAGE, [])
    q = result.snapshot.required_question
    assert q
    assert is_generic_template_question(q) is False
    assert "handoffs between teams" not in q.lower()


def test_generic_template_detection() -> None:
    assert is_generic_template_question(
        "What has changed most recently — timing, error rates, handoffs between teams?"
    )
    assert not is_generic_template_question(
        "After you changed compensation structure, did staff turnover shift materially?"
    )
