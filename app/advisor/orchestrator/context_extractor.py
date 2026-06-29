"""Hybrid context extraction — regex (sync) + optional LLM JSON (async)."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from app.advisor.constants import eval_timeout_ms_for_provider
from app.advisor.integrations.groq_llm import get_chat_llm_client
from app.core.config import settings

logger = logging.getLogger(__name__)

_EXTRACT_PROMPT = """Extract structured business context from the user message. Return JSON only:
{
  "entities": {"daily_volume": number|null, "backlog": number|null, "turnaround_days_current": number|null, "turnaround_days_baseline": number|null},
  "workflow_signals": {"stage_name": "manual|automated|queue"|...},
  "prior_attempts": [{"what": "...", "outcome": "failed|success", "reason": "..."}],
  "user_quote_hooks": ["short phrase from user worth referencing"],
  "inferred_bottleneck_stage": "intake|preparation|execution|quality_gate|delivery|exception_loop"
}
Use null for unknown numbers. Only include fields supported by the text."""


def _strip_json_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


async def extract_context_llm_async(
    message: str,
    history: list[str],
) -> dict[str, Any] | None:
    """Optional LLM enrichment with tight timeout budget."""
    if not settings.get_groq_api_keys():
        return None
    excerpt = "\n".join(history[-4:] + [message])[-2000:]
    messages = [
        {"role": "system", "content": _EXTRACT_PROMPT},
        {"role": "user", "content": excerpt},
    ]
    timeout_s = min(eval_timeout_ms_for_provider(settings.llm_provider) / 1000.0, 0.35)
    try:
        client = get_chat_llm_client()
        raw = await asyncio.wait_for(
            client.create_chat_completion(
                messages=messages,
                max_tokens=256,
                temperature=0.0,
                response_format={"type": "json_object"},
            ),
            timeout=timeout_s,
        )
        return json.loads(_strip_json_fences(raw))
    except Exception as exc:
        logger.debug("context LLM extract skipped: %s", exc)
        return None
