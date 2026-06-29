"""Frozen RAG query templates — deterministic arg building."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Final, Literal

from app.advisor.orchestrator.signals import get_signal_registry
from app.advisor.types import ProductFitDecision, SessionMetadata

RagQueryIntent = Literal[
    "product_fact", "product_compare", "concept_def",
    "architecture", "capabilities", "general",
]

INTENT_TO_RAG_QUERY: Final[dict[str, RagQueryIntent]] = {
    "product_comparison": "product_compare",
    "concept_explanation": "concept_def",
    "technical_solution_request": "architecture",
    "general": "general",
    "advice_request": "capabilities",
    "roi_analysis": "capabilities",
    "objection": "capabilities",
    "channel_prioritization": "capabilities",
    "product_tour": "product_fact",
    "booking": "general",
}

SLOT_MAX_MESSAGE = 120
SLOT_MAX_PAIN = 60
SLOT_MAX_PRODUCT = 40


@dataclass(frozen=True)
class RagQueryTemplate:
    query_template: str
    namespace: str
    top_k: int


RAG_QUERY_TEMPLATES: Final[dict[RagQueryIntent, RagQueryTemplate]] = {
    "product_fact": RagQueryTemplate(
        "{product} {message_core} workflow steps features",
        "auto", 3,
    ),
    "product_compare": RagQueryTemplate(
        "{product} workflow steps features differences {message_core}",
        "auto", 5,
    ),
    "concept_def": RagQueryTemplate(
        "{message_core} definition explanation",
        "auto", 3,
    ),
    "architecture": RagQueryTemplate(
        "{message_core} architecture integration workflow {pain}",
        "architecture", 3,
    ),
    "capabilities": RagQueryTemplate(
        "{message_core} capabilities features workflow {pain}",
        "capabilities", 3,
    ),
    "general": RagQueryTemplate(
        "{message_core} capabilities features workflow",
        "auto", 3,
    ),
}


def _strip_noise(message: str) -> str:
    text = message.strip()
    signals = get_signal_registry()
    for pat in signals.noise_strip_patterns:
        text = re.sub(pat, "", text, flags=re.I).strip()
    return text[:SLOT_MAX_MESSAGE]


def _slot(value: str, max_len: int) -> str:
    return value.strip()[:max_len]


def resolve_rag_intent(intent: str) -> RagQueryIntent:
    return INTENT_TO_RAG_QUERY.get(intent, "general")


def resolve_namespace(
    template_ns: str,
    fit: ProductFitDecision,
    catalog_product: str | None,
) -> str:
    if template_ns != "auto":
        return template_ns
    if fit.catalog_product_fit:
        return fit.catalog_product_fit
    if fit.solution_category == "custom_solutions":
        return "capabilities"
    if catalog_product:
        return catalog_product
    return "auto"


def resolve_namespace(
    template_ns: str,
    fit: ProductFitDecision,
    catalog_product: str | None,
) -> str:
    if template_ns != "auto":
        return template_ns
    if fit.catalog_product_fit:
        return fit.catalog_product_fit
    if fit.solution_category == "custom_solutions":
        return "capabilities"
    if catalog_product:
        return catalog_product
    return "auto"


def build_rag_spec(
    intent: str,
    message: str,
    meta: SessionMetadata,
    fit: ProductFitDecision,
    active_product: str | None,
) -> dict[str, Any]:
    rag_intent = resolve_rag_intent(intent)
    template = RAG_QUERY_TEMPLATES[rag_intent]
    message_core = _strip_noise(message)
    pain = _slot(meta.pain_point or "", SLOT_MAX_PAIN)
    product = _slot(
        fit.catalog_product_fit or active_product or meta.active_product or "",
        SLOT_MAX_PRODUCT,
    )
    query = template.query_template.format(
        message_core=message_core,
        pain=pain,
        product=product,
    ).strip()
    namespace = resolve_namespace(template.namespace, fit, active_product)
    return {"query": query, "namespace": namespace, "top_k": template.top_k}


def build_bi_rag_spec(
    meta: SessionMetadata,
    message: str,
    *,
    problem_dimension: str | None = None,
    universal_stage: str | None = None,
) -> dict[str, Any]:
    """Business intelligence KB query for cross-industry diagnostic patterns."""
    dim = problem_dimension or meta.problem_dimension or "throughput"
    stage = universal_stage or "unknown"
    message_core = _strip_noise(message)
    pain = _slot(meta.pain_point or "", SLOT_MAX_PAIN)
    query = (
        f"{dim} bottleneck {stage} {message_core} {pain} "
        "queue saturation manual handoff hypothesis differentiating question"
    ).strip()
    return {"query": query, "namespace": "business_intelligence", "top_k": 4}


def build_product_compare_args(
    meta: SessionMetadata,
    message: str,
) -> dict[str, Any]:
    products = [p for p in meta.products_discussed if p in ("retify", "ecg", "legal", "forecasting")]
    if len(products) < 2:
        products = ["retify", "forecasting"]
    focus = "general"
    lower = message.lower()
    if "workflow" in lower:
        focus = "workflow"
    elif "feature" in lower:
        focus = "features"
    return {"product_ids": products[:4], "comparison_focus": focus}
