"""Per-turn LLM judge for discovery profile and stage (Phase 7)."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from app.advisor.analytics.events import discovery_evaluated
from app.advisor.config.products import products_summary_for_evaluator
from app.advisor.constants import EVAL_TIMEOUT_MS
from app.advisor.integrations.groq_llm import get_groq_rotator
from app.advisor.orchestrator.custom_complexity import is_custom_complexity_confirmed
from app.advisor.orchestrator.diagnosis_router import should_diagnose
from app.advisor.orchestrator.goal_context import (
    detect_primary_goal,
    filter_missing_for_goal,
    growth_discovery_question,
    operations_discovery_question,
    profitability_discovery_question,
    workforce_discovery_question,
)
from app.advisor.orchestrator.product_context import ProductContext
from app.advisor.orchestrator.tool_gating import effective_readiness
from app.advisor.types import (
    ConversationStage,
    PageContext,
    ReadinessFlags,
    SessionMetadata,
    TurnEvaluation,
    UserSophistication,
)

logger = logging.getLogger(__name__)

_EVAL_HISTORY_CAP = 8

_LOW_SOPHISTICATION_SIGNALS = (
    "i'm not technical",
    "im not technical",
    "not a tech person",
    "don't know what",
    "dont know what",
    "what does that mean",
    "i don't understand",
    "never run a website",
)


def _detect_user_sophistication(message: str) -> UserSophistication | None:
    lower = message.lower()
    if any(sig in lower for sig in _LOW_SOPHISTICATION_SIGNALS):
        return "low"
    tech_terms = sum(
        1
        for term in ("api", "integration", "architecture", "rbac", "database", "backend")
        if term in lower
    )
    if tech_terms >= 2:
        return "high"
    if tech_terms == 1:
        return "medium"
    return None


def _should_recommend(missing: list[str]) -> bool:
    if len(missing) <= 1:
        return True
    if len(missing) == 2 and "product_fit" in missing:
        return True
    return False


def _profile_snapshot(meta: SessionMetadata) -> dict[str, Any]:
    return {
        "business_type": meta.business_type,
        "industry": meta.industry,
        "pain_point": meta.pain_point,
        "goals": meta.goals,
        "data_context": meta.data_context,
        "constraints": meta.constraints,
        "product_fit": meta.product_fit,
        "product_fit_confidence": meta.product_fit_confidence,
        "qualification_score": meta.qualification_score,
        "stage_reached": meta.stage_reached,
        "custom_complexity_confirmed": meta.custom_complexity_confirmed,
        "user_sophistication": meta.user_sophistication,
    }


def _history_excerpt(history: list[dict[str, Any]]) -> list[dict[str, str]]:
    excerpt: list[dict[str, str]] = []
    for msg in history[-_EVAL_HISTORY_CAP:]:
        role = msg.get("role", "")
        if role not in ("user", "assistant"):
            continue
        content = msg.get("content") or ""
        if isinstance(content, str) and content.strip():
            excerpt.append({"role": role, "content": content[:400]})
    return excerpt


def _default_evaluation(
    meta: SessionMetadata,
    *,
    message: str = "",
    history_texts: list[str] | None = None,
) -> TurnEvaluation:
    primary_goal = detect_primary_goal(meta, message, history_texts)
    missing: list[str] = []
    if not (meta.business_type or meta.industry):
        missing.append("business_context")
    if not meta.pain_point:
        missing.append("pain_point")
    if not meta.goals:
        missing.append("goals")
    if not meta.data_context and primary_goal not in (
        "growth_marketing",
        "profitability",
        "workforce",
    ):
        missing.append("data_context")
    if (
        (not meta.product_fit or meta.product_fit == "undecided")
        and primary_goal not in ("growth_marketing", "profitability", "workforce")
    ):
        missing.append("product_fit")
    missing = filter_missing_for_goal(missing, primary_goal)

    question = "What brings you to Boolmind today?"
    if primary_goal == "workforce" and (meta.business_type or meta.industry or meta.pain_point):
        question = workforce_discovery_question(meta, message, history_texts)
    elif primary_goal == "profitability" and (meta.business_type or meta.industry or meta.pain_point):
        question = profitability_discovery_question(meta, message, history_texts)
    elif primary_goal == "operations" and (meta.business_type or meta.industry or meta.pain_point):
        question = operations_discovery_question(meta, message, history_texts)
    elif primary_goal == "growth_marketing" and (meta.business_type or meta.industry):
        question = growth_discovery_question(meta, message)
    elif "business_context" in missing:
        question = "What type of business or industry are you in?"
    elif "pain_point" in missing:
        question = "What's the biggest friction in how you run things today?"
    elif "goals" in missing:
        question = "What would success look like for you in the next 90 days?"
    elif "product_fit" in missing:
        question = (
            "Which fits best — Retify (retail data), ECG (clinical docs), Legal (legal data), "
            "Forecasting Engine (demand planning), or a custom-built solution?"
        )
    elif "data_context" in missing:
        question = "What systems or tools are you using to run things today?"

    return TurnEvaluation(
        stage=meta.stage_reached,
        missing_fields=missing,
        next_discovery_question=question,
        readiness=meta.readiness,
        reasoning="fallback evaluation",
        should_recommend=_should_recommend(missing),
        user_sophistication=meta.user_sophistication,
    )


def _parse_evaluation(raw: str, meta: SessionMetadata) -> TurnEvaluation:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Evaluator returned invalid JSON")
        return _default_evaluation(meta)

    stage = data.get("stage", meta.stage_reached)
    if stage not in ("EXPLORE", "INTEREST", "QUALIFY", "CAPTURE", "BOOK", "DONE"):
        stage = meta.stage_reached

    readiness_raw = data.get("readiness") or {}
    readiness = ReadinessFlags(
        architecture=bool(readiness_raw.get("architecture")),
        product_tour=bool(readiness_raw.get("product_tour")),
        fidp=bool(readiness_raw.get("fidp")),
        lead_capture=bool(readiness_raw.get("lead_capture")),
        booking=bool(readiness_raw.get("booking")),
    )

    profile_updates = data.get("profile_updates") or {}
    if not isinstance(profile_updates, dict):
        profile_updates = {}

    missing = data.get("missing_fields") or []
    if not isinstance(missing, list):
        missing = []
    missing_strs = [str(m) for m in missing]

    merged_meta = meta.model_copy()
    for key, value in profile_updates.items():
        if hasattr(merged_meta, key) and value is not None:
            setattr(merged_meta, key, value)
    if stage:
        merged_meta.stage_reached = stage  # type: ignore[assignment]

    effective = effective_readiness(merged_meta, readiness)

    soph_raw = data.get("user_sophistication")
    sophistication: UserSophistication | None = None
    if soph_raw in ("low", "medium", "high"):
        sophistication = soph_raw  # type: ignore[assignment]

    should_rec = data.get("should_recommend")
    if not isinstance(should_rec, bool):
        should_rec = _should_recommend(missing_strs)

    return TurnEvaluation(
        stage=stage,  # type: ignore[arg-type]
        profile_updates=profile_updates,
        missing_fields=missing_strs,
        next_discovery_question=str(data.get("next_discovery_question") or ""),
        readiness=effective,
        reasoning=str(data.get("reasoning") or ""),
        should_recommend=should_rec,
        user_sophistication=sophistication,
    )


def _apply_goal_context(
    evaluation: TurnEvaluation,
    meta: SessionMetadata,
    *,
    message: str,
    history_texts: list[str] | None,
) -> TurnEvaluation:
    """Lock primary goal and filter missing fields that cause domain drift."""
    texts = history_texts or []
    primary = detect_primary_goal(meta, message, texts)
    if primary != "unknown":
        evaluation.profile_updates.setdefault("primary_goal", primary)

    merged = meta.model_copy()
    if primary != "unknown":
        merged.primary_goal = primary

    filtered = filter_missing_for_goal(evaluation.missing_fields, primary)
    evaluation.missing_fields = filtered

    if primary == "growth_marketing":
        drift_ops = any(
            kw in evaluation.next_discovery_question.lower()
            for kw in ("document", "data management", "workflow", "retify", "ecg", "legal")
        )
        if drift_ops or not evaluation.next_discovery_question:
            evaluation.next_discovery_question = growth_discovery_question(merged, message)

    if primary == "operations":
        drift_marketing = any(
            kw in evaluation.next_discovery_question.lower()
            for kw in ("website", "seo", "social media", "google business", "linkedin", "landing page")
        )
        if drift_marketing or not evaluation.next_discovery_question:
            evaluation.next_discovery_question = operations_discovery_question(
                merged, message, texts
            )

    if primary == "profitability":
        drift_throughput = any(
            kw in evaluation.next_discovery_question.lower()
            for kw in ("delay", "materials", "approval", "production capacity", "bottleneck")
        )
        if drift_throughput or not evaluation.next_discovery_question:
            evaluation.next_discovery_question = profitability_discovery_question(
                merged, message, texts
            )

    if primary == "workforce":
        drift_solutions = any(
            kw in evaluation.next_discovery_question.lower()
            for kw in (
                "have you considered",
                "professional development",
                "mentorship",
                "staffing adjustment",
                "implement",
            )
        )
        if drift_solutions or not evaluation.next_discovery_question:
            evaluation.next_discovery_question = workforce_discovery_question(
                merged, message, texts
            )

    if should_diagnose(merged, message, texts):
        evaluation.should_recommend = False
    else:
        evaluation.should_recommend = _should_recommend(filtered)
    return evaluation


def _history_user_texts(history: list[dict[str, Any]]) -> list[str]:
    texts: list[str] = []
    for msg in history:
        if msg.get("role") == "user":
            content = msg.get("content")
            if isinstance(content, str) and content.strip():
                texts.append(content)
    return texts


async def evaluate_turn(
    *,
    session_id: str,
    user_message: str,
    history: list[dict[str, Any]],
    profile: SessionMetadata,
    product_context: ProductContext,
    page_context: PageContext,
) -> TurnEvaluation:
    """LLM structured judge; falls back to rule-based defaults on timeout/error."""
    system = (
        "You evaluate Boolmind Advisor chat turns. Output JSON only.\n"
        "Extract business discovery fields from the latest user message. "
        "Extract business_type and industry from the user's words (any business, any vertical).\n"
        f"Available offerings: {products_summary_for_evaluator()}.\n"
        "Stages: EXPLORE, INTEREST, QUALIFY, CAPTURE, BOOK.\n"
        "primary_goal: growth_marketing if user wants customers/growth/discovery/marketing; "
        "profitability if profits/margins/pricing are flat while business is busy or growing; "
        "workforce if staff/teacher/instructor turnover, recruiting burden, or retention "
        "(compensation vs workload vs management) — even when enrollment is growing; "
        "operations if user has delivery delays, backlog, materials waits, or cannot fulfill "
        "orders (throughput — NOT profit or turnover questions). "
        "Busy + flat profits = profitability. Growing enrollment + turnover = workforce. "
        "When primary_goal=growth_marketing: NEVER ask about document management, data pipelines, "
        "or internal ops. NEVER route accounting/bookkeeping to legal/ecg/retify catalog products.\n"
        "product_fit routing: fleet/transport/driver workload/bespoke apps/marketplace/"
        "mobile app with confirmed complexity -> custom_solutions. "
        "Do NOT route online presence/website/marketing alone to custom_solutions — "
        "wait until user confirms enrollment, payments, scheduling, or multi-role needs.\n"
        "Retail POS unification -> retify. Clinical ECG docs -> ecg. Legal datasets -> legal. "
        "Sales/demand forecasting -> forecasting. Accounting/bookkeeping is NOT legal or ecg. "
        "Do NOT assign catalog products to unrelated verticals.\n"
        "When primary_goal=growth_marketing, omit data_context and product_fit from missing_fields.\n"
        "user_sophistication: low if user says not technical; high if uses technical terms; "
        "medium otherwise. Omit if unclear.\n"
        "should_recommend: true when missing_fields has <=1 item or only product_fit remains.\n"
        "Set readiness true only when profile has enough context for that deliverable.\n"
        "Required before any readiness: business_type OR industry, pain_point, goals.\n"
        "product_tour needs catalog product_fit with confidence>=0.7 (not custom_solutions).\n"
        "architecture/fidp need data_context.\n"
        "lead_capture needs stage>=CAPTURE.\n"
        "booking needs visitor name+email (only if mentioned).\n"
        "qualification_score: integer 1-10 only (lead quality). "
        "product_fit_confidence: float 0.0-1.0 only (never put 0.7 in qualification_score).\n"
        "Never extract or store phone numbers.\n"
        'JSON schema: {"stage","profile_updates":{...},"missing_fields":[],"'
        '"next_discovery_question":"","readiness":{...},"reasoning":"",'
        '"should_recommend":false,"user_sophistication":"low|medium|high|null",'
        '"profile_updates":{"primary_goal":"growth_marketing|operations|null",...}}'
    )

    user_payload = {
        "current_profile": _profile_snapshot(profile),
        "page_url": page_context.url,
        "active_product": product_context.active_product,
        "recent_messages": _history_excerpt(history),
        "latest_user_message": user_message,
    }

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(user_payload)},
    ]

    try:
        groq = get_groq_rotator()
        raw = await asyncio.wait_for(
            groq.create_chat_completion(
                messages=messages,
                response_format={"type": "json_object"},
                max_tokens=512,
            ),
            timeout=EVAL_TIMEOUT_MS / 1000.0,
        )
        evaluation = _parse_evaluation(raw, profile)
    except Exception as e:
        logger.warning("evaluate_turn failed: %s", e)
        history_texts = _history_user_texts(history)
        evaluation = _default_evaluation(
            profile, message=user_message, history_texts=history_texts
        )

    history_texts = _history_user_texts(history)
    evaluation = _apply_goal_context(
        evaluation,
        profile,
        message=user_message,
        history_texts=history_texts,
    )

    if not evaluation.next_discovery_question:
        evaluation.next_discovery_question = _default_evaluation(
            profile, message=user_message, history_texts=history_texts
        ).next_discovery_question

    detected_soph = _detect_user_sophistication(user_message)
    if detected_soph:
        evaluation.user_sophistication = detected_soph
        if "user_sophistication" not in evaluation.profile_updates:
            evaluation.profile_updates["user_sophistication"] = detected_soph

    all_user_texts = _history_user_texts(history) + [user_message]
    if is_custom_complexity_confirmed(*all_user_texts):
        evaluation.profile_updates["custom_complexity_confirmed"] = True  # type: ignore[assignment]

    discovery_evaluated(
        session_id,
        evaluation.stage,
        len(evaluation.missing_fields),
    )
    return evaluation
