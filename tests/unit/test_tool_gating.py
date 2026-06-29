"""Tool readiness gating tests."""

from app.advisor.orchestrator.tool_gating import (
    compute_rule_based_readiness,
    detect_deferred_deliverable_request,
    effective_readiness,
    filter_tool_definitions,
    has_minimum_discovery_context,
    is_tool_allowed,
)
from app.advisor.types import ReadinessFlags, SessionMetadata


def test_has_minimum_discovery_context() -> None:
    meta = SessionMetadata(
        industry="retail",
        pain_point="fragmented POS data",
        goals="unified analytics",
    )
    assert has_minimum_discovery_context(meta) is True


def test_readiness_blocks_gated_tools_initially() -> None:
    meta = SessionMetadata()
    readiness = compute_rule_based_readiness(meta)
    assert is_tool_allowed("rag_query", readiness) is True
    assert is_tool_allowed("product_tour", readiness) is False
    assert is_tool_allowed("generate_architecture_proposal", readiness) is False


def test_readiness_allows_tour_when_fit_confident() -> None:
    meta = SessionMetadata(
        industry="retail",
        pain_point="messy sales data",
        goals="single source of truth",
        product_fit="retify",
        product_fit_confidence=0.85,
        stage_reached="INTEREST",
    )
    readiness = compute_rule_based_readiness(meta)
    assert readiness.product_tour is True


def test_effective_readiness_intersection() -> None:
    meta = SessionMetadata(
        industry="retail",
        pain_point="messy sales data",
        goals="single source of truth",
        product_fit="retify",
        product_fit_confidence=0.85,
        stage_reached="INTEREST",
    )
    llm = ReadinessFlags(product_tour=True, architecture=True)
    effective = effective_readiness(meta, llm)
    assert effective.product_tour is True
    assert effective.architecture is False


def test_filter_tool_definitions() -> None:
    tools = [
        {"type": "function", "function": {"name": "rag_query"}},
        {"type": "function", "function": {"name": "product_tour"}},
    ]
    readiness = ReadinessFlags()
    filtered = filter_tool_definitions(tools, readiness)
    names = [t["function"]["name"] for t in filtered]
    assert names == ["rag_query"]


def test_detect_deferred_architecture_request() -> None:
    assert (
        detect_deferred_deliverable_request("Can you design our system architecture?")
        == "generate_architecture_proposal"
    )


def test_lead_capture_requires_capture_stage() -> None:
    meta = SessionMetadata(
        industry="retail",
        pain_point="messy sales data",
        goals="single source of truth",
        stage_reached="INTEREST",
    )
    readiness = compute_rule_based_readiness(meta)
    assert readiness.lead_capture is False

    meta.stage_reached = "CAPTURE"
    readiness = compute_rule_based_readiness(meta)
    assert readiness.lead_capture is True


def test_product_tour_blocked_for_custom_solutions() -> None:
    readiness = ReadinessFlags(product_tour=True)
    assert is_tool_allowed("product_tour", readiness, product_fit="custom_solutions") is False


def test_custom_solutions_architecture_not_blocked_by_fit() -> None:
    meta = SessionMetadata(
        industry="transportation",
        pain_point="fleet tracking",
        goals="scale operations",
        data_context="manual spreadsheets",
        product_fit="custom_solutions",
        product_fit_confidence=0.9,
        stage_reached="QUALIFY",
    )
    readiness = compute_rule_based_readiness(meta)
    assert readiness.product_tour is False
    assert readiness.architecture is True
