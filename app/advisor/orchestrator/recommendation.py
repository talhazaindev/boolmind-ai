"""Deterministic recommendation block injection for advise/recommend modes."""

from __future__ import annotations

from app.advisor.orchestrator.industry_strategy import (
    business_label,
    generic_phased_framework,
    is_micro_budget,
    micro_budget_advisory,
    pushback_for_website_question,
    rag_industry_guidance_line,
    should_defer_boolmind_pitch,
)
from app.advisor.orchestrator.diagnosis_router import (
    build_diagnosis_block_for_dimension,
    should_diagnose,
)
from app.advisor.orchestrator.operations_diagnosis import (
    infer_ops_bottleneck,
    operations_strategic_insight,
    strategic_tradeoff_insight as ops_tradeoff_insight,
)
from app.advisor.orchestrator.problem_dimension import detect_problem_dimension
from app.advisor.orchestrator.profitability_diagnosis import (
    infer_profit_hypothesis,
    profitability_strategic_insight,
    strategic_tradeoff_insight as profit_tradeoff_insight,
)
from app.advisor.orchestrator.workforce_diagnosis import (
    infer_workforce_hypothesis,
    strategic_tradeoff_insight as workforce_tradeoff_insight,
    workforce_strategic_insight,
)
from app.advisor.orchestrator.strategy_diagnosis import strategic_insight
from app.advisor.types import ConversationMode, SessionMetadata


def _known_summary(meta: SessionMetadata) -> str:
    parts: list[str] = []
    if meta.business_type:
        parts.append(f"business={meta.business_type}")
    if meta.industry:
        parts.append(f"industry={meta.industry}")
    if meta.pain_point:
        parts.append(f"pain={meta.pain_point}")
    if meta.goals:
        parts.append(f"goals={meta.goals}")
    if meta.constraints:
        parts.append(f"constraints={meta.constraints}")
    if meta.data_context:
        parts.append(f"data_context={meta.data_context}")
    if meta.product_fit and meta.product_fit != "undecided":
        parts.append(f"product_fit={meta.product_fit}")
    return ", ".join(parts) if parts else "early discovery"


def should_synthesize(meta: SessionMetadata) -> bool:
    if meta.reasoning_phase not in ("discovery", "convergence"):
        return False
    if meta.message_count < 3 or meta.message_count % 3 != 0:
        return False
    return bool(meta.business_type or meta.industry or meta.pain_point)


def build_synthesis_block(
    meta: SessionMetadata,
    *,
    message: str = "",
    history: list[str] | None = None,
) -> str:
    known = _known_summary(meta)
    label = business_label(meta)
    dimension = detect_problem_dimension(meta, message, history)
    if dimension == "profitability":
        insight = profitability_strategic_insight(meta, message, history)
        tradeoff = profit_tradeoff_insight(meta, message, history)
        return (
            f"\n\nSYNTHESIS REQUIRED:\n"
            f"Start with: \"Based on what you've told me so far...\" and summarize: {known}.\n"
            f"Strategic insight: {insight or 'Identify the profitability constraint.'}\n"
            f"Tradeoff: {tradeoff}\n"
            f"Business: {label}. Diagnose pricing vs utilization — NOT delivery throughput.\n"
            f"End with at most ONE comparative diagnostic question."
        )
    if dimension == "workforce":
        insight = workforce_strategic_insight(meta, message, history)
        tradeoff = workforce_tradeoff_insight(meta, message, history)
        return (
            f"\n\nSYNTHESIS REQUIRED:\n"
            f"Start with: \"Based on what you've told me so far...\" and summarize: {known}.\n"
            f"Strategic insight: {insight or 'Identify the dominant turnover driver.'}\n"
            f"Tradeoff: {tradeoff}\n"
            f"Business: {label}. Evidence is NOT confirmation — validate ONE driver.\n"
            f"End with at most ONE comparative diagnostic question."
        )
    if dimension == "throughput":
        insight = operations_strategic_insight(meta, message, history)
        tradeoff = ops_tradeoff_insight(meta, message, history)
        return (
            f"\n\nSYNTHESIS REQUIRED:\n"
            f"Start with: \"Based on what you've told me so far...\" and summarize: {known}.\n"
            f"Strategic insight: {insight or 'Identify the dominant operational bottleneck.'}\n"
            f"Tradeoff: {tradeoff}\n"
            f"Business: {label}. Do NOT recommend tools until bottleneck is validated.\n"
            f"End with at most ONE comparative diagnostic question."
        )
    insight = strategic_insight(meta, message, history)
    return (
        f"\n\nSYNTHESIS REQUIRED:\n"
        f"Start with: \"Based on what you've told me so far...\" and summarize: {known}.\n"
        f"State strategic insight before tactics: {insight or 'Identify discovery vs conversion vs retention.'}\n"
        f"Business: {label}. {rag_industry_guidance_line(meta)}\n"
        f"End with at most ONE diagnostic question."
    )


