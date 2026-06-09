"""Multi-namespace product comparison via RAG (no hardcoded feature tables)."""

from __future__ import annotations

from typing import Any

from app.advisor.config.products import compare_product_ids, workflow_steps_note
from app.advisor.constants import PRODUCT_NAMES
from app.advisor.rag.retrieve import retrieve

VALID_PRODUCTS = frozenset(compare_product_ids())

FOCUS_QUERIES: dict[str, str] = {
    "general": "overview primary use case workflow steps target vertical key capability",
    "workflow": "workflow pipeline steps stages how it works",
    "features": "features capabilities supported formats outputs",
    "integration": "integration API EMR deployment connectivity",
    "compliance": "compliance security HIPAA GDPR privacy",
}


async def handle(arguments: dict[str, Any]) -> dict[str, Any]:
    raw_ids = arguments.get("product_ids") or []
    product_ids = [p for p in raw_ids if p in VALID_PRODUCTS]
    if len(product_ids) < 2:
        product_ids = compare_product_ids()

    focus = arguments.get("comparison_focus", "general")
    if focus not in FOCUS_QUERIES:
        focus = "general"
    query_suffix = FOCUS_QUERIES[focus]

    rows: list[dict[str, str]] = []
    for pid in product_ids:
        name = PRODUCT_NAMES.get(pid, pid)
        context = retrieve(
            query=f"{name} {query_suffix}",
            namespace_arg=pid,
            active_product=pid,
            top_k=3,
            product_fit=pid,
        )
        excerpt = context[:800] if context else "No knowledge base content found."
        rows.append(
            {
                "productId": pid,
                "productName": name,
                "excerpt": excerpt,
            }
        )

    return {
        "productsCompared": product_ids,
        "comparisonFocus": focus,
        "rows": rows,
        "source": "knowledge_base",
        "note": (
            f"Catalog products have distinct workflows — not interchangeable: {workflow_steps_note()}."
        ),
    }
