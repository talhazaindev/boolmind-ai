"""Intent classifier tests."""

from app.advisor.orchestrator.intent_classifier import (
    classify_intent,
    is_advisory_intent,
    is_solution_architecture_mode,
)


def test_advice_request_intent() -> None:
    result = classify_intent("What would you recommend I do in the next 3 months?")
    assert result.intent == "advice_request"


def test_roi_analysis_intent() -> None:
    result = classify_intent("How do I know if $5000 is worth it?")
    assert result.intent == "roi_analysis"


def test_objection_intent() -> None:
    result = classify_intent("Why not just use Wix instead?")
    assert result.intent == "objection"


def test_product_comparison_intent() -> None:
    result = classify_intent("Compare Retify vs ECG")
    assert result.intent == "product_comparison"


def test_architecture_mode() -> None:
    msg = "Can you design the system architecture and data flow for our platform?"
    assert is_solution_architecture_mode(msg) is True


def test_channel_prioritization_intent() -> None:
    msg = (
        "I've heard about websites, SEO, social media, online ads, and AI tools, "
        "but I don't know what's actually worth focusing on."
    )
    assert classify_intent(msg).intent == "channel_prioritization"


def test_concept_explanation_intent() -> None:
    result = classify_intent(
        "Before I answer that, can you explain what you mean by online presence?"
    )
    assert result.intent == "concept_explanation"


def test_is_advisory_intent() -> None:
    assert is_advisory_intent("What should I do?") is True
    assert is_advisory_intent("We run a retail store") is False
