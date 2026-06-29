"""Contextual question composition — business-systems EDV path only."""

from __future__ import annotations

from app.advisor.knowledge.ontology_schema import BusinessArchetype
from app.advisor.orchestrator.fact_grounding import question_assumes_unstated_facts
from app.advisor.pipeline.business_systems_engine import run_business_systems_reasoning
from app.advisor.pipeline.diagnostic_protocol import (
    issue_tree_from_session,
    select_question_from_issue_tree,
)
from app.advisor.pipeline.question_gate import validate_follow_up_question
from app.advisor.pipeline.progress_questions import (
    has_high_signal_progress,
    is_generic_template_question,
    select_best_progress_question,
)
from app.advisor.types import (
    ConversationContextGraph,
    ExecutionMode,
    HypothesisSnapshot,
    HypothesisState,
    InternalReasoning,
    SessionMetadata,
)


def build_narrator_hints(
    graph: ConversationContextGraph,
    reasoning: InternalReasoning,
    snapshot: HypothesisSnapshot,
    meta: SessionMetadata,
    mode: ExecutionMode,
) -> list[str]:
    """Acknowledgment hints for the LLM narrator block."""
    from app.advisor.orchestrator.fact_grounding import build_narrator_grounding_hints
    from app.advisor.orchestrator.inference_builder import acknowledgment_snippets

    hints = build_narrator_grounding_hints(graph, snapshot, reasoning, meta, mode)
    if not hints:
        hints = acknowledgment_snippets(graph)
    return hints[:4]


def compose_contextual_question(
    graph: ConversationContextGraph,
    snapshot: HypothesisSnapshot,
    meta: SessionMetadata,
    *,
    bi_snippets: list[str] | None = None,
    message: str = "",
    history: list[str] | None = None,
    matched_scored: list[tuple[float, BusinessArchetype]] | None = None,
) -> tuple[str | None, InternalReasoning]:
    """Return EDV-optimized question from business-systems reasoning."""
    del bi_snippets  # catalog snippets removed from critical path

    matched_archetypes = [arch for _, arch in (matched_scored or [])]

    bss = run_business_systems_reasoning(
        meta,
        snapshot,
        message=message,
        history=history,
        graph=graph,
        matched_archetypes=matched_archetypes or None,
    )

    reasoning = InternalReasoning(
        observations=[bss.narrative_state.pattern_label or "pattern pending"],
        evidence=[c.label for c in bss.confidence.root_causes[:3]],
        inferences=[g.specialization_label or g.universal_id for g in bss.capability_gaps[:3]],
        universal_stage=graph.universal_stage,
        next_action="recommend" if bss.readiness.ready else "ask_followup",
    )
    if bss.causal_graph.nodes:
        reasoning.top_hypothesis_ids = [n.id for n in bss.causal_graph.nodes if n.kind == "cause"][:3]

    from app.advisor.pipeline.diagnostic_protocol import DiagnosticDepth, issue_tree_from_session
    from app.advisor.pipeline.hypothesis_question_engine import select_hypothesis_question
    from app.advisor.pipeline.question_ledger import is_question_exhausted, normalize_question_fingerprint

    already_asked = set(meta.asked_question_fingerprints)
    if meta.last_appended_question:
        already_asked.add(normalize_question_fingerprint(meta.last_appended_question))

    depth = DiagnosticDepth.from_session(meta)
    hypothesis_q = select_hypothesis_question(
        matched_scored=matched_scored or [],
        issue_tree=issue_tree_from_session(meta),
        depth=depth,
        already_asked=already_asked,
    )
    should_short_circuit = bool(matched_scored) or (
        depth.score < 20 and len(message.strip()) < 100
    )
    if should_short_circuit and hypothesis_q and not is_question_exhausted(hypothesis_q, meta):
        return hypothesis_q, reasoning

    from app.advisor.orchestrator.hypothesis_state import select_required_question
    from app.advisor.pipeline.discovery_engine import run_discovery, select_discovery_question

    discovery_state = run_discovery(meta, snapshot, message=message, history=history, graph=graph)
    disc_q, disc_gain = select_discovery_question(discovery_state)
    progress_q, progress_score = select_best_progress_question(
        discovery_state.fact_graph, bss=bss, discovery=discovery_state, meta=meta, message=message
    )
    catalog_q = select_required_question(
        snapshot, snapshot.resolved_unknowns, meta
    )
    high_signal = has_high_signal_progress(discovery_state.fact_graph)

    issue_tree_q = select_question_from_issue_tree(issue_tree_from_session(meta))

    candidates: list[str | None] = []
    if issue_tree_q:
        candidates.append(issue_tree_q)
    if high_signal:
        candidates.extend([progress_q, bss.recommended_question])
    else:
        candidates.extend([catalog_q, bss.recommended_question, disc_q if disc_gain >= 0.55 else None])
    candidates.extend([progress_q, disc_q if disc_gain >= 0.55 else None, snapshot.required_question])

    from app.advisor.pipeline.question_ledger import filter_questions_by_ledger, is_question_exhausted

    filtered = [
        q
        for q in filter_questions_by_ledger(candidates, meta)
        if not is_generic_template_question(q)
    ]

    question = None
    for candidate in filtered:
        if question_assumes_unstated_facts(candidate, graph, snapshot):
            continue
        validated, _violations = validate_follow_up_question(
            candidate,
            snapshot,
            meta,
            graph=graph,
            message=message,
            history=history,
        )
        if validated and not is_question_exhausted(validated, meta):
            question = validated
            break

    if (
        not question
        and snapshot.required_question
        and not is_generic_template_question(snapshot.required_question)
        and not is_question_exhausted(snapshot.required_question, meta)
    ):
        question = snapshot.required_question

    return question, reasoning


def update_hypotheses_from_graph(
    meta: SessionMetadata,
    graph: ConversationContextGraph,
    snapshot: HypothesisSnapshot,
    *,
    message: str = "",
) -> list[HypothesisState]:
    """Project causal graph root causes into hypothesis state."""
    bss = run_business_systems_reasoning(
        meta, snapshot, message=message, graph=graph
    )
    updated: list[HypothesisState] = []
    for rc in bss.confidence.root_causes[:5]:
        updated.append(
            HypothesisState(
                id=rc.cause_id,
                label=rc.label,
                confidence=rc.confidence,
                status="active",
            )
        )
    return updated
