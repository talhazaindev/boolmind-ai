"""Groq chat loop with tool calling and SSE events."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from app.advisor.ab_testing import prompt_variant_suffix
from app.advisor.integrations.groq_llm import get_groq_rotator, _is_rate_limit_error
from app.advisor.integrations.redis_store import RedisSessionStore
from app.advisor.orchestrator.conversation_evaluator import evaluate_turn
from app.advisor.orchestrator.conversation_mode import (
    intent_prompt_suffix,
    mode_prompt_suffix,
    select_conversation_mode,
    update_consecutive_question_turns,
)
from app.advisor.orchestrator.goal_context import detect_primary_goal, goal_lock_prompt_block
from app.advisor.orchestrator.industry_strategy import should_defer_boolmind_pitch
from app.advisor.orchestrator.intent_classifier import (
    classify_intent,
    is_advisory_intent,
    is_concept_explanation,
    is_solution_architecture_mode,
)
from app.advisor.orchestrator.product_context import ProductContext, apply_product_fit
from app.advisor.orchestrator.recommendation import (
    build_recommendation_block,
    build_synthesis_block,
    should_synthesize,
)
from app.advisor.orchestrator.intent_classifier import is_channel_prioritization
from app.advisor.orchestrator.operations_diagnosis import (
    hypothesis_unvalidated as ops_hypothesis_unvalidated,
    infer_ops_bottleneck,
)
from app.advisor.orchestrator.problem_dimension import (
    detect_problem_dimension,
    dimension_lock_prompt_block,
)
from app.advisor.orchestrator.profitability_diagnosis import (
    hypothesis_unvalidated as profit_hypothesis_unvalidated,
    infer_profit_hypothesis,
)
from app.advisor.orchestrator.workforce_diagnosis import (
    hypothesis_unvalidated as workforce_hypothesis_unvalidated,
    infer_workforce_hypothesis,
)
from app.advisor.orchestrator.strategy_diagnosis import (
    build_opening_value_block,
    detect_active_channels,
    infer_growth_blocker,
)
from app.advisor.orchestrator.response_guards import (
    asks_for_contact,
    email_guard_rewrite_instruction,
    has_repeated_content,
    premature_solution_rewrite_instruction,
    repetition_rewrite_instruction,
)
from app.advisor.orchestrator.diagnostic_validation import response_contains_premature_solutions
from app.advisor.orchestrator.session_metadata import (
    persist_discovery_evaluation,
    persist_visitor_metadata,
)
from app.advisor.orchestrator.system_prompt import SystemPromptContext, build_system_prompt
from app.advisor.orchestrator.tool_args import (
    is_groq_validation_error,
    sanitize_tool_arguments,
    strip_groq_validation_errors,
)
from app.advisor.orchestrator.tool_gating import (
    detect_deferred_deliverable_request,
    filter_tool_definitions,
    is_tool_allowed,
)
from app.advisor.analytics.events import message_sent, product_discussed
from app.advisor.mcp import get_tool_router
from app.advisor.mcp.mcp_host import get_mcp_host
from app.advisor.types import PageContext, SessionMetadata

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 5


class AdvisorChatLoop:
    def __init__(self, redis: RedisSessionStore) -> None:
        self._redis = redis
        self._groq = get_groq_rotator()

    def _previous_assistant_text(self, history: list[dict[str, Any]]) -> str:
        for msg in reversed(history):
            if msg.get("role") == "assistant":
                content = msg.get("content") or ""
                if isinstance(content, str):
                    return content
        return ""

    async def _run_synthesis(
        self,
        system_prompt: str,
        messages: list[dict[str, Any]],
    ) -> AsyncIterator[str]:
        api_messages = [{"role": "system", "content": system_prompt}] + messages
        try:
            stream = await self._groq.create_chat_stream(
                messages=api_messages,
                tools=None,
                tool_choice=None,
            )
        except Exception as e:
            if _is_rate_limit_error(e):
                raise
            logger.exception("Groq synthesis failed: %s", e)
            raise

        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta.content and not is_groq_validation_error(delta.content):
                yield delta.content

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
        history = await self._redis.get_history(session_id)
        messages: list[dict[str, Any]] = list(history)
        messages.append({"role": "user", "content": message})

        profile = session_meta or SessionMetadata()
        evaluation = await evaluate_turn(
            session_id=session_id,
            user_message=message,
            history=messages[:-1],
            profile=profile,
            product_context=product_context,
            page_context=page_context,
        )
        updated_meta = await persist_discovery_evaluation(
            self._redis,
            visitor_id,
            session_meta,
            stage=evaluation.stage,
            profile_updates=evaluation.profile_updates,
            missing_fields=evaluation.missing_fields,
            llm_readiness=evaluation.readiness,
            user_sophistication=evaluation.user_sophistication,
        )
        readiness = updated_meta.readiness

        # Gate custom_solutions fit until complexity confirmed
        product_fit_candidate = updated_meta.product_fit
        if (
            product_fit_candidate == "custom_solutions"
            and not updated_meta.custom_complexity_confirmed
            and updated_meta.product_fit_confidence < 0.85
        ):
            product_fit_candidate = None

        product_context = apply_product_fit(product_context, product_fit_candidate)
        product_fit = product_fit_candidate

        user_history_texts = [
            m.get("content", "")
            for m in messages[:-1]
            if m.get("role") == "user" and isinstance(m.get("content"), str)
        ]
        channels = detect_active_channels(updated_meta, message, user_history_texts)
        if channels:
            updated_meta.channels_active = list(
                dict.fromkeys([*updated_meta.channels_active, *channels])
            )
        blocker = infer_growth_blocker(updated_meta, message, user_history_texts)
        if blocker != "unknown":
            updated_meta.growth_blocker = blocker
        ops_bottleneck = infer_ops_bottleneck(updated_meta, message, user_history_texts)
        if ops_bottleneck != "unknown" and not ops_hypothesis_unvalidated(
            updated_meta, message, user_history_texts
        ):
            updated_meta.ops_bottleneck = ops_bottleneck
        profit_hypothesis = infer_profit_hypothesis(updated_meta, message, user_history_texts)
        if profit_hypothesis != "unknown" and not profit_hypothesis_unvalidated(
            updated_meta, message, user_history_texts
        ):
            updated_meta.profit_hypothesis = profit_hypothesis
        workforce_hypothesis = infer_workforce_hypothesis(
            updated_meta, message, user_history_texts
        )
        if workforce_hypothesis != "unknown" and not workforce_hypothesis_unvalidated(
            updated_meta, message, user_history_texts
        ):
            updated_meta.workforce_hypothesis = workforce_hypothesis
        dimension = detect_problem_dimension(updated_meta, message, user_history_texts)
        if dimension != "unknown":
            updated_meta.problem_dimension = dimension

        intent = classify_intent(message)
        deferred_tool = detect_deferred_deliverable_request(message)
        conversation_mode = select_conversation_mode(
            message,
            updated_meta,
            readiness,
            deferred_tool=deferred_tool,
            product_fit=product_fit,
            history_texts=user_history_texts,
        )

        prompt_ctx = SystemPromptContext(
            page_context=page_context,
            session_data=updated_meta,
            product_context=product_context,
            user_language=user_language,
            discovery=evaluation,
            conversation_mode=conversation_mode,
        )
        system_prompt = build_system_prompt(prompt_ctx)
        system_prompt += mode_prompt_suffix(conversation_mode)
        system_prompt += intent_prompt_suffix(intent, conversation_mode)

        primary_goal = detect_primary_goal(
            updated_meta,
            message,
            user_history_texts,
        )
        if primary_goal != "unknown":
            updated_meta.primary_goal = primary_goal  # type: ignore[assignment]
        system_prompt += goal_lock_prompt_block(primary_goal, updated_meta)
        system_prompt += dimension_lock_prompt_block(dimension, updated_meta)

        if is_channel_prioritization(message) and updated_meta.message_count <= 1:
            system_prompt += build_opening_value_block()

        if should_synthesize(updated_meta):
            system_prompt += build_synthesis_block(
                updated_meta, message=message, history=user_history_texts
            )

        if (
            not is_concept_explanation(message)
            and not (is_channel_prioritization(message) and updated_meta.message_count <= 1)
            and (
                conversation_mode in ("diagnose", "advise", "recommend")
                or evaluation.should_recommend
            )
        ):
            system_prompt += build_recommendation_block(
                updated_meta,
                conversation_mode,
                user_message=message,
                include_boolmind=not should_defer_boolmind_pitch(updated_meta),
                history=user_history_texts,
            )

        if deferred_tool and not is_tool_allowed(
            deferred_tool, readiness, product_fit=product_fit
        ):
            if is_advisory_intent(message):
                system_prompt += (
                    f"\n\nDELIVERABLE_DEFERRED: User asked for {deferred_tool}. "
                    f"Do NOT call {deferred_tool} yet. "
                    f"Acknowledge their interest and provide partial advisory value "
                    f"with a Boolmind next step. Do NOT force a discovery question."
                )
            else:
                system_prompt += (
                    f"\n\nDELIVERABLE_DEFERRED: User asked for {deferred_tool}. "
                    f"Do NOT call {deferred_tool}. "
                    f"Write 2-3 sentences: (1) briefly acknowledge their interest, "
                    f"(2) explain you need a little context first to tailor the demo/solution, "
                    f"(3) end with this discovery question: \"{evaluation.next_discovery_question}\" "
                    f"Never stop after acknowledgment alone — the last sentence MUST be a question."
                )
        elif (
            is_solution_architecture_mode(message)
            and readiness.architecture
        ):
            system_prompt += (
                "\n\nACTIVE MODE: SOLUTION_ARCHITECTURE — use generate_architecture_proposal "
                "and structured architecture format."
            )

        system_prompt += prompt_variant_suffix(session_id, product_context.active_product)
        message_sent(session_id, "user", product_context.active_product)
        get_mcp_host()
        router = get_tool_router()
        all_tools = router.list_tools()
        tools = filter_tool_definitions(all_tools, readiness, product_fit=product_fit)

        full_assistant = ""
        tool_messages_for_history: list[dict[str, Any]] = []
        stage = updated_meta.stage_reached
        active_product = product_context.active_product

        for _round in range(MAX_TOOL_ROUNDS):
            api_messages = [{"role": "system", "content": system_prompt}] + messages
            tool_calls_acc: dict[int, dict[str, Any]] = {}
            round_text = ""

            try:
                stream = await self._groq.create_chat_stream(
                    messages=api_messages,
                    tools=tools,
                    tool_choice="auto",
                )
            except Exception as e:
                if _is_rate_limit_error(e):
                    logger.warning("Groq rate limit: all keys exhausted")
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
                yield {
                    "type": "error",
                    "code": "INTERNAL",
                    "message": "Something went wrong. Please try again in a moment.",
                }
                return

            async for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta.content:
                    if is_groq_validation_error(delta.content):
                        logger.warning("Groq tool validation error suppressed: %s", delta.content[:200])
                        continue
                    round_text += delta.content
                    full_assistant += delta.content
                    yield {"type": "delta", "content": delta.content}
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in tool_calls_acc:
                            tool_calls_acc[idx] = {
                                "id": tc.id or "",
                                "type": "function",
                                "function": {"name": "", "arguments": ""},
                            }
                        if tc.id:
                            tool_calls_acc[idx]["id"] = tc.id
                        if tc.function:
                            if tc.function.name:
                                tool_calls_acc[idx]["function"]["name"] = tc.function.name
                            if tc.function.arguments:
                                tool_calls_acc[idx]["function"]["arguments"] += tc.function.arguments

            if not tool_calls_acc:
                break

            assistant_msg: dict[str, Any] = {
                "role": "assistant",
                "content": round_text or None,
                "tool_calls": [
                    {
                        "id": tool_calls_acc[i]["id"],
                        "type": "function",
                        "function": tool_calls_acc[i]["function"],
                    }
                    for i in sorted(tool_calls_acc.keys())
                ],
            }
            messages.append(assistant_msg)
            tool_messages_for_history.append(assistant_msg)

            for i in sorted(tool_calls_acc.keys()):
                tc = tool_calls_acc[i]
                name = tc["function"]["name"]
                try:
                    args = json.loads(tc["function"]["arguments"] or "{}")
                except json.JSONDecodeError:
                    args = {}
                args = sanitize_tool_arguments(name, args)
                yield {"type": "tool_start", "tool": name, "input": args}
                result = await router.call_tool(
                    name,
                    args,
                    product_context,
                    session_id,
                    visitor_id,
                    readiness=readiness,
                    product_fit=product_fit,
                )
                content = router.result_content(result)
                yield {
                    "type": "tool_result",
                    "tool": name,
                    "result": result.data if result.success else {"fallback": content},
                }
                tool_msg = {
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": content,
                }
                messages.append(tool_msg)
                tool_messages_for_history.append(tool_msg)

        full_assistant = strip_groq_validation_errors(full_assistant)

        needs_synthesis = not full_assistant.strip() or (
            deferred_tool
            and not is_tool_allowed(deferred_tool, readiness, product_fit=product_fit)
            and not is_advisory_intent(message)
            and "?" not in full_assistant
        )
        if needs_synthesis:
            try:
                async for delta in self._run_synthesis(system_prompt, messages):
                    full_assistant += delta
                    yield {"type": "delta", "content": delta}
            except Exception as e:
                if _is_rate_limit_error(e):
                    yield {
                        "type": "error",
                        "code": "RATE_LIMIT",
                        "message": (
                            "We're handling high demand right now. "
                            "Please wait a moment and try again."
                        ),
                    }
                    return
                yield {
                    "type": "error",
                    "code": "INTERNAL",
                    "message": "Something went wrong. Please try again in a moment.",
                }
                return

        full_assistant = strip_groq_validation_errors(full_assistant)

        prev_assistant = self._previous_assistant_text(history)
        rewrite_prompt = system_prompt
        needs_rewrite = False
        if not readiness.lead_capture and asks_for_contact(full_assistant):
            rewrite_prompt += email_guard_rewrite_instruction()
            needs_rewrite = True
        elif has_repeated_content(full_assistant, prev_assistant):
            rewrite_prompt += repetition_rewrite_instruction()
            needs_rewrite = True
        elif conversation_mode == "diagnose" and response_contains_premature_solutions(
            full_assistant
        ):
            rewrite_prompt += premature_solution_rewrite_instruction()
            needs_rewrite = True

        if needs_rewrite:
            rewrite_messages = messages + [
                {"role": "assistant", "content": full_assistant},
            ]
            rewritten = ""
            try:
                async for delta in self._run_synthesis(rewrite_prompt, rewrite_messages):
                    rewritten += delta
                    yield {"type": "delta", "content": delta}
            except Exception:
                pass
            else:
                if rewritten.strip():
                    full_assistant = strip_groq_validation_errors(rewritten)

        consecutive = update_consecutive_question_turns(
            updated_meta, full_assistant, conversation_mode
        )
        updated_meta.consecutive_question_turns = consecutive
        if visitor_id:
            await self._redis.save_visitor_metadata(visitor_id, updated_meta)

        await self._redis.append_history(
            session_id,
            message,
            full_assistant,
            tool_messages_for_history if tool_messages_for_history else None,
        )

        await persist_visitor_metadata(
            self._redis,
            visitor_id,
            message,
            product_context,
            updated_meta,
        )

        discussed = list(product_context.products_discussed)
        if product_context.active_product and product_context.active_product not in discussed:
            discussed.append(product_context.active_product)
            product_discussed(session_id, product_context.active_product)
        message_sent(session_id, "assistant", product_context.active_product)

        yield {
            "type": "done",
            "sessionId": session_id,
            "stage": stage,
            "activeProduct": active_product,
            "productsDiscussed": discussed,
            "missingFields": updated_meta.missing_fields,
            "readiness": updated_meta.readiness.model_dump(),
            "conversationMode": conversation_mode,
        }
