"""Boolmind Advisor API — /api/chat and /api/chat-init."""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from app.advisor.analytics.events import session_start
from app.advisor.constants import PRODUCT_NAMES
from app.advisor.integrations.failed_operations import get_memory_queue
from app.advisor.integrations.failed_ops_retry import replay_all_queues
from app.advisor.integrations.integration_health import check_all as integration_health_check
from app.advisor.integrations.supabase_client import fetch_chat_events, fetch_failed_operations
from app.advisor.monitoring.rollup import metrics_summary
from app.advisor.monitoring.prometheus_metrics import set_failed_ops_pending
from app.advisor.security import (
    check_rate_limit,
    client_ip,
    sanitize_message,
    verify_chat_signature,
)
from app.advisor.integrations.redis_store import get_redis_store
from app.advisor.orchestrator.loop import AdvisorChatLoop
from app.advisor.orchestrator.page_context import opening_message_for_page, product_id_from_url
from app.advisor.orchestrator.product_context import resolve_product_context
from app.advisor.orchestrator.session_metadata import (
    clear_visitor_conversation_context,
    ensure_visitor_on_init,
)
from app.advisor.proactive import get_proactive_triggers
from app.advisor.types import PageContext, SessionMetadata
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["advisor"])


class PageContextBody(BaseModel):
    title: str = ""
    url: str = ""
    product_id: str | None = None
    product_name: str | None = None


class ChatRequest(BaseModel):
    session_id: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1, max_length=2000)
    page_context: PageContextBody = Field(default_factory=PageContextBody)
    user_timezone: str = "UTC"
    visitor_id: str | None = None
    user_language: str = "en"


class ChatInitRequest(BaseModel):
    visitor_id: str | None = None
    page_context: PageContextBody = Field(default_factory=PageContextBody)


class ChatClearRequest(BaseModel):
    session_id: str = Field(..., min_length=1)
    visitor_id: str | None = None
    page_context: PageContextBody = Field(default_factory=PageContextBody)


def _ensure_tier_a() -> None:
    if not settings.advisor_tier_a_ready:
        missing = []
        if not settings.llm_configured:
            if settings.llm_provider_resolved == "ollama":
                missing.append("OLLAMA_BASE_URL / OLLAMA_MODEL")
            else:
                missing.append("GROQ_API_KEY or GROQ_API_KEY_1..4")
        if not settings.embeddings_configured:
            missing.append("EMBEDDING_PROVIDER / OPENAI_API_KEY")
        if not settings.pinecone_configured:
            missing.append("PINECONE_*")
        if not settings.redis_configured:
            missing.append("REDIS_URL or UPSTASH_REDIS_*")
        raise HTTPException(
            status_code=503,
            detail=f"Advisor not configured. Missing: {', '.join(missing)}",
        )


def _page_context_from_body(body: PageContextBody) -> PageContext:
    pid, pname = product_id_from_url(body.url)
    return PageContext(
        title=body.title,
        url=body.url,
        product_id=body.product_id or pid,
        product_name=body.product_name or pname,
    )


@router.post("/chat-init")
async def chat_init(body: ChatInitRequest, request: Request) -> dict[str, Any]:
    _ensure_tier_a()
    ip = client_ip(request)
    check_rate_limit(f"init:{ip}", settings.chat_init_rate_limit_per_hour, 3600)
    redis = get_redis_store()
    visitor_id = body.visitor_id or str(uuid.uuid4())
    session_id = str(uuid.uuid4())
    page = _page_context_from_body(body.page_context)

    meta = await ensure_visitor_on_init(redis, visitor_id, page)
    is_returning = meta.visit_count > 1
    page_opening = opening_message_for_page(page)
    opening: str | None
    if is_returning:
        if meta.visitor_name:
            opening = (
                f"Welcome back, {meta.visitor_name}. "
                f"Last time we discussed {meta.last_topic or 'our products'}. "
                "How can I help you continue?"
            )
        elif meta.last_topic:
            opening = (
                f"Welcome back. Last time we discussed {meta.last_topic}. "
                "Want to continue or explore something else?"
            )
        else:
            opening = f"Welcome back. {page_opening}"
    else:
        opening = page_opening

    suggested_tour = page.product_id if page.product_id else None
    proactive = get_proactive_triggers(page, is_returning)
    session_start(session_id, page.product_id)

    return {
        "sessionId": session_id,
        "visitorId": visitor_id,
        "isReturning": is_returning,
        "openingMessage": opening,
        "productContext": {
            "activeProduct": page.product_id,
            "productName": page.product_name or (
                PRODUCT_NAMES.get(page.product_id, "") if page.product_id else None
            ),
            "suggestedTour": suggested_tour,
            "productsDiscussed": meta.products_discussed if meta else [],
        },
        "proactiveTriggers": proactive,
        "supportedLanguages": ["en", "ur", "ar"],
    }


