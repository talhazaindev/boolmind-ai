"""RAG query tool handler."""

from __future__ import annotations

from typing import Any

from app.advisor.orchestrator.product_context import ProductContext
from app.advisor.rag.retrieve import retrieve


async def handle(
    arguments: dict[str, Any],
    product_context: ProductContext,
) -> dict[str, Any]:
    query = arguments.get("query", "")
    top_k = int(arguments.get("top_k", 3))
    namespace = arguments.get("namespace", "auto")
    product_fit = product_context.product_fit or product_context.active_product
    context = retrieve(
        query=query,
        namespace_arg=namespace,
        active_product=product_context.active_product,
        top_k=top_k,
        product_fit=product_fit,
    )
    return {
        "context": context,
        "query": query,
        "namespace": namespace,
        "product_fit": product_fit,
    }
