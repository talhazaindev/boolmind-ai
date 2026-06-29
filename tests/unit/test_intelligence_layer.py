"""Intelligence layer unit tests."""

from app.advisor.orchestrator.context_graph import build_context_graph
from app.advisor.orchestrator.diagnostic_trees import locate_universal_stage, rank_ops_hypotheses
from app.advisor.orchestrator.inference_builder import build_derived_inferences
from app.advisor.orchestrator.question_composer import compose_contextual_question
from app.advisor.pipeline.question_tracker import question_key_for_text
from app.advisor.pipeline.turn_pipeline import TurnPipeline
from app.advisor.pipeline.volume_patterns import extract_volume_indicators
from app.advisor.orchestrator.signals.v1 import UNKNOWN_TO_QUESTION
from app.advisor.types import ConversationContextGraph, HypothesisSnapshot, MetricValue, SessionMetadata

_LENDING_TURN_1 = (
    "We operate a regional commercial lending business. Loan applications have "
    "increased significantly over the last year, but approval turnaround times "
    "have gone from 3 days to nearly 9 days on average."
)

_LENDING_TURN_2 = (
    "We process around 220 loan applications per day. Initial intake is digital, "
    "but underwriting analysts manually gather supporting documents from email, "
    "verify financial statements, and enter data into our loan origination system. "
    "Compliance reviews are handled by a separate team and applications often sit "
    "in queues waiting for approval. We actually tried automating document collection "
    "last year. Adoption was poor because analysts said the system missed exceptions "
    "and they went back to email. Compliance reviews are completely manual and there "
    "is currently a backlog of about 600 applications."
)


def test_question_tracker_maps_scale_key() -> None:
    key = question_key_for_text(UNKNOWN_TO_QUESTION["scale"])
    assert key == "scale"


def test_volume_extraction_lending() -> None:
    found = extract_volume_indicators(_LENDING_TURN_2)
    assert any("220" in f for f in found)


def test_derived_queue_days_inference() -> None:
    graph = ConversationContextGraph(
        metrics={
            "daily_volume": MetricValue(value=220),
            "backlog": MetricValue(value=600),
        }
    )
    inferences = build_derived_inferences(graph)
    assert inferences
    assert "queue_days" in graph.metrics


def test_universal_stage_compliance() -> None:
    graph = ConversationContextGraph(
        workflow_stages={
            "quality_gate": __import__(
                "app.advisor.types", fromlist=["StageState"]
            ).StageState(mode="manual", confidence=0.8)
        }
    )
    stage = locate_universal_stage(graph, "manual compliance review backlog")
    assert stage == "quality_gate"


def test_lending_pipeline_no_scale_repeat_turn2() -> None:
    meta = SessionMetadata(message_count=2, industry="financial_services")
    result = TurnPipeline.run(meta, _LENDING_TURN_2, [_LENDING_TURN_1])
    q = (result.snapshot.required_question or "").lower()
    assert "volume" not in q or "220" in q
    assert result.context_graph is not None
    assert result.context_graph.metrics.get("daily_volume") is not None


def test_compose_question_references_automation_failure() -> None:
    meta = SessionMetadata(message_count=2, industry="financial_services")
    result = TurnPipeline.run(meta, _LENDING_TURN_2, [_LENDING_TURN_1])
    q = (result.snapshot.required_question or "").lower()
    assert any(
        term in q
        for term in ("exception", "email", "compliance", "backlog", "underwriting")
    )


def test_ops_hypothesis_ranking() -> None:
    graph = ConversationContextGraph(pain_points=["compliance backlog manual"])
    snap = HypothesisSnapshot(confirmed_facts=["compliance reviews are manual"])
    ranked = rank_ops_hypotheses(graph, snap)
    assert ranked
    assert ranked[0][0] in (
        "queue_saturation",
        "manual_compliance_review",
        "manual_handoff",
        "prioritization_gap",
    ) or "compliance" in ranked[0][0]


def test_compose_contextual_question_returns_reasoning() -> None:
    meta = SessionMetadata(message_count=2)
    snap = HypothesisSnapshot(
        active_business_vertical="financial_services",
        confirmed_facts=["commercial lending operation"],
        resolved_unknowns=["scale", "backlog_size"],
    )
    graph = build_context_graph(meta, _LENDING_TURN_2, [_LENDING_TURN_1], snap)
    q, reasoning = compose_contextual_question(graph, snap, meta)
    assert q
    assert reasoning.next_action == "ask_followup"
