"""Orchestrates L1–L8 deterministic turn processing."""

from __future__ import annotations

from app.advisor.orchestrator.business_memory import (
    update_business_memory,
)
from app.advisor.orchestrator.context_graph import (
    build_context_graph,
    persist_graph,
)
from app.advisor.orchestrator.question_composer import (
    compose_contextual_question,
    update_hypotheses_from_graph,
)
from app.advisor.pipeline.question_gate import validate_follow_up_question
from app.advisor.orchestrator.execution_router import derive_router_output
from app.advisor.orchestrator.hypothesis_state import update_hypothesis_snapshot
from app.advisor.orchestrator.product_fit_mapper import map_product_fit
from app.advisor.orchestrator.tool_gating import detect_deferred_deliverable_request
from app.advisor.pipeline.conflict_engine import detect_conflicts
from app.advisor.pipeline.fact_extractor import extract_message_facts
from app.advisor.pipeline.question_selector import (
    question_key_for_trace,
    resolve_required_question,
)
from app.advisor.pipeline.question_tracker import (
    apply_answered_questions,
    should_suppress_diagnostic_question,
)
from app.advisor.pipeline.readiness import assess_readiness
from app.advisor.pipeline.stage_engine import architecture_fast_path_qualify, promote_funnel_stage
from app.advisor.pipeline.state_mutator import mutate_session_metadata
from app.advisor.pipeline.thread_tracker import update_active_thread
from app.advisor.pipeline.conversation_planner import ConversationPlanner, TurnPlan
from app.advisor.pipeline.diagnostic_protocol import DiagnosticDepth
from app.advisor.pipeline.types import TurnDecisionTrace, TurnPipelineResult
from app.advisor.types import SessionMetadata


