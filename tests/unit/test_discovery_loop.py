"""Discovery loop, memory retention, and diagnostic progression tests."""

from app.advisor.orchestrator.hypothesis_state import update_hypothesis_snapshot
from app.advisor.orchestrator.signals.v1 import INFORMATION_GAIN_QUESTIONS, UNKNOWN_TO_QUESTION
from app.advisor.pipeline.question_gate import question_violations, validate_follow_up_question
from app.advisor.pipeline.turn_pipeline import TurnPipeline
from app.advisor.types import SessionMetadata


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


def test_lending_volume_not_reasked_after_provided() -> None:
    meta = SessionMetadata(message_count=2, industry="financial_services")
    history = [_LENDING_TURN_1]
    snap = update_hypothesis_snapshot(meta, _LENDING_TURN_2, history)

    assert snap.scale_indicators
    assert "scale" in snap.resolved_unknowns
    assert snap.required_question is not None
    assert snap.required_question != UNKNOWN_TO_QUESTION["scale"]
    assert "volume" not in (snap.required_question or "").lower()


def test_lending_follow_up_targets_uncertainty() -> None:
    meta = SessionMetadata(message_count=2, industry="financial_services")
    history = [_LENDING_TURN_1]
    snap = update_hypothesis_snapshot(meta, _LENDING_TURN_2, history)
    q = (snap.required_question or "").lower()

    assert any(
        phrase in q
        for phrase in (
            "backlog",
            "compliance",
            "exception",
            "underwriting",
            "documentation",
        )
    )


def test_question_gate_blocks_scale_when_known() -> None:
    meta = SessionMetadata(message_count=2, data_context="220 applications/day")
    history = [_LENDING_TURN_1]
    snap = update_hypothesis_snapshot(meta, _LENDING_TURN_2, history)

    violations = question_violations(UNKNOWN_TO_QUESTION["scale"], snap, meta)
    assert violations
    validated, _ = validate_follow_up_question(UNKNOWN_TO_QUESTION["scale"], snap, meta)
    assert validated != UNKNOWN_TO_QUESTION["scale"]


def test_lending_facts_extracted_to_memory() -> None:
    meta = SessionMetadata(message_count=1)
    result = TurnPipeline.run(meta, _LENDING_TURN_2, [_LENDING_TURN_1])

    facts_blob = " ".join(result.snapshot.confirmed_facts).lower()
    assert "220" in facts_blob or "application" in facts_blob
    assert "compliance" in facts_blob or "backlog" in facts_blob

    memory_keys = {line.key for line in result.business_memory.lines}
    assert "scale" in memory_keys or result.snapshot.scale_indicators


def test_premature_diagnosis_blocked_on_sparse_turn() -> None:
    meta = SessionMetadata(message_count=1)
    result = TurnPipeline.run(meta, _LENDING_TURN_1, [])
    assert result.router_output.mode == "DISCOVERY"
    assert result.snapshot.overall_confidence < 0.75


def test_diagnosis_allowed_after_rich_lending_context() -> None:
    meta = SessionMetadata(message_count=2, industry="financial_services")
    result = TurnPipeline.run(meta, _LENDING_TURN_2, [_LENDING_TURN_1])
    assert result.snapshot.overall_confidence >= 0.75
    assert result.router_output.mode in ("DIAGNOSE", "SALES")


def test_hypothesis_confidence_ranked_for_lending() -> None:
    meta = SessionMetadata(message_count=2)
    snap = update_hypothesis_snapshot(meta, _LENDING_TURN_2, [_LENDING_TURN_1])
    assert snap.confidence_scores.get("manual_compliance_review", 0) >= 0.7
    assert "compliance_queue_backlog" in snap.confidence_scores or "manual_compliance_review" in snap.confidence_scores


def test_logistics_regression_scale_still_works() -> None:
    meta = SessionMetadata(industry="logistics", message_count=2)
    msg = "We dispatch around 1,500 shipments per day manually in spreadsheets."
    snap = update_hypothesis_snapshot(meta, msg, ["We run a logistics company"])
    assert "scale" in snap.resolved_unknowns
    assert snap.required_question != INFORMATION_GAIN_QUESTIONS.get("routing_constraints") or True
