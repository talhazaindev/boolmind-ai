"""A/B system prompt variants per product (Phase 4)."""

from __future__ import annotations

import hashlib

VARIANTS: dict[str, dict[str, str]] = {
    "retify": {
        "A": "Emphasize retail ROI and speed to unified insights.",
        "B": "Emphasize technical pipeline depth and ERP/POS integrations.",
    },
    "ecg": {
        "A": "Emphasize clinical accuracy and EMR readiness.",
        "B": "Emphasize OCR quality on low-quality scans.",
    },
    "legal": {
        "A": "Emphasize golden record quality and compliance.",
        "B": "Emphasize semantic discovery and HITL resolution.",
    },
}


def prompt_variant_suffix(session_id: str, product: str | None) -> str:
    if not product or product not in VARIANTS:
        return ""
    bucket = int(hashlib.md5(session_id.encode()).hexdigest()[:8], 16) % 2
    key = "A" if bucket == 0 else "B"
    return f"\nVariant {key}: {VARIANTS[product][key]}"
