"""Tech depth detection (spec 9.1.2)."""

from __future__ import annotations

import re
from typing import Literal

TechDepth = Literal["engineer", "business", "general"]

ENGINEER_SIGNALS = [
    r"\bapi\b",
    r"\betl\b",
    r"\bschema\b",
    r"\bpipeline\b",
    r"\bsql\b",
    r"\bwarehouse\b",
    r"\bocr\b",
    r"\bhl7\b",
    r"\bfhir\b",
    r"\bembedding\b",
    r"\bvector\b",
    r"\bmicroservice\b",
]

PRODUCT_EXPERT: dict[str, list[str]] = {
    "retify": [r"\bsku\b", r"\bpos\b", r"\berp\b", r"\binventory\b"],
    "ecg": [r"\b12-lead\b", r"\bholter\b", r"\bwfdb\b", r"\bemr\b"],
    "legal": [r"\bgolden\s+schema\b", r"\bcontract\b", r"\bmatter\b", r"\bgdpr\b"],
}


def detect_tech_depth(message: str, active_product: str | None = None) -> TechDepth:
    lower = message.lower()
    engineer_hits = sum(1 for p in ENGINEER_SIGNALS if re.search(p, lower))
    if active_product:
        for pat in PRODUCT_EXPERT.get(active_product, []):
            if re.search(pat, lower):
                engineer_hits += 1
    if engineer_hits >= 2:
        return "engineer"
    business_kw = ("roi", "cost", "team", "business", "outcome", "efficiency")
    if any(kw in lower for kw in business_kw):
        return "business"
    return "general"
