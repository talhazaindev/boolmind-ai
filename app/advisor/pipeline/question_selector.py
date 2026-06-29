"""Question selection — business-systems fallback only (no vertical templates)."""

from __future__ import annotations

from app.advisor.pipeline.business_systems_engine import run_business_systems_reasoning
from app.advisor.pipeline.evidence_extractor import extract_fact_graph
from app.advisor.pipeline.progress_questions import (
    is_generic_template_question,
    select_best_progress_question,
)
from app.advisor.pipeline.question_gate import question_topic_for_text
from app.advisor.types import HypothesisSnapshot, SessionMetadata


def select_escalation_question(
    snapshot: HypothesisSnapshot,
    meta: SessionMetadata,
    *,
    violations: list[str] | None = None,
    exclude_topics: set[str] | None = None,
) -> str | None:
    """Pick replacement question when validation fails — EDV path only."""
    del violations, exclude_topics
    if snapshot.hypothesis_status == "conflicted":
        return snapshot.conflict_detail

    bss = run_business_systems_reasoning(meta, snapshot)
    if bss.recommended_question and not is_generic_template_question(bss.recommended_question):
        return bss.recommended_question

    fact_graph = extract_fact_graph(meta, snapshot)
    grounded, _ = select_best_progress_question(fact_graph, bss=bss)
    return grounded


def resolve_required_question(
    snapshot: HypothesisSnapshot,
    meta: SessionMetadata,
    violations: list[str] | None = None,
) -> HypothesisSnapshot:
    """Apply violation-aware question swap without vertical template routing."""
    if not snapshot.required_question or not violations:
        return snapshot
    replacement = select_escalation_question(snapshot, meta, violations=violations)
    if replacement:
        return snapshot.model_copy(update={"required_question": replacement})
    return snapshot.model_copy(update={"required_question": None})


def question_key_for_trace(question: str | None) -> str | None:
    if not question:
        return None
    topic = question_topic_for_text(question)
    return topic or "custom"
