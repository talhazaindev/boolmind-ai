"""Evidence-based product fit — catalog vs solution_category."""

from __future__ import annotations

from typing import Final

from app.advisor.constants import PRODUCT_KEYWORDS
from app.advisor.types import ProductFitDecision, SessionMetadata

CATALOG_PRODUCTS: Final[frozenset[str]] = frozenset(
    {"retify", "ecg", "legal", "forecasting"}
)

FORECASTING_EVIDENCE: Final[tuple[str, ...]] = (
    "demand planning", "inventory forecast", "sku forecast", "sales prediction",
    "time series", "stockout", "promotion roi",
)

SOLUTION_EVIDENCE: Final[tuple[str, ...]] = (
    "custom", "bespoke", "marketplace", "fleet", "logistics platform",
    "automation", "ai workflow", "mobile app", "build an app", "two-sided",
    "dispatch", "routing", "shipment",
)

ANTI_FORECASTING: Final[tuple[str, ...]] = (
    "logistics", "dispatch", "shipment", "fleet", "truck",
)


def _blob(meta: SessionMetadata, message: str, history: list[str]) -> str:
    return " ".join([
        message,
        *history[-4:],
        meta.industry or "",
        meta.pain_point or "",
        meta.goals or "",
    ]).lower()


def _match_reasons(blob: str, signals: tuple[str, ...]) -> list[str]:
    return [s for s in signals if s in blob]


def map_product_fit(
    meta: SessionMetadata,
    message: str,
    history: list[str],
) -> ProductFitDecision:
    blob = _blob(meta, message, history)
    catalog_reasons: list[str] = []
    solution_reasons: list[str] = []
    catalog_fit: str | None = None
    solution_category: str | None = None

    forecast_hits = _match_reasons(blob, FORECASTING_EVIDENCE)
    anti_only = _match_reasons(blob, ANTI_FORECASTING) and not forecast_hits

    if forecast_hits and not anti_only:
        catalog_fit = "forecasting"
        catalog_reasons = forecast_hits

    for pid in CATALOG_PRODUCTS:
        if pid == "forecasting":
            continue
        hits = _match_reasons(blob, tuple(PRODUCT_KEYWORDS.get(pid, [])))
        if hits and not catalog_fit:
            catalog_fit = pid
            catalog_reasons = hits[:3]

    sol_hits = _match_reasons(blob, SOLUTION_EVIDENCE)
    custom_kw = _match_reasons(blob, tuple(PRODUCT_KEYWORDS.get("custom_solutions", [])))
    all_sol = list(dict.fromkeys([*sol_hits, *custom_kw]))
    if all_sol:
        solution_category = "custom_solutions"
        solution_reasons = all_sol[:5]
        if catalog_fit == "forecasting" and anti_only:
            catalog_fit = None
            catalog_reasons = []

    if not catalog_fit and not solution_category:
        solution_category = "undecided"

    confidence = 0.0
    if catalog_reasons:
        confidence = min(0.5 + 0.1 * len(catalog_reasons), 0.95)
    elif solution_reasons:
        confidence = min(0.5 + 0.08 * len(solution_reasons), 0.9)

    return ProductFitDecision(
        catalog_product_fit=catalog_fit,
        catalog_reasons=catalog_reasons,
        solution_category=solution_category,
        solution_reasons=solution_reasons,
        confidence=confidence,
    )
