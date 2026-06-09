"""Conversation mode selection for advisor consulting behavior."""

from __future__ import annotations

from app.advisor.orchestrator.intent_classifier import IntentResult, classify_intent
from app.advisor.orchestrator.diagnosis_router import should_diagnose
from app.advisor.orchestrator.tool_gating import has_minimum_discovery_context, is_tool_allowed
from app.advisor.types import ConversationMode, ReadinessFlags, SessionMetadata

_ADVISORY_INTENTS = frozenset({
    "advice_request",
    "roi_analysis",
    "objection",
    "channel_prioritization",
})


def select_conversation_mode(
    message: str,
    meta: SessionMetadata,
    readiness: ReadinessFlags,
    *,
    deferred_tool: str | None = None,
    product_fit: str | None = None,
    history_texts: list[str] | None = None,
) -> ConversationMode:
    """Deterministic mode selection — no extra LLM call."""
    intent = classify_intent(message)

    if deferred_tool and is_tool_allowed(deferred_tool, readiness, product_fit=product_fit):
        return "deliver"

    if should_diagnose(meta, message, history_texts):
        return "diagnose"

    if intent.intent in _ADVISORY_INTENTS:
        return "advise"

    if meta.consecutive_question_turns >= 2:
        if has_minimum_discovery_context(meta):
            return "recommend"
        return "advise"

    if meta.message_count >= 3 and has_minimum_discovery_context(meta):
        return "recommend"

    return "discover"


def mode_prompt_suffix(mode: ConversationMode) -> str:
    """Inject mode-specific instructions into the system prompt."""
    if mode == "discover":
        return (
            "\n\nCONVERSATION MODE: DISCOVER — "
            "Provide 1-2 sentences of value or context BEFORE your question. "
            "End with at most ONE discovery question targeting missing profile fields."
        )
    if mode == "diagnose":
        return (
            "\n\nCONVERSATION MODE: DIAGNOSE — "
            "State strategic inference FIRST (what's working vs not). "
            "Explain tradeoffs (why the wrong fix wastes money/time). "
            "Do NOT recommend tools, software, hiring, or tactics until root cause is validated. "
            "One comparative diagnostic question at the end (max ONE). No Boolmind pitch."
        )
    if mode == "advise":
        return (
            "\n\nCONVERSATION MODE: ADVISE — "
            "Flow: diagnosis insight → prioritized tactics → optional question. "
            "Industry-specific, not generic SEO/post-more-content. "
            "Boolmind only when Phase 3+ warrants it."
        )
    if mode == "recommend":
        return (
            "\n\nCONVERSATION MODE: RECOMMEND — "
            "Synthesize findings, then industry-specific phased plan. "
            "Free channels before website. Boolmind only when complexity/budget justify. "
            "End with at most ONE optional question."
        )
    return (
        "\n\nCONVERSATION MODE: DELIVER — "
        "Deliver the tool result or phased plan. No discovery question."
    )


def intent_prompt_suffix(intent: IntentResult, mode: ConversationMode | None = None) -> str:
    """Additional prompt injection based on classified intent."""
    if intent.intent == "channel_prioritization":
        return (
            "\n\nINTENT: CHANNEL_PRIORITIZATION — "
            "User is confused about website vs SEO vs social vs ads vs AI. "
            "Educate on how channel choice depends on business type BEFORE asking business type. "
            "No Boolmind pitch."
        )
    if intent.intent == "concept_explanation":
        return (
            "\n\nINTENT: CONCEPT_EXPLANATION — "
            "Educate clearly in plain language. Do NOT pitch Boolmind, landing pages, "
            "or phased implementation plans. Answer the concept only."
        )
    if intent.intent == "advice_request":
        if mode == "diagnose":
            return (
                "\n\nINTENT: ADVICE_REQUEST (DIAGNOSE MODE) — "
                "User wants guidance but root cause is unconfirmed. "
                "Give strategic insight and tradeoff analysis FIRST. "
                "Do NOT recommend tools, software, or hiring yet. "
                "End with ONE validation question."
            )
        return (
            "\n\nINTENT: ADVICE_REQUEST — "
            "User wants your recommendation. Answer directly before asking anything."
        )
    if intent.intent == "roi_analysis":
        return (
            "\n\nINTENT: ROI_ANALYSIS — "
            "Explain ROI framework first (revenue gain + cost savings − investment). "
            "Use a worked example if helpful. Then ask for 1–2 inputs. "
            "Conclude with when a Boolmind engagement pays off."
        )
    if intent.intent == "objection":
        return (
            "\n\nINTENT: OBJECTION — "
            "Acknowledge alternative trade-offs briefly, then explain Boolmind differentiation "
            "(integration, scale, support, tailored workflows). "
            "Do NOT recommend walking away from Boolmind unless need is trivial AND user "
            "explicitly asked whether to hire Boolmind."
        )
    if intent.intent == "product_comparison":
        return (
            "\n\nINTENT: PRODUCT_COMPARISON — "
            "Use product_compare for catalog products when appropriate."
        )
    if intent.intent == "product_tour":
        return (
            "\n\nINTENT: PRODUCT_TOUR — "
            "Offer product_tour when readiness.product_tour is true."
        )
    return ""


def update_consecutive_question_turns(
    meta: SessionMetadata,
    assistant_text: str,
    mode: ConversationMode,
) -> int:
    """Track consecutive question-only turns for mode forcing."""
    if mode in ("advise", "recommend", "deliver", "diagnose"):
        return 0
    if "?" in assistant_text:
        return meta.consecutive_question_turns + 1
    return 0
