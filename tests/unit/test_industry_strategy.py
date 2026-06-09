"""Generic growth advisory signals (not per-industry maps)."""

from app.advisor.orchestrator.industry_strategy import (
    business_label,
    generic_phased_framework,
    is_local_footprint,
    is_micro_budget,
    pushback_for_website_question,
    rag_industry_guidance_line,
)
from app.advisor.types import SessionMetadata


def test_business_label_from_evaluator_fields() -> None:
    assert business_label(SessionMetadata(business_type="local fitness studio")) == "local fitness studio"
    assert business_label(SessionMetadata(industry="professional services")) == "professional services"


def test_local_footprint_any_industry() -> None:
    meta = SessionMetadata(business_type="widget repair shop")
    assert is_local_footprint(meta, "most customers come from referrals nearby") is True


def test_generic_framework_mentions_rag_not_verticals() -> None:
    plan = generic_phased_framework()
    assert "rag_query" in plan
    assert "bakery" not in plan.lower()
    assert "fitness" not in plan.lower()


def test_rag_guidance_uses_business_label() -> None:
    line = rag_industry_guidance_line(SessionMetadata(business_type="pet grooming"))
    assert "pet grooming" in line
    assert "rag_query" in line


def test_micro_budget_detection() -> None:
    assert is_micro_budget(SessionMetadata(constraints="only $500 budget")) is True


def test_website_pushback_local_referrals() -> None:
    meta = SessionMetadata(business_type="any local shop")
    msg = "Do I really need a website? Most customers come from referrals"
    assert pushback_for_website_question(meta, msg) is not None
