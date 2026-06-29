"""Groq chat loop with execution engine — pre-flight tools, single LLM call."""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from typing import Any

from app.advisor.ab_testing import prompt_variant_suffix
from app.advisor.analytics.events import message_sent, product_discussed
from app.advisor.integrations.groq_llm import _is_rate_limit_error, get_chat_llm_client
from app.advisor.integrations.redis_store import RedisSessionStore
from app.advisor.mcp import get_tool_router
from app.advisor.mcp.mcp_host import get_mcp_host
from app.advisor.monitoring import events as ev
from app.advisor.monitoring.latency import TurnLatency
from app.advisor.monitoring.telemetry import emit
from app.advisor.orchestrator.conversation_mode import update_consecutive_question_turns
from app.advisor.orchestrator.evaluation_worker import enqueue_evaluation
from app.advisor.orchestrator.product_context import ProductContext, apply_product_fit
from app.advisor.orchestrator.prompt_composition import (
    assemble_execution_prompt,
    build_outcome_framing_block,
)
from app.advisor.pipeline.question_ledger import record_asked_question
from app.advisor.pipeline.question_tracker import should_suppress_diagnostic_question
from app.advisor.pipeline.turn_pipeline import TurnPipeline
from app.advisor.orchestrator.public_output import PublicOutputFilter, sanitize_public_output
from app.advisor.orchestrator.context_extractor import extract_context_llm_async
from app.advisor.orchestrator.question_composer import build_narrator_hints
from app.advisor.orchestrator.fact_grounding import sanitize_ungrounded_assertions
from app.advisor.orchestrator.question_append import (
    finalize_response,
    question_already_in_text,
    strip_redundant_questions,
)
from app.advisor.pipeline.conversation_planner import ConversationPlanner
from app.advisor.pipeline.diagnostic_protocol import DiagnosticDepth
from app.advisor.orchestrator.rag_degradation import call_with_rag_degradation, narrow_rag_namespace
from app.advisor.orchestrator.response_guards import (
    asks_for_contact,
    has_repeated_content,
)
from app.advisor.orchestrator.response_quality import assess_response_quality
from app.advisor.orchestrator.session_metadata import persist_visitor_metadata
from app.advisor.orchestrator.tool_args import is_groq_validation_error, strip_groq_validation_errors
from app.advisor.orchestrator.tool_context import build_deliverable_block, build_grounding_block
from app.advisor.tools.case_retrieval import retrieve_case_evidence
from app.advisor.constants import RAG_TOOLS, SELF_GROUNDING_TOOLS
from app.advisor.types import PageContext, SessionMetadata, TurnContext

logger = logging.getLogger(__name__)

_FALLBACK_EMPTY = (
    "I want to make sure I give you a useful answer — could you rephrase that briefly?"
)


