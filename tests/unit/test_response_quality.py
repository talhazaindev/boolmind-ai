"""Response quality — telemetry only."""

from app.advisor.orchestrator.response_quality import assess_response_quality
from app.advisor.types import HypothesisSnapshot


def test_generic_response_fails() -> None:
    snap = HypothesisSnapshot(business_model="service")
    check = assess_response_quality(
        "Manual dispatching may be causing delays. Tell me more about your business?",
        "DIAGNOSE",
        snap,
    )
    assert not check.passed
    assert "generic_phrase" in check.failures


def test_anchored_diagnose_passes() -> None:
    snap = HypothesisSnapshot(
        business_model="service",
        primary_bottleneck="dispatch",
        diagnose_depth="early",
    )
    body = (
        "A serious slip — manual dispatch at your volume likely creates a throughput "
        "constraint because coordinators cannot keep pace with peak demand."
    )
    check = assess_response_quality(body, "DIAGNOSE", snap)
    assert check.passed
