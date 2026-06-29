"""Solution architecture proposal (Section 16)."""

from __future__ import annotations

from typing import Any

from app.advisor.constants import PRODUCT_NAMES, RAG_SPARSE_INTERNAL_NOTE
from app.advisor.rag.retrieve import retrieve


async def handle(arguments: dict[str, Any]) -> dict[str, Any]:
    product = arguments.get("primary_product", "retify")
    summary = arguments.get("requirements_summary", "")
    constraints = arguments.get("constraints", [])

    context = retrieve(
        query=f"{summary} architecture integration patterns {product}",
        namespace_arg="architecture",
        active_product=product,
        top_k=5,
    )
    if context == RAG_SPARSE_INTERNAL_NOTE or not context.strip():
        context = retrieve(
            query=f"{summary} workflow integration",
            namespace_arg=product,
            active_product=product,
            top_k=3,
        )

    name = PRODUCT_NAMES.get(product, product)
    mermaid = (
        "flowchart LR\n"
        "  A[Sources] --> B[Ingest]\n"
        "  B --> C[Process]\n"
        "  C --> D[Golden Records]\n"
        "  D --> E[Analytics / EMR]"
    )

    return {
        "mode": "SOLUTION_ARCHITECTURE",
        "requirementsSummary": summary,
        "primaryProduct": product,
        "productName": name,
        "overview": (
            f"Proposed architecture using {name} for the described requirements. "
            "Components below map to Boolmind workflow steps and external integrations."
        ),
        "mermaidDiagram": mermaid,
        "components": [
            {
                "name": "Data Ingestion Layer",
                "role": "Multi-format intake",
                "provider": "Boolmind",
                "product": product,
            },
            {
                "name": "Processing Pipeline",
                "role": "Schema, quality, entity resolution",
                "provider": "Boolmind",
                "product": product,
            },
            {
                "name": "Downstream Systems",
                "role": "Warehouse / EMR / analytics",
                "provider": "External",
                "product": product,
            },
        ],
        "dataFlow": "Sources → ingest → process → validate → harmonized output → consumers",
        "phases": [
            {"phase": 1, "title": "Discovery", "duration": "1-2 weeks"},
            {"phase": 2, "title": "Pilot ingest", "duration": "2-4 weeks"},
            {"phase": 3, "title": "Production rollout", "duration": "4-8 weeks"},
        ],
        "techStack": ["Python/FastAPI", "Pinecone", "Redis", name],
        "risks": [
            {"risk": "Source schema drift", "severity": "medium", "mitigation": "Continuous profiling"},
            {"risk": "Integration latency", "severity": "low", "mitigation": "Async pipelines"},
        ],
        "constraints": constraints,
        "ragContext": context[:2000],
        "nextStep": "Book a deep-dive architecture session with our solutions team.",
    }