class AdvisorChatLoop:
    def __init__(self, redis: RedisSessionStore) -> None:
        self._redis = redis
        self._llm = get_chat_llm_client()

    def _previous_assistant_text(self, history: list[dict[str, Any]]) -> str:
        for msg in reversed(history):
            if msg.get("role") == "assistant":
                content = msg.get("content") or ""
                if isinstance(content, str):
                    return content
        return ""

    def _emit_public_delta(
        self,
        output_filter: PublicOutputFilter,
        raw: str,
    ) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        cleaned = output_filter.feed(raw)
        if cleaned:
            events.append({"type": "delta", "content": cleaned})
        return events

    async def stream_chat(
        self,
        session_id: str,
        message: str,
        page_context: PageContext,
        visitor_id: str | None,
        user_language: str,
        product_context: ProductContext,
        session_meta: SessionMetadata | None,
    ) -> AsyncIterator[dict[str, Any]]:
        turn_latency = TurnLatency()
        turn_latency.mark("turn_start")
        history = await self._redis.get_history(session_id)
        messages: list[dict[str, Any]] = list(history)
        messages.append({"role": "user", "content": message})

        profile = session_meta or SessionMetadata()
        frozen_meta = profile.model_copy(deep=True)
        user_history_texts = [
            m.get("content", "")
            for m in messages[:-1]
            if m.get("role") == "user" and isinstance(m.get("content"), str)
        ]

        # --- Critical path: optional LLM context enrich + deterministic pipeline ---
        llm_context = await extract_context_llm_async(message, user_history_texts)
        planner = ConversationPlanner()
        depth = DiagnosticDepth.from_session(frozen_meta)
        seed_turn_plan = planner.plan(
            session_metadata=frozen_meta,
            depth=depth,
            matched_archetypes=[],
            message_count=frozen_meta.message_count,
        )
        pipeline_result = TurnPipeline.run(
            frozen_meta,
            message,
            user_history_texts,
            active_product=product_context.active_product,
            llm_context=llm_context,
            seed_turn_plan=seed_turn_plan,
        )
        extracted_meta = pipeline_result.extracted_meta
        snapshot = pipeline_result.snapshot
        fit_decision = pipeline_result.fit_decision
        business_memory = pipeline_result.business_memory
        readiness = pipeline_result.readiness
        router_output = pipeline_result.router_output
        decision_trace = pipeline_result.decision_trace
        context_graph = pipeline_result.context_graph
        internal_reasoning = pipeline_result.internal_reasoning
        turn_value = pipeline_result.turn_value
        legacy_fit = pipeline_result.legacy_fit
        turn_plan = pipeline_result.turn_plan
        matched_archetypes = pipeline_result.matched_archetypes
        prev_diagnostic_depth = frozen_meta.diagnostic_depth

        product_context = apply_product_fit(product_context, legacy_fit)

        case_evidence: list[dict[str, str]] = []
        if turn_plan and turn_plan.allow_case_reference and matched_archetypes:
            vertical = extracted_meta.active_business_vertical or extracted_meta.industry
            case_evidence = await retrieve_case_evidence(matched_archetypes, vertical=vertical)

        pipeline_result.case_evidence_retrieved = bool(case_evidence)
        outcome_framing_block = build_outcome_framing_block(
            matched_archetypes or None,
            turn_plan,
        )
        pipeline_result.outcome_framing_applied = bool(outcome_framing_block.strip())

        if pipeline_result.matched_archetype_ids:
            await emit(
                ev.ARCHETYPE_MATCHED,
                session_id,
                visitor_id=visitor_id,
                metadata={
                    "archetypes": pipeline_result.matched_archetype_ids,
                    "similarity_scores": pipeline_result.archetype_similarity_scores,
                    "vertical": extracted_meta.active_business_vertical
                    or extracted_meta.industry,
                },
            )

        if pipeline_result.diagnostic_depth != prev_diagnostic_depth:
            await emit(
                ev.DIAGNOSTIC_DEPTH_UPDATED,
                session_id,
                visitor_id=visitor_id,
                metadata={
                    "previous_depth": prev_diagnostic_depth,
                    "new_depth": pipeline_result.diagnostic_depth,
                    "phase": pipeline_result.diagnostic_phase,
                    "delta_source": "turn_pipeline",
                },
            )

        if pipeline_result.hypothesis_question_used:
            await emit(
                ev.HYPOTHESIS_QUESTION_SELECTED,
                session_id,
                visitor_id=visitor_id,
                metadata={
                    "question_key": decision_trace.required_question_key,
                    "diagnostic_depth": pipeline_result.diagnostic_depth,
                    "matched_archetypes": pipeline_result.matched_archetype_ids,
                },
            )

        solution_gate_gates = [
            g
            for g in router_output.decision_record.confidence_gates_applied
            if "<60->" in g
        ]
        if solution_gate_gates:
            blocked_mode = "SALES"
            for gate in solution_gate_gates:
                tail = gate.split("<60->", 1)[-1]
                if "->" in tail:
                    blocked_mode = tail.split("->", 1)[0]
                    break
            await emit(
                ev.SOLUTION_GATE_TRIGGERED,
                session_id,
                visitor_id=visitor_id,
                metadata={
                    "diagnostic_depth": pipeline_result.diagnostic_depth,
                    "blocked_mode": blocked_mode,
                    "gates": solution_gate_gates,
                },
            )

        grounding_block: str | None = None
        deliverable_block: str | None = None
        rag_status = "skipped"
        tool_router = get_tool_router()
        get_mcp_host()

        plan = router_output.tool_plan
        if plan:
            args = dict(plan.arguments)
            if plan.tool_name == "rag_query" and "namespace" in args:
                args["namespace"] = narrow_rag_namespace(
                    str(args["namespace"]),
                    fit_decision,
                    product_context.active_product,
                )
            yield {"type": "tool_start", "tool": plan.tool_name, "input": args}
            turn_latency.mark("tools_batch_start")

            async def _call() -> Any:
                return await tool_router.call_tool(
                    plan.tool_name,
                    args,
                    product_context,
                    session_id,
                    visitor_id,
                    readiness=readiness,
                    product_fit=legacy_fit,
                )

            result, rag_status = await call_with_rag_degradation(plan.tool_name, _call)
            turn_latency.mark("tools_batch_end")
            content = tool_router.result_content(result)
            yield {
                "type": "tool_result",
                "tool": plan.tool_name,
                "result": result.data if result.success else {"fallback": content},
                "outcome": result.outcome,
            }
            if plan.tool_name in RAG_TOOLS and plan.tool_name not in SELF_GROUNDING_TOOLS:
                block, grounding_block = build_grounding_block(result, plan.tool_name)
                if (
                    router_output.mode in ("DISCOVERY", "DIAGNOSE")
                    and fit_decision.solution_category == "custom_solutions"
                    and grounding_block
                ):
                    for name in (
                        "Legal Data Fusion",
                        "Retify",
                        "ECG Document Intelligence",
                    ):
                        grounding_block = grounding_block.replace(name, "custom solutions")
            else:
                _, deliverable_block = build_deliverable_block(result, plan.tool_name)

        acknowledgment_hints = (
            build_narrator_hints(
                context_graph,
                internal_reasoning,
                snapshot,
                extracted_meta,
                router_output.mode,
            )
            if context_graph and internal_reasoning
            else []
        )

        turn_value_block = turn_value.prompt_block if turn_value else None
        turn_visual = (
            turn_value.as_is_visual.model_dump()
            if turn_value and turn_value.as_is_visual
            else None
        )

        turn_ctx = TurnContext(
            session_id=session_id,
            message=message,
            history_texts=tuple(user_history_texts),
            frozen_meta=frozen_meta,
            extracted_meta=extracted_meta,
            snapshot=snapshot,
            business_memory=business_memory,
            product_fit_decision=fit_decision,
            router_output=router_output,
            grounding_block=grounding_block,
            deliverable_block=deliverable_block,
            rag_status=rag_status,
            context_graph=context_graph,
            internal_reasoning=internal_reasoning,
            acknowledgment_hints=acknowledgment_hints,
            next_question=snapshot.required_question,
            turn_value_block=turn_value_block,
            turn_visual=turn_visual,
            turn_plan=turn_plan,
            matched_archetypes=matched_archetypes,
            case_evidence=case_evidence,
        )

        system_prompt = assemble_execution_prompt(turn_ctx)
        system_prompt += prompt_variant_suffix(session_id, product_context.active_product)
        message_sent(session_id, "user", product_context.active_product)

        if pipeline_result.outcome_framing_applied:
            await emit(
                ev.OUTCOME_FRAMING_APPLIED,
                session_id,
                visitor_id=visitor_id,
                metadata={
                    "matched_archetypes": pipeline_result.matched_archetype_ids,
                    "allow_solution_hint": bool(turn_plan and turn_plan.allow_solution_hint),
                },
            )

        record = router_output.decision_record
        record.memory_lines_used = [line.key for line in business_memory.lines]
        await emit(
            ev.ROUTER_DECISION,
            session_id,
            visitor_id=visitor_id,
            metadata=record.model_dump(),
        )
        if decision_trace.conflict_hold:
            await emit(
                ev.CONFLICT_DETECTED,
                session_id,
                visitor_id=visitor_id,
                metadata=decision_trace.model_dump(),
            )
        await emit(
            ev.MODE_SELECTED,
            session_id,
            visitor_id=visitor_id,
            metadata={
                "execution_mode": router_output.mode,
                "mode_reasons": decision_trace.mode_reasons,
                "pipeline_stage": decision_trace.pipeline_stage,
            },
        )

        full_body = ""
        output_filter = PublicOutputFilter()
        first_token_marked = False
        turn_latency.mark("llm_r0_start")

        try:
            stream = await self._llm.create_chat_stream(
                messages=[{"role": "system", "content": system_prompt}] + messages,
                tools=None,
                tool_choice="none",
            )
        except Exception as e:
            if _is_rate_limit_error(e):
                await emit(ev.LLM_RATE_LIMITED, session_id, visitor_id=visitor_id)
                yield {
                    "type": "error",
                    "code": "RATE_LIMIT",
                    "message": (
                        "We're handling high demand right now. "
                        "Please wait a moment and try again."
                    ),
                }
                return
            logger.exception("Groq chat failed: %s", e)
            await emit(
                ev.TOOL_FAILED,
                session_id,
                visitor_id=visitor_id,
                metadata={"error_class": type(e).__name__, "stage": "llm_stream"},
                exception=e,
            )
            yield {
                "type": "error",
                "code": "INTERNAL",
                "message": "Something went wrong. Please try again in a moment.",
            }
            return

        streamed_public = ""
        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta.content and not is_groq_validation_error(delta.content):
                full_body += delta.content
                if not first_token_marked:
                    turn_latency.mark("first_token")
                    first_token_marked = True
                for event in self._emit_public_delta(output_filter, delta.content):
                    if event.get("type") == "delta" and event.get("content"):
                        streamed_public += str(event["content"])
                    yield event

        turn_latency.mark("llm_r0_end")
        trailing = output_filter.flush()
        if trailing:
            full_body += trailing
            yield {"type": "delta", "content": trailing}

        if internal_reasoning:
            await emit(
                ev.INTERNAL_REASONING,
                session_id,
                visitor_id=visitor_id,
                metadata=internal_reasoning.model_dump(),
            )

        full_body = strip_groq_validation_errors(full_body)
        full_body = sanitize_public_output(full_body)
        full_body = sanitize_ungrounded_assertions(
            full_body,
            router_output.mode,
            snapshot,
            extracted_meta,
            context_graph,
        )
        full_body = strip_redundant_questions(
            full_body,
            snapshot,
            extracted_meta,
            appended_question=snapshot.required_question,
            graph=context_graph,
            message=message,
            history=user_history_texts,
        )

        if not full_body.strip():
            full_body = _FALLBACK_EMPTY
            yield {"type": "delta", "content": full_body}

        quality = assess_response_quality(
            full_body, router_output.mode, snapshot
        )
        await emit(
            ev.RESPONSE_QUALITY,
            session_id,
            visitor_id=visitor_id,
            metadata=quality.model_dump(),
        )

        updated_meta = extracted_meta.model_copy(deep=True)
        if not quality.passed:
            updated_meta.quality_hint_next_turn = True
            updated_meta.quality_failure_count = (updated_meta.quality_failure_count or 0) + 1
        else:
            updated_meta.quality_hint_next_turn = False

        required_q = snapshot.required_question
        if should_suppress_diagnostic_question(
            router_output.mode,
            has_deliverable=bool(deliverable_block),
        ):
            required_q = None

        full_assistant = finalize_response(full_body, required_q)
        if turn_value and turn_value.as_is_visual:
            yield {
                "type": "visual",
                "visualType": turn_value.as_is_visual.visual_type,
                "title": turn_value.as_is_visual.title,
                "mermaid": turn_value.as_is_visual.mermaid,
                "caption": turn_value.as_is_visual.caption,
                "isDraft": turn_value.as_is_visual.is_draft,
            }
        if required_q:
            updated_meta = record_asked_question(updated_meta, required_q)
        if (
            required_q
            and full_assistant != full_body
            and not question_already_in_text(streamed_public, required_q)
        ):
            appended = full_assistant[len(full_body.rstrip()) :].strip()
            if appended:
                yield {"type": "delta", "content": "\n\n" + appended}

        prev_assistant = self._previous_assistant_text(history)
        if has_repeated_content(full_assistant, prev_assistant):
            full_assistant = sanitize_public_output(
                full_assistant + " Let me add a different angle for you."
            )

        if not readiness.lead_capture and asks_for_contact(full_assistant):
            full_assistant = sanitize_public_output(
                full_assistant.replace("email", "next step").replace("Email", "Next step")
            )

        consecutive = update_consecutive_question_turns(
            updated_meta, full_assistant, router_output.internal_mode
        )
        if required_q:
            consecutive = max(consecutive, (updated_meta.consecutive_question_turns or 0) + 1)
        updated_meta.consecutive_question_turns = consecutive

        if visitor_id:
            await self._redis.save_visitor_metadata(visitor_id, updated_meta)

        await self._redis.append_history(session_id, message, full_assistant, None)

        await persist_visitor_metadata(
            self._redis,
            visitor_id,
            message,
            product_context,
            updated_meta,
        )

        enqueue_evaluation(
            self._redis,
            session_id,
            visitor_id,
            message,
            messages[:-1],
            updated_meta,
            product_context,
            page_context,
        )
        await emit(ev.EVAL_QUEUED, session_id, visitor_id=visitor_id)

        discussed = list(product_context.products_discussed)
        if product_context.active_product and product_context.active_product not in discussed:
            discussed.append(product_context.active_product)
            product_discussed(session_id, product_context.active_product)
        message_sent(session_id, "assistant", product_context.active_product)

        turn_latency.mark("turn_end")
        turn_summary = turn_latency.summary()
        logger.info(
            "[advisor.latency] session=%s total_ms=%.1f execution_mode=%s rag=%s",
            session_id,
            turn_summary["total_ms"],
            router_output.mode,
            rag_status,
        )
        await emit(
            ev.TURN_COMPLETED,
            session_id,
            visitor_id=visitor_id,
            product_id=product_context.active_product,
            metadata={
                **turn_summary,
                "execution_mode": router_output.mode,
                "rag_status": rag_status,
                "quality_score": quality.score,
            },
        )

        done_event: dict[str, Any] = {
            "type": "done",
            "sessionId": session_id,
            "stage": updated_meta.stage_reached,
            "activeProduct": product_context.active_product,
            "productsDiscussed": discussed,
            "missingFields": updated_meta.missing_fields,
            "readiness": updated_meta.readiness.model_dump(),
            "conversationMode": router_output.internal_mode,
            "executionMode": router_output.mode,
            "routingConfidence": router_output.routing_confidence,
            "toolConfidence": router_output.tool_confidence,
            "ragStatus": rag_status,
            "qualityScore": quality.score,
            "qualityPassed": quality.passed,
            "evalQueued": True,
            "resolutionTrace": router_output.resolution.trace,
            "decisionTrace": decision_trace.model_dump(),
            "diagnosticDepth": pipeline_result.diagnostic_depth,
            "diagnosticPhase": pipeline_result.diagnostic_phase,
            "matchedArchetypes": pipeline_result.matched_archetype_ids,
            "turnPlanPriority": pipeline_result.turn_plan_priority,
            "hypothesisQuestionUsed": pipeline_result.hypothesis_question_used,
        }
        if os.getenv("ADVISOR_DEBUG_ROUTER", "").lower() in ("1", "true", "yes"):
            done_event["routerDecision"] = record.model_dump()
        yield done_event
