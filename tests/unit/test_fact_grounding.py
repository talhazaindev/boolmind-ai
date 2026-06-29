"""Fact-grounding and discovery hedging tests."""

from app.advisor.orchestrator.fact_grounding import (
    build_hedged_contributors,
    question_assumes_unstated_facts,
    sanitize_ungrounded_assertions,
    user_stated_backlog,
)
from app.advisor.orchestrator.question_composer import compose_contextual_question
from app.advisor.pipeline.turn_pipeline import TurnPipeline
from app.advisor.types import ConversationContextGraph, HypothesisSnapshot, SessionMetadata

_BANK_TURN_1 = (
    "We're a regional bank with about 150 branches. Customer complaints have "
    "increased sharply over the last six months, and account opening times have "
    "gone from under a day to nearly a week."
)

_BANK_TURN_2 = (
    "Most applications are completed at the branch on the same day. The delay "
    "happens after submission. Compliance reviews have grown from a few hours to "
    "several days, and applications often move between branch staff, compliance "
    "analysts, and risk teams before a decision is made."
)


def test_no_backlog_without_user_statement() -> None:
    graph = ConversationContextGraph(pain_points=["compliance reviews are manual"])
    snap = HypothesisSnapshot(confirmed_facts=["compliance reviews are manual"])
    assert not user_stated_backlog(graph, snap)


def test_sanitize_removes_ungrounded_backlog_reference() -> None:
    body = (
        "You're seeing a clear compliance bottleneck. "
        "With the backlog you described, scheduling may be an issue."
    )
    meta = SessionMetadata()
    snap = HypothesisSnapshot(overall_confidence=0.55)
    graph = ConversationContextGraph()
    cleaned = sanitize_ungrounded_assertions(body, "DISCOVERY", snap, meta, graph)
    assert "backlog you described" not in cleaned.lower()
    assert "you're seeing" not in cleaned.lower()


def test_sanitize_softens_definitive_language_low_confidence() -> None:
    body = "The primary bottleneck is scheduling and this confirms the ops issue."
    meta = SessionMetadata()
    snap = HypothesisSnapshot(overall_confidence=0.5)
    cleaned = sanitize_ungrounded_assertions(body, "DIAGNOSE", snap, meta, None)
    assert "primary bottleneck is" not in cleaned.lower()
    assert "this confirms" not in cleaned.lower()


def test_hedged_contributors_not_definitive() -> None:
    graph = ConversationContextGraph(pain_points=["compliance reviews are manual"])
    snap = HypothesisSnapshot(
        confirmed_facts=["compliance reviews are manual"],
        confidence_scores={"manual_compliance_review": 0.61},
    )
    text = build_hedged_contributors(graph, snap)
    assert text
    assert "primary bottleneck" not in text.lower()
    assert "possible contributors" in text.lower() or "one possibility" in text.lower()


def test_question_no_false_backlog_reference() -> None:
    graph = ConversationContextGraph(
        pain_points=["compliance reviews are manual"],
        active_thread="compliance_backlog",
        thread_depth=1,
    )
    snap = HypothesisSnapshot(
        confirmed_facts=["compliance reviews are manual"],
        confidence_scores={"manual_compliance_review": 0.61},
    )
    meta = SessionMetadata(message_count=2)
    q, _ = compose_contextual_question(graph, snap, meta)
    assert q
    assert "backlog you described" not in q.lower()


def test_bank_turn2_question_discriminates_hypotheses() -> None:
    meta = SessionMetadata(message_count=2, industry="financial_services")
    result = TurnPipeline.run(meta, _BANK_TURN_2, [_BANK_TURN_1])
    q = (result.snapshot.required_question or "").lower()
    assert "backlog you described" not in q
    assert any(
        term in q
        for term in (
            "priorit",
            "fifo",
            "risk tier",
            "handoff",
            "queue",
            "compliance",
            "walk me through",
            "how long",
            "quality gate",
        )
    )


def test_question_assumes_unstated_backlog() -> None:
    graph = ConversationContextGraph()
    snap = HypothesisSnapshot()
    assert question_assumes_unstated_facts(
        "With the backlog you described, how do you prioritize?",
        graph,
        snap,
    )
