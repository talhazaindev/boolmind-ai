"""Product context resolution from page URL and message."""

from __future__ import annotations

from dataclasses import dataclass

from app.advisor.constants import PRODUCT_KEYWORDS, PRODUCT_NAMES
from app.advisor.orchestrator.page_context import product_id_from_url
from app.advisor.rag.namespaces import PRODUCT_TO_NAMESPACE
from app.advisor.types import PageContext, SessionMetadata

__all__ = [
    "ProductContext",
    "apply_product_fit",
    "detect_product_in_message",
    "product_id_from_url",
    "resolve_product_context",
]

_CUSTOM_PRIORITY_SIGNALS = (
    "fleet management",
    "driver workload",
    "fleet tracking",
    "truck maintenance",
    "transportation",
    "logistics platform",
)


@dataclass
class ProductContext:
    active_product: str | None
    active_product_name: str | None
    products_discussed: list[str]
    namespace: str
    product_fit: str | None = None


def detect_product_in_message(message: str) -> str | None:
    lower = message.lower()
    if any(sig in lower for sig in _CUSTOM_PRIORITY_SIGNALS):
        return "custom_solutions"
    for product_id, keywords in PRODUCT_KEYWORDS.items():
        for kw in keywords:
            if kw in lower:
                return product_id
    return None


def _namespace_for_product(product_id: str | None) -> str:
    if not product_id:
        return "general"
    return PRODUCT_TO_NAMESPACE.get(product_id, product_id)


def apply_product_fit(
    context: ProductContext,
    product_fit: str | None,
) -> ProductContext:
    if not product_fit or product_fit == "undecided":
        return context
    return ProductContext(
        active_product=product_fit,
        active_product_name=PRODUCT_NAMES.get(product_fit, product_fit),
        products_discussed=context.products_discussed,
        namespace=_namespace_for_product(product_fit),
        product_fit=product_fit,
    )


def resolve_product_context(
    page_context: PageContext,
    session_data: SessionMetadata | None,
    message: str,
) -> ProductContext:
    discussed = list(session_data.products_discussed) if session_data else []
    session_fit = session_data.product_fit if session_data else None

    if session_fit and session_fit != "undecided":
        return apply_product_fit(
            ProductContext(
                active_product=None,
                active_product_name=None,
                products_discussed=discussed,
                namespace="general",
            ),
            session_fit,
        )

    if page_context.product_id:
        pid = page_context.product_id
        return ProductContext(
            active_product=pid,
            active_product_name=PRODUCT_NAMES.get(pid, page_context.product_name or pid),
            products_discussed=discussed,
            namespace=_namespace_for_product(pid),
        )

    if session_data and session_data.active_product:
        pid = session_data.active_product
        return ProductContext(
            active_product=pid,
            active_product_name=PRODUCT_NAMES.get(pid, pid),
            products_discussed=discussed,
            namespace=_namespace_for_product(pid),
        )

    detected = detect_product_in_message(message)
    if detected:
        return ProductContext(
            active_product=detected,
            active_product_name=PRODUCT_NAMES.get(detected, detected),
            products_discussed=discussed,
            namespace=_namespace_for_product(detected),
            product_fit=detected,
        )

    if discussed:
        pid = discussed[-1]
        return ProductContext(
            active_product=pid,
            active_product_name=PRODUCT_NAMES.get(pid, pid),
            products_discussed=discussed,
            namespace=_namespace_for_product(pid),
        )

    return ProductContext(
        active_product=None,
        active_product_name=None,
        products_discussed=discussed,
        namespace="general",
    )