def build_recommendation_block(
    meta: SessionMetadata,
    mode: ConversationMode,
    *,
    user_message: str = "",
    include_boolmind: bool = True,
    history: list[str] | None = None,
) -> str:
    if mode == "diagnose" or should_diagnose(meta, user_message, history):
        return build_diagnosis_block_for_dimension(meta, user_message, history)

    if is_micro_budget(meta, user_message):
        return f"\n\n{micro_budget_advisory()}"

    pushback = pushback_for_website_question(meta, user_message)
    if pushback:
        return f"\n\n{pushback}\n{generic_phased_framework()}"

    if not include_boolmind or should_defer_boolmind_pitch(meta):
        boolmind_line = (
            " Do NOT mention Boolmind or landing pages this turn. "
            "Focus on diagnosis and channel fit."
        )
    else:
        boolmind_line = (
            " Mention Boolmind only when Phase 3 complexity warrants it."
        )

    known = _known_summary(meta)
    label = business_label(meta)

    dimension = detect_problem_dimension(meta, user_message, history)
    header = "ADVISORY DELIVERY REQUIRED" if mode == "advise" else "RECOMMENDATION REQUIRED"

    if dimension == "profitability":
        profit_insight = profitability_strategic_insight(meta, user_message, history)
        tradeoff = profit_tradeoff_insight(meta, user_message, history)
        hypothesis = infer_profit_hypothesis(meta, user_message, history)
        plan = (
            "Phase 1 — Unit economics: validate profit per project/client/hour.\n"
            "Phase 2 — Fix the confirmed constraint (pricing, mix, scope, or utilization).\n"
            "Phase 3 — Systematize: templates, scoping, time tracking — "
            "rag_query(capabilities) for industry-specific tactics."
        )
        return (
            f"\n\n{header} (PROFITABILITY):\n"
            f"Known context: {known}. Business: {label}. Hypothesis: {hypothesis}.\n"
            f"1. Insight: {profit_insight or 'What is working vs not.'}\n"
            f"2. Tradeoff: {tradeoff}\n"
            f"3. Prioritized tactics with WHY — grounded in rag_query(capabilities).\n"
            f"Framework:\n{plan}\n"
            f"{boolmind_line}\n"
            f"End with ONE optional question only if critical info is still missing."
        )

    if dimension == "workforce":
        wf_insight = workforce_strategic_insight(meta, user_message, history)
        tradeoff = workforce_tradeoff_insight(meta, user_message, history)
        hypothesis = infer_workforce_hypothesis(meta, user_message, history)
        plan = (
            "Phase 1 — Validate: confirm the dominant turnover driver with data or exit interviews.\n"
            "Phase 2 — Fix: address the confirmed constraint (pay, workload, paths, management).\n"
            "Phase 3 — Systematize: onboarding, capacity planning — "
            "rag_query(capabilities) for industry-specific retention tactics."
        )
        return (
            f"\n\n{header} (WORKFORCE):\n"
            f"Known context: {known}. Business: {label}. Hypothesis: {hypothesis}.\n"
            f"1. Insight: {wf_insight or 'What is working vs not.'}\n"
            f"2. Tradeoff: {tradeoff}\n"
            f"3. Prioritized tactics with WHY — grounded in rag_query(capabilities).\n"
            f"Framework:\n{plan}\n"
            f"{boolmind_line}\n"
            f"End with ONE optional question only if critical info is still missing."
        )

    if dimension == "throughput":
        ops_insight = operations_strategic_insight(meta, user_message, history)
        tradeoff = ops_tradeoff_insight(meta, user_message, history)
        blocker = infer_ops_bottleneck(meta, user_message, history)
        ops_plan = (
            "Phase 1 — Stabilize: address the confirmed bottleneck first.\n"
            "Phase 2 — Systematize: process visibility, handoffs, and planning.\n"
            "Phase 3 — Technology: only when manual process is maxed — "
            "use rag_query(capabilities) for industry-specific ops tools."
        )
        return (
            f"\n\n{header} (THROUGHPUT):\n"
            f"Known context: {known}. Business: {label}. Bottleneck: {blocker}.\n"
            f"1. Insight: {ops_insight or 'What is working vs not.'}\n"
            f"2. Tradeoff: {tradeoff}\n"
            f"3. Prioritized tactics with WHY — grounded in rag_query(capabilities).\n"
            f"Framework:\n{ops_plan}\n"
            f"{boolmind_line}\n"
            f"End with ONE optional question only if critical info is still missing."
        )

    plan = generic_phased_framework()
    insight = strategic_insight(meta, user_message, history)
    rag_line = rag_industry_guidance_line(meta)

    if mode == "advise":
        return (
            f"\n\nADVISORY DELIVERY REQUIRED:\n"
            f"Known context: {known}. Business: {label}.\n"
            f"1. State insight: {insight or 'What is working vs not.'}\n"
            f"2. {rag_line}\n"
            f"3. Then prioritized tactics with WHY — not generic lists.\n"
            f"Framework:\n{plan}\n"
            f"{boolmind_line}"
        )

    return (
        f"\n\nRECOMMENDATION REQUIRED:\n"
        f"Based on what we know: {known}. Business: {label}.\n"
        f"Insight first: {insight or 'Diagnose blocker before tactics.'}\n"
        f"{rag_line}\n"
        f"Framework:\n{plan}\n"
        f"{boolmind_line}\n"
        f"End with ONE optional question only if critical info is still missing."
    )
