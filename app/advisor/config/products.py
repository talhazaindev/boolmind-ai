"""Product and capability registry — single source for discovery, prompts, and tools."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ProductKind = Literal["pipeline", "platform", "services"]


@dataclass(frozen=True)
class ProductDefinition:
    id: str
    name: str
    kind: ProductKind
    workflow_steps: int | None
    discovery_question: str
    keywords_namespace: str
    compare_in_default: bool
    supports_tour: bool


PRODUCTS: tuple[ProductDefinition, ...] = (
    ProductDefinition(
        id="retify",
        name="Retify — Retail Data Unification",
        kind="pipeline",
        workflow_steps=10,
        discovery_question="What retail data sources are you working with?",
        keywords_namespace="retify",
        compare_in_default=True,
        supports_tour=True,
    ),
    ProductDefinition(
        id="ecg",
        name="ECG Document Intelligence",
        kind="pipeline",
        workflow_steps=7,
        discovery_question="Are you working with scanned ECGs, waveforms, or both?",
        keywords_namespace="ecg",
        compare_in_default=True,
        supports_tour=True,
    ),
    ProductDefinition(
        id="legal",
        name="Legal Data Fusion",
        kind="pipeline",
        workflow_steps=6,
        discovery_question="What types of legal datasets are you looking to consolidate?",
        keywords_namespace="legal",
        compare_in_default=True,
        supports_tour=True,
    ),
    ProductDefinition(
        id="forecasting",
        name="Forecasting Engine",
        kind="platform",
        workflow_steps=8,
        discovery_question="What sales or demand data do you want to forecast, and for which stores or products?",
        keywords_namespace="forecasting",
        compare_in_default=True,
        supports_tour=True,
    ),
    ProductDefinition(
        id="custom_solutions",
        name="Boolmind Custom Solutions",
        kind="services",
        workflow_steps=None,
        discovery_question="What business outcome do you need from a custom-built solution?",
        keywords_namespace="capabilities",
        compare_in_default=False,
        supports_tour=False,
    ),
)


def get_product(product_id: str) -> ProductDefinition | None:
    for product in PRODUCTS:
        if product.id == product_id:
            return product
    return None


def product_ids() -> list[str]:
    return [p.id for p in PRODUCTS]


def catalog_product_ids() -> list[str]:
    """Products with tours and pipeline/platform workflows (excludes custom_solutions)."""
    return [p.id for p in PRODUCTS if p.id != "custom_solutions"]


def tour_product_ids() -> list[str]:
    return [p.id for p in PRODUCTS if p.supports_tour]


def compare_product_ids() -> list[str]:
    return [p.id for p in PRODUCTS if p.compare_in_default]


def crm_primary_product_ids() -> list[str]:
    return catalog_product_ids()


def products_summary_for_prompt() -> str:
    parts: list[str] = []
    for p in PRODUCTS:
        if p.workflow_steps is not None:
            parts.append(f"{p.id.upper()}: {p.name} ({p.workflow_steps}-step)")
        elif p.id == "custom_solutions":
            parts.append(f"CUSTOM: web, mobile, applied AI, automation (bespoke builds)")
        else:
            parts.append(f"{p.id.upper()}: {p.name}")
    return "; ".join(parts)


def products_summary_for_evaluator() -> str:
    catalog = ", ".join(
        f"{p.id} ({p.name})" for p in PRODUCTS if p.id != "custom_solutions"
    )
    return f"{catalog}; custom_solutions (bespoke web/mobile/AI when catalog does not fit)"


def workflow_steps_note() -> str:
    items = [
        f"{p.name.split(' — ')[0] if ' — ' in p.name else p.name} ({p.workflow_steps} steps)"
        for p in PRODUCTS
        if p.workflow_steps is not None
    ]
    return "; ".join(items)
