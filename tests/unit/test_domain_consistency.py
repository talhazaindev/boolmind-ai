"""Domain consistency and duplicate-question assembly tests."""

from app.advisor.orchestrator.question_append import (
    finalize_response,
    question_already_in_text,
    strip_redundant_questions,
)
from app.advisor.pipeline.domain_consistency import (
    detect_industry_context,
    domain_terminology_violations,
    metric_label_for_cause,
    sanitize_question_for_domain,
)
from app.advisor.pipeline.question_value import build_metric_change_question, extract_competing_causes
from app.advisor.pipeline.turn_pipeline import TurnPipeline
from app.advisor.types import HypothesisSnapshot, SessionMetadata

_HVAC_TURN_1 = (
    "We're a multi-location home services company (HVAC, plumbing, and electrical). "
    "Revenue has grown about 35% over the last 18 months, but profit margins keep "
    "shrinking. Leadership disagrees on the cause — operations thinks technician "
    "utilization is the issue, finance points to rising labor costs, and sales "
    "believes pricing hasn't kept up with market conditions. We have 22 service "
    "locations and roughly 300 field technicians."
)


def test_detect_home_services_context() -> None:
    meta = SessionMetadata()
    snap = HypothesisSnapshot()
    ctx = detect_industry_context(meta, snap, message=_HVAC_TURN_1)
    assert ctx == "home_services"


def test_no_chair_utilization_in_hvac_metric_question() -> None:
    meta = SessionMetadata()
    snap = HypothesisSnapshot()
    causes = extract_competing_causes(_HVAC_TURN_1.lower())
    q = build_metric_change_question(
        causes,
        _HVAC_TURN_1.lower(),
        meta=meta,
        snapshot=snap,
        message=_HVAC_TURN_1,
    )
    assert q
    assert "chair" not in q.lower()
    assert "technician" in q.lower() or "labor" in q.lower()


def test_domain_violation_chair_in_hvac() -> None:
    meta = SessionMetadata()
    snap = HypothesisSnapshot()
    bad = (
        "Over the last recent months, which changed most materially — labor costs "
        "per location, or billable or chair utilization rates?"
    )
    violations = domain_terminology_violations(
        bad, meta, snap, message=_HVAC_TURN_1
    )
    assert violations
    cleaned = sanitize_question_for_domain(bad, meta, snap, message=_HVAC_TURN_1)
    assert cleaned
    assert "chair" not in cleaned.lower()


def test_metric_label_home_services() -> None:
    label = metric_label_for_cause("labor_utilization", "home_services")
    assert "technician" in label.lower()
    assert "chair" not in label.lower()


def test_hvac_pipeline_question_domain_safe() -> None:
    result = TurnPipeline.run(SessionMetadata(message_count=1), _HVAC_TURN_1, [])
    q = result.snapshot.required_question or ""
    assert q
    assert "chair" not in q.lower()
    assert "18 months" in q.lower()


def test_finalize_response_no_duplicate_question() -> None:
    q = "Over the last 18 months, which changed most — labor costs or technician utilization?"
    body = f"Margins are shrinking.\n\n{q}"
    final = finalize_response(body, q)
    assert final.count("?") == 1
    assert question_already_in_text(final, q)


def test_dedupe_identical_paragraphs() -> None:
    q = "Over the last 18 months, which changed most — labor costs or technician utilization?"
    body = f"{q}\n\n{q}"
    cleaned = strip_redundant_questions(
        body,
        HypothesisSnapshot(),
        SessionMetadata(),
        appended_question=q,
    )
    assert cleaned.count("?") == 0
