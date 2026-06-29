"""Persist visitor session metadata after each chat turn."""

from __future__ import annotations

import logging

from app.advisor.integrations.redis_store import RedisSessionStore
from app.advisor.orchestrator.product_context import ProductContext, detect_product_in_message
from app.advisor.orchestrator.tech_depth import detect_tech_depth
from app.advisor.orchestrator.tool_gating import effective_readiness
from app.advisor.types import ConversationStage, PageContext, ReadinessFlags, SessionMetadata

logger = logging.getLogger(__name__)


async def ensure_visitor_on_init(
    redis: RedisSessionStore,
    visitor_id: str,
    page: PageContext,
) -> SessionMetadata:
    """
    Persist visitor on chat-init so returning users are recognized before first message.
    First visit: visit_count=1, is_returning=False.
    Later visits (same visitor_id): visit_count incremented, is_returning=True.
    """
    meta = await redis.get_visitor_metadata(visitor_id)
    if meta is None:
        meta = SessionMetadata(
            is_returning=False,
            visit_count=1,
            active_product=page.product_id,
        )
        await redis.save_visitor_metadata(visitor_id, meta)
        return meta

    meta.visit_count = max(meta.visit_count, 1) + 1
    meta.is_returning = True
    if page.product_id:
        meta.active_product = page.product_id
    await redis.save_visitor_metadata(visitor_id, meta)
    return meta


async def persist_visitor_metadata(
    redis: RedisSessionStore,
    visitor_id: str | None,
    message: str,
    product_context: ProductContext,
    existing: SessionMetadata | None,
) -> None:
    if not visitor_id:
        return

    meta = existing or SessionMetadata(is_returning=True, visit_count=1)
    meta.is_returning = True
    meta.visit_count = max(meta.visit_count, 1)
    meta.message_count = (meta.message_count or 0) + 1
    meta.last_topic = message[:120] if message else meta.last_topic
    meta.tech_depth = detect_tech_depth(message, product_context.active_product)

    discussed = list(meta.products_discussed)
    candidates: list[str | None] = [
        product_context.active_product,
        detect_product_in_message(message),
    ]
    candidates.extend(product_context.products_discussed)
    for pid in candidates:
        if pid and pid not in discussed:
            discussed.append(pid)
    meta.products_discussed = discussed

    if product_context.active_product:
        meta.active_product = product_context.active_product
        meta.top_product = product_context.active_product
    elif discussed:
        meta.top_product = discussed[-1]

    await redis.save_visitor_metadata(visitor_id, meta)


def _coerce_qualification_score(value: str | int | float) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return max(1, min(10, value))
    if isinstance(value, float):
        if 0 < value <= 1:
            return max(1, min(10, round(value * 10)))
        return max(1, min(10, round(value)))
    if isinstance(value, str) and value.strip().replace(".", "", 1).isdigit():
        parsed = float(value)
        if 0 < parsed <= 1:
            return max(1, min(10, round(parsed * 10)))
        return max(1, min(10, round(parsed)))
    return None


def _coerce_product_fit_confidence(value: str | int | float) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        conf = float(value)
        if conf > 1 and conf <= 10:
            conf = conf / 10.0
        return max(0.0, min(1.0, conf))
    if isinstance(value, str):
        try:
            conf = float(value.strip())
        except ValueError:
            return None
        if conf > 1 and conf <= 10:
            conf = conf / 10.0
        return max(0.0, min(1.0, conf))
    return None


def _normalize_profile_field(
    key: str,
    value: str | int | float,
) -> tuple[str, str | int | float] | None:
    """Coerce evaluator output; remap confidence accidentally sent as qualification_score."""
    if key == "qualification_score":
        if isinstance(value, float) and 0 < value <= 1:
            conf = _coerce_product_fit_confidence(value)
            return ("product_fit_confidence", conf) if conf is not None else None
        score = _coerce_qualification_score(value)
        return ("qualification_score", score) if score is not None else None
    if key == "product_fit_confidence":
        conf = _coerce_product_fit_confidence(value)
        return ("product_fit_confidence", conf) if conf is not None else None
    if isinstance(value, str):
        return (key, value.strip()) if value.strip() else None
    return (key, value)


