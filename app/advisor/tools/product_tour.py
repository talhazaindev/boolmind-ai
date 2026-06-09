"""Product tour JSON loader."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.advisor.constants import PRODUCT_NAMES
from app.core.config import settings

logger = logging.getLogger(__name__)


def _validate_tour(data: dict[str, Any]) -> None:
    required = ("productId", "productName", "totalSteps", "steps")
    for key in required:
        if key not in data:
            raise ValueError(f"Tour missing required field: {key}")
    for step in data["steps"]:
        for field in ("step", "title", "body", "visualType", "visualContent"):
            if field not in step:
                raise ValueError(f"Tour step missing field: {field}")


async def handle(arguments: dict[str, Any]) -> dict[str, Any]:
    product_id = arguments.get("product_id", "retify")
    start_step = int(arguments.get("start_step", 1))
    tours_dir = settings.advisor_tours_path or Path("knowledge-base/tours")
    path = Path(tours_dir) / f"{product_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"Tour not found: {path}")

    data = json.loads(path.read_text(encoding="utf-8"))
    _validate_tour(data)
    steps = [s for s in data["steps"] if s.get("step", 0) >= start_step]
    return {
        "productId": data.get("productId", product_id),
        "productName": data.get("productName", PRODUCT_NAMES.get(product_id, product_id)),
        "tagline": data.get("tagline", ""),
        "totalSteps": data.get("totalSteps", len(steps)),
        "steps": steps,
    }
