"""Pinecone namespace configuration."""

from __future__ import annotations

from typing import Final

from app.advisor.config.products import (
    PRODUCTS,
    catalog_product_ids,
    compare_product_ids,
)

NAMESPACES: Final[list[str]] = [
    *catalog_product_ids(),
    "capabilities",
    "general",
    "architecture",
]

PRODUCT_TO_NAMESPACE: Final[dict[str, str]] = {
    p.id: p.keywords_namespace for p in PRODUCTS if p.id != "custom_solutions"
}
PRODUCT_TO_NAMESPACE["custom_solutions"] = "capabilities"


def resolve_namespace(
    namespace_arg: str,
    active_product: str | None,
    product_fit: str | None = None,
) -> list[str]:
    if namespace_arg == "capabilities":
        return ["capabilities"]

    if namespace_arg == "all":
        return [*compare_product_ids(), "general"]

    if namespace_arg == "auto":
        fit = product_fit or active_product
        if fit == "custom_solutions":
            return ["capabilities", "general"]
        if fit and fit in PRODUCT_TO_NAMESPACE:
            return [PRODUCT_TO_NAMESPACE[fit]]
        if active_product and active_product in PRODUCT_TO_NAMESPACE:
            return [PRODUCT_TO_NAMESPACE[active_product]]
        return ["general"]

    if namespace_arg in NAMESPACES:
        return [namespace_arg]
    if namespace_arg in catalog_product_ids():
        return [namespace_arg]
    return ["general"]