class TurnPipeline:
    """Critical-path deterministic execution pipeline."""

    @staticmethod
    def run(
        frozen_meta: SessionMetadata,
        message: str,
        user_history_texts: list[str],
        *,
        active_product: str | None = None,
        llm_context: dict | None = None,
        bi_snippets: list[str] | None = None,
        seed_turn_plan: TurnPlan | None = None,
    ) -> TurnPipelineResult:
        del seed_turn_plan  # authoritative passes below supersede loop pre-stub

        planner = ConversationPlanner()
        depth = DiagnosticDepth.from_session(frozen_meta)
        turn_plan = planner.plan(
            session_metadata=frozen_meta,
            depth=depth,
            matched_archetypes=[],
            message_count=frozen_meta.message_count,
        )

        # L2 — read-only facts
        facts = extract_message_facts(message, user_history_texts)

        # L3 — conflict on frozen state
        conflict_report = detect_conflicts(
            frozen_meta,
            frozen_meta.business_memory_lines,
            facts,
            message,
        )

        # L4 — state mutation (vertical guarded on conflict)
        extracted_meta = mutate_session_metadata(
            frozen_meta, message, user_history_texts, conflict_report
        )

        fit_decision = map_product_fit(extracted_meta, message, user_history_texts)
        extracted_meta.catalog_product_fit = fit_decision.catalog_product_fit
        extracted_meta.solution_category = fit_decision.solution_category
        extracted_meta.catalog_fit_reasons = fit_decision.catalog_reasons
        extracted_meta.solution_reasons = fit_decision.solution_reasons
        legacy_fit = fit_decision.catalog_product_fit or (
            fit_decision.solution_category
            if fit_decision.solution_category not in (None, "undecided")
            else None
        )
        if legacy_fit:
            extracted_meta.product_fit = legacy_fit
            extracted_meta.product_fit_confidence = fit_decision.confidence

        open_keys, answered_keys, skipped_keys = apply_answered_questions(
            extracted_meta, message, user_history_texts
        )
        extracted_meta.open_question_keys = open_keys
        extracted_meta.answered_question_keys = answered_keys
        extracted_meta.skipped_question_keys = skipped_keys

        # Hypothesis snapshot (single pass, post-conflict)
        snapshot = update_hypothesis_snapshot(
            extracted_meta,
            message,
            user_history_texts,
            is_conflicted=conflict_report.is_conflicted,
            conflict_detail=conflict_report.clarification_question,
        )
        extracted_meta.evidence_score_peak = snapshot.overall_confidence

        memory_lines, business_memory = update_business_memory(
            extracted_meta.business_memory_lines,
            extracted_meta,
            snapshot,
            fit_decision,
            message,
            extracted_meta.message_count,
        )
        extracted_meta.business_memory_lines = memory_lines

        # Intelligence layer — context graph, hypotheses, composed question
        context_graph = build_context_graph(
            extracted_meta,
            message,
            user_history_texts,
            snapshot,
            llm_data=llm_context,
        )
        context_graph = update_active_thread(extracted_meta, message, context_graph)
        extracted_meta.hypotheses = update_hypotheses_from_graph(
            extracted_meta, context_graph, snapshot, message=message
        )

        from app.advisor.knowledge.ontology_loader import match_archetypes_scored_sync
        from app.advisor.knowledge.ontology_schema import BusinessArchetype
        from app.advisor.pipeline.business_systems_engine import run_business_systems_reasoning

        employee_count = facts.proposed_employee_count
        if employee_count is None:
            for line in extracted_meta.business_memory_lines:
                if line.key == "employee_count":
                    try:
                        employee_count = int(str(line.value).replace(",", ""))
                    except ValueError:
                        pass
                    break

        vertical = extracted_meta.active_business_vertical or extracted_meta.industry

        matched_scored: list[tuple[float, BusinessArchetype]] = []
        try:
            matched_scored = match_archetypes_scored_sync(
                current_message=message,
                recent_user_turns=user_history_texts[-3:],
                vertical=vertical,
                employee_count=employee_count,
            )
        except Exception:
            matched_scored = []

        matched_archetypes = [arch for _, arch in matched_scored]

        turn_plan = planner.plan(
            session_metadata=frozen_meta,
            depth=depth,
            matched_archetypes=matched_archetypes,
            message_count=frozen_meta.message_count,
        )

        composed_q, internal_reasoning = compose_contextual_question(
            context_graph,
            snapshot,
            extracted_meta,
            message=message,
            history=user_history_texts,
            matched_scored=matched_scored,
        )
        if composed_q:
            snapshot = snapshot.model_copy(update={"required_question": composed_q})

        bss = run_business_systems_reasoning(
            extracted_meta,
            snapshot,
            message=message,
            history=user_history_texts,
            graph=context_graph,
            matched_archetypes=matched_archetypes,
        )
        extracted_meta.business_systems_state = bss.model_dump()
        extracted_meta.reasoning_stage = bss.reasoning_stage
        extracted_meta.executive_narrative = bss.narrative_state.model_dump()
        if bss.economic_drivers:
            extracted_meta.primary_economic_driver = bss.economic_drivers[0]

        from app.advisor.pipeline.diagnostic_protocol import (
            bss_diagnostic_signals,
            issue_tree_from_session,
            issue_tree_to_dict,
            select_question_from_issue_tree,
            update_issue_tree,
        )

        depth = DiagnosticDepth(score=frozen_meta.diagnostic_depth)
        signals = bss_diagnostic_signals(bss, extracted_meta)

        if signals.symptom_identified:
            depth.add_symptom_identified()
        vertical_new = bool(
            (extracted_meta.active_business_vertical or extracted_meta.industry)
            and not (frozen_meta.active_business_vertical or frozen_meta.industry)
        )
        if vertical_new:
            depth.add_vertical_confirmed()
        scale_new = bool(
            (facts.proposed_employee_count or extracted_meta.data_context)
            and not (
                frozen_meta.data_context
                or any(
                    line.key in ("employee_count", "scale")
                    for line in frozen_meta.business_memory_lines
                )
            )
        )
        if scale_new:
            depth.add_scale_confirmed()
        if signals.root_cause_hypothesised:
            depth.add_root_cause_hypothesised()
        if signals.root_cause_confirmed:
            depth.add_root_cause_confirmed()
        if signals.impact_quantified:
            depth.add_impact_quantified()
        if signals.constraint_discovered:
            depth.add_constraint_discovered()
        _timeline_kw = ("before", "by", "deadline", "urgent", "asap", "next month", "quarter")
        if any(kw in message.lower() for kw in _timeline_kw):
            depth.add_timeline_signal()

        tree = update_issue_tree(
            issue_tree_from_session(extracted_meta),
            bss,
            extracted_meta,
            message,
            matched_archetype_id=matched_archetypes[0].id if matched_archetypes else None,
        )
        extracted_meta.diagnostic_depth = depth.score
        extracted_meta.diagnostic_phase = depth.phase.value
        tree.current_phase = depth.phase
        extracted_meta.issue_tree = issue_tree_to_dict(tree)

        issue_q = select_question_from_issue_tree(tree)
        if issue_q:
            validated_issue_q, _violations = validate_follow_up_question(
                issue_q,
                snapshot,
                extracted_meta,
                graph=context_graph,
                message=message,
                history=user_history_texts,
            )
            if validated_issue_q:
                snapshot = snapshot.model_copy(update={"required_question": validated_issue_q})

        extracted_meta = persist_graph(extracted_meta, context_graph)

        if snapshot.required_question:
            validated_q, violations = validate_follow_up_question(
                snapshot.required_question,
                snapshot,
                extracted_meta,
                graph=context_graph,
                message=message,
                history=user_history_texts,
            )
            snapshot = snapshot.model_copy(update={"required_question": validated_q})
            if violations and validated_q is None:
                snapshot = resolve_required_question(
                    snapshot, extracted_meta, violations=violations
                )

        if snapshot.active_business_vertical and not conflict_report.blocks_vertical_update:
            extracted_meta.active_business_vertical = snapshot.active_business_vertical
        extracted_meta.confirmed_bottleneck_count = snapshot.confirmed_bottleneck_count

        # L6 — funnel stage promotion (T0)
        deferred = detect_deferred_deliverable_request(message)
        extracted_meta.stage_reached = promote_funnel_stage(extracted_meta, snapshot)
        if deferred == "generate_architecture_proposal":
            extracted_meta.stage_reached = architecture_fast_path_qualify(
                extracted_meta,
                snapshot,
                deferred_architecture=True,
            )

        # L5 — readiness
        readiness = assess_readiness(extracted_meta)
        extracted_meta.readiness = readiness

        # L7 + L8 — mode and tool via execution router (refactored)
        router_output = derive_router_output(
            extracted_meta,
            snapshot,
            message,
            readiness,
            product_fit=fit_decision,
            active_product=active_product,
            history_texts=user_history_texts,
            turn_plan=turn_plan,
        )

        if should_suppress_diagnostic_question(
            router_output.mode,
            has_deliverable=deferred == "generate_architecture_proposal",
        ):
            snapshot = snapshot.model_copy(update={"required_question": None})

        record = router_output.decision_record
        trace = TurnDecisionTrace(
            pipeline_stage=snapshot.conversation_stage,
            funnel_stage=extracted_meta.stage_reached,
            execution_mode=router_output.mode,
            mode_reasons=list(record.mode_reasons),
            conflict_hold=conflict_report.conflict_hold,
            evidence_score=snapshot.overall_confidence,
            routing_confidence_advisory=router_output.routing_confidence,
            readiness=readiness,
            tool_selected=record.tool_selected,
            tool_reason=record.tool_reason,
            gates_applied=list(record.confidence_gates_applied),
            gates_rejected=list(record.resolution_trace),
            memory_lines_used=[line.key for line in business_memory.lines],
            required_question_key=question_key_for_trace(snapshot.required_question),
            eval_tier="T0_deterministic",
            active_thread=context_graph.active_thread,
            universal_stage=context_graph.universal_stage,
            top_hypothesis_ids=internal_reasoning.top_hypothesis_ids,
        )

        if snapshot.required_question:
            from app.advisor.pipeline.question_ledger import record_asked_question

            extracted_meta = record_asked_question(extracted_meta, snapshot.required_question)

        from app.advisor.pipeline.discovery_engine import run_discovery
        from app.advisor.pipeline.turn_value import (
            build_turn_value,
            detect_draft_confirmation,
        )

        if detect_draft_confirmation(message):
            extracted_meta.draft_working_picture_confirmed = True
        discovery_state = run_discovery(
            extracted_meta,
            snapshot,
            message=message,
            history=user_history_texts,
            graph=context_graph,
        )
        turn_value = build_turn_value(
            discovery_state.fact_graph,
            extracted_meta,
            graph=context_graph,
            draft_confirmed=extracted_meta.draft_working_picture_confirmed,
        )
        if turn_value.deliver:
            extracted_meta.last_turn_value = turn_value.model_dump()
            extracted_meta.insight_delivered_turn = extracted_meta.message_count

        from app.advisor.pipeline.hypothesis_question_engine import is_hypothesis_engine_question

        hypothesis_question_used = is_hypothesis_engine_question(snapshot.required_question)

        return TurnPipelineResult(
            extracted_meta=extracted_meta,
            snapshot=snapshot,
            fit_decision=fit_decision,
            business_memory=business_memory,
            readiness=readiness,
            router_output=router_output,
            decision_trace=trace,
            legacy_fit=legacy_fit,
            context_graph=context_graph,
            internal_reasoning=internal_reasoning,
            turn_value=turn_value if turn_value.deliver else None,
            turn_plan=turn_plan,
            matched_archetypes=matched_archetypes,
            matched_archetype_ids=[arch.id for arch in matched_archetypes],
            archetype_similarity_scores=[round(score, 3) for score, _ in matched_scored],
            diagnostic_depth=depth.score,
            diagnostic_phase=depth.phase.value,
            issue_tree_snapshot=extracted_meta.issue_tree or issue_tree_to_dict(tree),
            turn_plan_priority=turn_plan.this_turn_priority if turn_plan else "",
            hypothesis_question_used=hypothesis_question_used,
        )
