"""Advisor constants."""

from typing import Final

from app.advisor.config.products import PRODUCTS, get_product

PRODUCT_NAMES: Final[dict[str, str]] = {p.id: p.name for p in PRODUCTS}

PRODUCT_KEYWORDS: Final[dict[str, list[str]]] = {
    "retify": [
        "retify",
        "retail",
        "retail data",
        "pos data",
        "store data",
        "sku",
        "inventory",
        "erp",
        "retail analytics",
        "retail insights",
    ],
    "ecg": [
        "ecg",
        "electrocardiogram",
        "cardiac",
        "heart",
        "clinical",
        "medical document",
        "waveform",
        "ecg pdf",
        "holter",
        "cardiology",
    ],
    "legal": [
        "legal data",
        "legal fusion",
        "law",
        "compliance",
        "regulatory",
        "contract",
        "legal document",
        "case law",
        "regulation",
        "gdpr",
    ],
    "forecasting": [
        "forecasting",
        "forecast",
        "demand planning",
        "sales prediction",
        "time series",
        "stockout",
        "promotion roi",
        "weather impact",
        "inventory optimization",
        "hierarchical forecast",
    ],
    "custom_solutions": [
        "custom solution",
        "custom build",
        "bespoke",
        "fleet management",
        "fleet",
        "transportation",
        "logistics",
        "driver workload",
        "truck maintenance",
        "mobile app",
        "build an app",
        "marketplace",
        "booking app",
        "two-sided",
        "web development",
        "applied ai",
        "ai automation",
    ],
}

CUSTOM_SOLUTIONS_KEYWORDS: Final[list[str]] = PRODUCT_KEYWORDS["custom_solutions"]

TOOL_TIMEOUT_MS: Final[dict[str, int]] = {
    "rag_query": 2000,
    "crm_create_lead": 3000,
    "product_tour": 1000,
    "calendar_get_slots": 3000,
    "calendar_book_slot": 3000,
    "send_meeting_invite": 3000,
    "product_compare": 3000,
    "generate_fidp": 180000,
    "generate_architecture_proposal": 5000,
}

HISTORY_TTL_SECONDS: Final[int] = 7200  # 2 hours
VISITOR_TTL_SECONDS: Final[int] = 2592000  # 30 days
MAX_HISTORY_MESSAGES: Final[int] = 20

GENERIC_ERROR_MESSAGE: Final[str] = (
    "Something went wrong on our side. Please try again in a moment."
)
FALLBACK_CRM_MESSAGE: Final[str] = (
    "I've noted your details — our team will follow up shortly."
)

EVAL_TIMEOUT_MS: Final[int] = 2000

_EVAL_TIMEOUT_BY_PROVIDER: Final[dict[str, int]] = {
    "groq": 2000,
    "anthropic": 5000,
    "openai": 5000,
    "ollama": 60000,
}


def eval_timeout_ms_for_provider(provider: str) -> int:
    """Provider-aware background eval timeout."""
    return _EVAL_TIMEOUT_BY_PROVIDER.get(provider.strip().lower(), EVAL_TIMEOUT_MS)
PRODUCT_FIT_CONFIDENCE_MIN: Final[float] = 0.7
RAG_SPARSE_SCORE_THRESHOLD: Final[float] = 0.35

DISCOVERY_REQUIRED_FIELDS: Final[list[str]] = [
    "business_context",
    "pain_point",
    "goals",
]

TOOL_READINESS_KEY: Final[dict[str, str]] = {
    "product_tour": "product_tour",
    "generate_architecture_proposal": "architecture",
    "generate_fidp": "fidp",
    "crm_create_lead": "lead_capture",
    "calendar_get_slots": "booking",
    "calendar_book_slot": "booking",
    "send_meeting_invite": "booking",
}

ALWAYS_AVAILABLE_TOOLS: Final[frozenset[str]] = frozenset({"rag_query", "product_compare"})

SELF_GROUNDING_TOOLS: Final[frozenset[str]] = frozenset({
    "product_compare",
    "generate_architecture_proposal",
})

RAG_TOOLS: Final[frozenset[str]] = frozenset({"rag_query", "product_compare"})

DELIVERABLE_TOOLS: Final[frozenset[str]] = frozenset({
    "generate_architecture_proposal",
    "generate_fidp",
    "product_tour",
    "crm_create_lead",
    "calendar_get_slots",
    "calendar_book_slot",
    "send_meeting_invite",
})

ROUTING_CONFIDENCE_DISCOVERY_THRESHOLD: Final[float] = 0.60
TOOL_CONFIDENCE_THRESHOLD: Final[float] = 0.75
DIAGNOSIS_CONFIDENCE_THRESHOLD: Final[float] = 0.75

RAG_SOFT_TIMEOUT_MS: Final[int] = 800

# Internal LLM note when RAG has no excerpt — must never be quoted verbatim to users.
RAG_SPARSE_INTERNAL_NOTE: Final[str] = (
    "Sparse KB match for this specific detail. Use conversation context to recommend "
    "a Boolmind-appropriate path (catalog product or phased custom engagement). "
    "Do NOT mention knowledge base gaps to the user. "
    "Do NOT steer user to DIY/Wix/freelancer unless they explicitly asked."
)


def product_name(product_id: str) -> str:
    p = get_product(product_id)
    return p.name if p else product_id
