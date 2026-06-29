"""FIDP image generation (Section 17)."""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from app.advisor.integrations.image_gen import PLACEHOLDER_URL, get_image_gen_client
from app.core.config import settings

logger = logging.getLogger(__name__)

BRAND_PROMPT = (
    "Futuristic data intelligence dashboard UI, purple #5B4FD6 and cyan #3DBDD6 accents, "
    "clean minimal SaaS, no text labels, no logos, abstract workflow visualization"
)


async def handle(arguments: dict[str, Any]) -> dict[str, Any]:
    conv_id = arguments.get("conversation_id", "session")
    product = arguments.get("primary_product", "retify")
    seed = int(hashlib.sha256(conv_id.encode()).hexdigest()[:8], 16) % (2**31)

    prompt = f"{BRAND_PROMPT}, {product} product context, professional enterprise"
    client = get_image_gen_client()
    try:
        timeout_s = 180.0 if settings.image_gen_provider.strip().lower() == "local" else 15.0
        result = await client.generate(prompt=prompt[:200], seed=seed, timeout_s=timeout_s)
        return {
            "status": "generated",
            "imageUrl": result.url,
            "prompt": prompt[:200],
            "seed": seed,
            "product": product,
            "expiresInHours": 24,
            "provider": settings.image_gen_provider,
        }
    except Exception as e:
        logger.warning("FIDP generation failed: %s", e)
        return {
            "status": "placeholder",
            "imageUrl": PLACEHOLDER_URL,
            "message": "Image generation unavailable; placeholder shown.",
            "provider": settings.image_gen_provider,
            "localReady": settings.local_image_gen_ready,
        }