async def _chat_sse_generator(
    body: ChatRequest,
) -> AsyncIterator[dict[str, str]]:
    try:
        redis = get_redis_store()
        page = _page_context_from_body(body.page_context)
        visitor_id = body.visitor_id
        session_meta = None
        if visitor_id:
            session_meta = await redis.get_visitor_metadata(visitor_id)

        product_ctx = resolve_product_context(
            page,
            session_meta,
            body.message,
        )
        loop = AdvisorChatLoop(redis)
        async for event in loop.stream_chat(
            session_id=body.session_id,
            message=body.message,
            page_context=page,
            visitor_id=visitor_id,
            user_language=body.user_language,
            product_context=product_ctx,
            session_meta=session_meta,
        ):
            yield {"data": json.dumps(event)}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Chat stream error: %s", e)
        yield {
            "data": json.dumps(
                {"type": "error", "code": "INTERNAL", "message": str(e)[:200]}
            )
        }


@router.post("/chat-clear")
async def chat_clear(body: ChatClearRequest) -> dict[str, Any]:
    """Clear Redis conversation history and start a fresh session."""
    _ensure_tier_a()
    redis = get_redis_store()
    await redis.clear_history(body.session_id)
    if body.visitor_id:
        await clear_visitor_conversation_context(redis, body.visitor_id)

    visitor_id = body.visitor_id or str(uuid.uuid4())
    session_id = str(uuid.uuid4())
    page = _page_context_from_body(body.page_context)
    opening = opening_message_for_page(page)

    return {
        "sessionId": session_id,
        "visitorId": visitor_id,
        "cleared": True,
        "openingMessage": opening,
        "productContext": {
            "activeProduct": page.product_id,
            "productName": page.product_name or (
                PRODUCT_NAMES.get(page.product_id, "") if page.product_id else None
            ),
            "productsDiscussed": [],
        },
    }


@router.post("/chat")
async def chat(request: Request) -> EventSourceResponse:
    _ensure_tier_a()
    raw = await request.body()
    verify_chat_signature(request, raw)
    ip = client_ip(request)
    check_rate_limit(f"chat:{ip}", settings.chat_rate_limit_per_minute)
    data = json.loads(raw)
    data["message"] = sanitize_message(data.get("message", ""))
    body = ChatRequest.model_validate(data)
    return EventSourceResponse(_chat_sse_generator(body))


@router.post("/retry-failed-ops")
async def retry_failed_ops() -> dict[str, Any]:
    """Retry queued failed operations (memory + Supabase)."""
    result = await replay_all_queues()
    set_failed_ops_pending(result["pending"])
    return result


@router.get("/admin/integrations/health")
async def admin_integrations_health() -> dict[str, Any]:
    """Live connectivity probes for configured integrations."""
    return await integration_health_check()


@router.get("/admin/stats")
async def admin_stats() -> dict[str, Any]:
    """Lightweight admin visibility (Phase 4)."""
    queue = get_memory_queue()
    remote_count = 0
    if settings.supabase_configured:
        remote_count = len(await fetch_failed_operations())
    set_failed_ops_pending(len(queue) + remote_count)
    health = await integration_health_check()
    integrations = {
        "hubspot": settings.hubspot_configured,
        "calcom": settings.calcom_configured,
        "resend": settings.resend_configured,
        "supabase": settings.supabase_configured,
        "posthog": settings.posthog_configured,
        "sentry": settings.sentry_configured,
    }
    integration_health = {
        name: health.get(name, {}).get("status", "OFF" if not integrations.get(name) else "ON")
        for name in integrations
    }
    return {
        "failedOperations": len(queue) + remote_count,
        "advisorReady": settings.advisor_tier_a_ready,
        "telemetryEnabled": settings.telemetry_enabled,
        "integrations": integrations,
        "integrationHealth": integration_health,
        "links": {
            "grafana": "http://localhost:3001",
            "posthog": settings.posthog_host if settings.posthog_configured else None,
            "sentry": "https://sentry.io/issues/" if settings.sentry_configured else None,
        },
    }


@router.get("/admin/metrics/summary")
async def admin_metrics_summary() -> dict[str, Any]:
    """Aggregated telemetry rollup for the last hour."""
    return metrics_summary()


@router.get("/admin/sessions/{session_id}/events")
async def admin_session_events(session_id: str) -> dict[str, Any]:
    """Chat event audit trail for a session (Supabase chat_events)."""
    events = await fetch_chat_events(session_id)
    return {"session_id": session_id, "events": events, "count": len(events)}


@router.get("/admin/failed-ops")
async def admin_failed_ops() -> dict[str, Any]:
    """List pending failed operations (memory + Supabase)."""
    memory = [{**item, "source": "memory"} for item in get_memory_queue()]
    remote: list[dict[str, Any]] = []
    if settings.supabase_configured:
        rows = await fetch_failed_operations()
        for row in rows:
            payload = row.get("payload") or {}
            remote.append(
                {
                    "id": row.get("id"),
                    "source": "supabase",
                    "operation": row.get("operation"),
                    "error": row.get("error_message", ""),
                    "retries": row.get("retries", 0),
                    "created_at": row.get("created_at"),
                    "payload": payload,
                }
            )
    combined = memory + remote
    return {
        "memory": memory,
        "supabase": remote,
        "combined": combined,
        "pending": len(combined),
    }
