"""Signal registry v1 — frozen; changes require v2 bump."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

HYPOTHESIS_SIGNALS_VERSION: Final[str] = "v1"
ACTIVE_SIGNALS_VERSION: Final[str] = HYPOTHESIS_SIGNALS_VERSION

BUSINESS_MODEL_SIGNALS: Final[dict[str, tuple[str, ...]]] = {
    "saas": (
        "saas", "software", "b2b software", "app", "platform", "trial",
        "activation", "mrr", "arr", "subscription software",
    ),
    "subscription": (
        "subscription", "subscriber", "recurring", "monthly plan",
        "membership", "cancel after",
    ),
    "service": (
        "agency", "consulting", "professional service", "client project",
        "billable", "service business",
    ),
    "education": (
        "school", "teacher", "instructor", "student", "enrollment",
        "learning center", "academy", "classroom",
    ),
    "local_retail": (
        "bakery", "restaurant", "retail", "store", "foot traffic",
        "local business", "shop",
    ),
}

INTEGRATION_KEYWORDS: Final[tuple[str, ...]] = (
    "sap", "crm", "salesforce", "hubspot", "api", "erp", "manual",
    "spreadsheet", "excel", "email chain",
)

SCALE_PATTERNS: Final[tuple[str, ...]] = (
    r"\d+\+?\s*(shipments|orders|users|transactions|customers|applications|loans|cases)",
    r"\d+\s*(loan\s+)?applications?\s*(per day|daily|a day)",
    r"\d+\s*(per day|daily|a day)",
    r"\d+\s*(regions|countries|locations)",
)

EXPLICIT_STATEMENT_PATTERNS: Final[tuple[str, ...]] = (
    r"we are a[n]?\s+(\w+)",
    r"we use\s+(\w+)",
    r"our (?:erp|crm|system) is\s+(\w+)",
)

UNKNOWN_TO_QUESTION: Final[dict[str, str]] = {
    "bottleneck": (
        "Walk me through where work accumulates most — intake, preparation, "
        "execution, or review?"
    ),
    "business_context": (
        "What does a typical workflow look like from request to delivery?"
    ),
    "pain_point": (
        "Where do delays or errors most often show up in that workflow?"
    ),
    "goals": (
        "Which operational metric matters most right now — throughput, cost per unit, "
        "or conversion rate?"
    ),
    "scale": (
        "Roughly what volume are you handling per day or week?"
    ),
    "integration": (
        "Which systems still require manual handoffs today — ERP, spreadsheets, "
        "email, or coordination outside any system?"
    ),
}

# Highest information-gain questions when context is rich (not first-template)
INFORMATION_GAIN_QUESTIONS: Final[dict[str, str]] = {
    "assignment_logic": (
        "How do coordinators currently decide which driver receives which shipment—"
        "availability, geography, vehicle type, customer priority, or another rule?"
    ),
    "planning_tools": (
        "What tools or systems are currently used for dispatch planning and tracking?"
    ),
    "routing_constraints": (
        "What constraints drive planning decisions—territory, vehicle capacity, "
        "SLA windows, or customer tiers?"
    ),
    "workflow_steps": (
        "Walk me through one order from intake to driver departure—which steps are manual?"
    ),
    "business_clarification": (
        "Are these separate business units, or should I update my understanding of the business?"
    ),
    "backlog_composition": (
        "Of the applications in backlog, approximately what percentage are waiting "
        "for compliance review versus waiting for missing documentation?"
    ),
    "exception_types": (
        "When automation failed, what types of exceptions caused the most manual intervention?"
    ),
    "compliance_prioritization": (
        "How does your compliance team prioritize applications—manually, "
        "or through a rule-based system?"
    ),
    "underwriting_process": (
        "Are financial statement verifications and document checks done via manual review "
        "or automated tools today?"
    ),
}

# Vertical labels that conflict when both asserted
_VERTICAL_SIGNALS: Final[dict[str, tuple[str, ...]]] = {
    "logistics": (
        "logistics", "dispatch", "shipment", "fleet", "driver", "delivery",
        "coordinator", "routing",
    ),
    "manufacturing": (
        "manufacturing", "factory", "production line", "assembly", "plant",
    ),
    "retail": ("retail", "store", "pos", "sku"),
    "financial_services": (
        "lending", "loan", "loans", "underwriting", "commercial lending",
        "origination", "credit", "mortgage",
    ),
}

GENERIC_PHRASES: Final[tuple[str, ...]] = (
    "may be causing",
    "tell me more",
    "what are your goals",
    "can you tell me more about your business",
    "what challenges are you facing",
)

NOISE_STRIP_PATTERNS: Final[tuple[str, ...]] = (
    r"^(hi|hello|hey|thanks|thank you)[,!.?\s]*",
    r"^(can you|could you|please)\s+",
)


@dataclass(frozen=True)
class SignalRegistryV1:
    version: str
    business_model_signals: dict[str, tuple[str, ...]]
    integration_keywords: tuple[str, ...]
    scale_patterns: tuple[str, ...]
    unknown_to_question: dict[str, str]
    generic_phrases: tuple[str, ...]
    noise_strip_patterns: tuple[str, ...]
    explicit_statement_patterns: tuple[str, ...]


_REGISTRY = SignalRegistryV1(
    version=HYPOTHESIS_SIGNALS_VERSION,
    business_model_signals=BUSINESS_MODEL_SIGNALS,
    integration_keywords=INTEGRATION_KEYWORDS,
    scale_patterns=SCALE_PATTERNS,
    unknown_to_question=UNKNOWN_TO_QUESTION,
    generic_phrases=GENERIC_PHRASES,
    noise_strip_patterns=NOISE_STRIP_PATTERNS,
    explicit_statement_patterns=EXPLICIT_STATEMENT_PATTERNS,
)


def get_signal_registry(version: str = ACTIVE_SIGNALS_VERSION) -> SignalRegistryV1:
    if version != "v1":
        raise ValueError(f"Unsupported signal registry version: {version}")
    return _REGISTRY