def merge_profile_updates(
    meta: SessionMetadata,
    updates: dict[str, str | int | float | bool | None],
) -> SessionMetadata:
    """Apply non-empty profile_updates from turn evaluation."""
    allowed = {
        "business_type",
        "industry",
        "pain_point",
        "goals",
        "data_context",
        "constraints",
        "product_fit",
        "product_fit_confidence",
        "qualification_score",
        "user_sophistication",
        "custom_complexity_confirmed",
        "primary_goal",
        "growth_blocker",
        "channels_active",
        "business_model",
        "funnel_stage",
        "reasoning_phase",
    }
    data = meta.model_dump()
    for key, value in updates.items():
        if key not in allowed:
            continue
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        if key == "custom_complexity_confirmed" and isinstance(value, bool):
            data[key] = value
            continue
        if key == "user_sophistication" and value in ("low", "medium", "high"):
            data[key] = value
            continue
        if key == "primary_goal" and value in ("growth_marketing", "operations"):
            data[key] = value
            continue
        if key == "growth_blocker" and value in ("discovery", "conversion", "retention"):
            data[key] = value
            continue
        if key == "channels_active" and isinstance(value, list):
            data[key] = [str(c) for c in value]
            continue
        if key == "business_model" and value in (
            "saas",
            "subscription",
            "service",
            "education",
            "local_retail",
            "unknown",
        ):
            data[key] = value
            continue
        if key == "reasoning_phase" and value in (
            "discovery",
            "hypothesis_generation",
            "hypothesis_testing",
            "convergence",
            "strategic_insight",
            "solution_exploration",
            "boolmind_positioning",
        ):
            data[key] = value
            continue
        if key == "funnel_stage" and isinstance(value, str) and value.strip():
            data[key] = value.strip()
            continue
        if not isinstance(value, (str, int, float)):
            continue
        normalized = _normalize_profile_field(key, value)
        if normalized is None:
            continue
        norm_key, norm_value = normalized
        data[norm_key] = norm_value
    return SessionMetadata.model_validate(data)


async def persist_discovery_evaluation(
    redis: RedisSessionStore,
    visitor_id: str | None,
    existing: SessionMetadata | None,
    *,
    stage: str,
    profile_updates: dict[str, str | int | float | bool | None],
    missing_fields: list[str],
    llm_readiness: ReadinessFlags,
    user_sophistication: str | None = None,
) -> SessionMetadata:
    """Merge evaluation into visitor metadata and persist."""
    meta = existing or SessionMetadata(is_returning=True, visit_count=1)
    try:
        meta = merge_profile_updates(meta, profile_updates)
    except Exception as e:
        logger.warning("merge_profile_updates failed, keeping prior metadata: %s", e)
        meta = existing or SessionMetadata(is_returning=True, visit_count=1)
    valid_stages: tuple[ConversationStage, ...] = (
        "EXPLORE",
        "INTEREST",
        "QUALIFY",
        "CAPTURE",
        "BOOK",
        "DONE",
    )
    if stage in valid_stages:
        meta.stage_reached = stage  # type: ignore[assignment]
    meta.missing_fields = list(missing_fields)
    meta.readiness = effective_readiness(meta, llm_readiness)
    if user_sophistication in ("low", "medium", "high"):
        meta.user_sophistication = user_sophistication  # type: ignore[assignment]
    if visitor_id:
        await redis.save_visitor_metadata(visitor_id, meta)
    return meta


async def clear_visitor_conversation_context(
    redis: RedisSessionStore,
    visitor_id: str,
) -> None:
    """Reset per-chat context on visitor record; keep name/email and stage."""
    existing = await redis.get_visitor_metadata(visitor_id)
    if existing is None:
        return
    meta = existing.model_copy(
        update={
            "last_topic": None,
            "products_discussed": [],
            "active_product": None,
            "top_product": None,
        }
    )
    await redis.save_visitor_metadata(visitor_id, meta)
