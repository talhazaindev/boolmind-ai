"""Evidence-driven discovery engine — reason from facts and uncertainty, not catalogs."""

from __future__ import annotations

import re

from app.advisor.pipeline.business_systems_models import BusinessSystemsState
from app.advisor.pipeline.discovery_models import DiscoveryState, DynamicHypothesis, FactGraph
from app.advisor.pipeline.evidence_extractor import (
    build_conversation_text,
    contaminant_terms_in_text,
    extract_fact_graph,
    is_contaminant_term,
    term_in_vocabulary,
)
from app.advisor.pipeline.tension_engine import analyze_tensions, hypotheses_from_facts
from app.advisor.types import ConversationContextGraph, HypothesisSnapshot, SessionMetadata

_DEFAULT_TIMELINE = "recent months"


def _join_metrics(phrases: list[str]) -> str:
    if len(phrases) == 1:
        return phrases[0]
    if len(phrases) == 2:
        return f"{phrases[0]}, or {phrases[1]}"
    return ", ".join(phrases[:-1]) + f", or {phrases[-1]}"


def build_discriminative_question(
    hypotheses: list[DynamicHypothesis],
    fact_graph: FactGraph,
) -> str | None:
    """Highest-information-gain question when competing theories exist."""
    theories = [
        h
        for h in hypotheses
        if h.source in ("stakeholder", "inferred")
        and not h.id.startswith("hyp_symptom_")
    ]
    if len(theories) < 2:
        return None

    period = fact_graph.timeline_phrase or _DEFAULT_TIMELINE
    metrics: list[str] = []
    for hyp in theories[:4]:
        phrase = hyp.metric_phrase
        if phrase not in metrics:
            metrics.append(phrase)

    if len(metrics) < 2:
        return None

    joined = _join_metrics(metrics)
    return (
        f"Over the last {period}, which changed most materially — {joined}?"
    )


def build_outcome_clarification_question(fact_graph: FactGraph) -> str | None:
    if fact_graph.primary_outcome:
        return None
    return (
        "To focus on the right lever — which outcome is hurting most right now: "
        "customer retention, margins, delivery reliability, or something else?"
    )


def build_timeline_question() -> str:
    return (
        "When did you first notice this shift — roughly which quarter or month?"
    )


def score_question_information_gain(
    question: str,
    state: DiscoveryState,
) -> float:
    """Estimate uncertainty reduction — discriminative power among top hypotheses."""
    if not question.strip():
        return 0.0
    q = question.lower()
    hyps = state.hypotheses[:4]
    if not hyps:
        return 0.3 if any(w in q for w in ("what", "when", "how", "which")) else 0.1

    matched = 0
    for hyp in hyps:
        phrase = hyp.metric_phrase.lower()
        if phrase in q:
            matched += 1
            continue
        if any(len(w) > 5 and w in q for w in phrase.split()):
            matched += 1

    base = 0.25
    if "changed most materially" in q or "which changed" in q:
        base = 0.85
    if matched >= 2:
        base = min(0.98, base + 0.08 * matched)
    elif matched == 1 and len(hyps) == 1:
        base = 0.7

    competing = any(t.kind == "competing_explanations" for t in state.tensions)
    if competing and matched >= 2:
        base = max(base, 0.92)

    if any(p in q for p in ("is it more likely", "do you think", "which feels closer")):
        base *= 0.2

    return round(min(0.99, base), 2)


def score_expected_decision_value(
    question: str,
    state: DiscoveryState,
    *,
    bss: BusinessSystemsState | None = None,
) -> float:
    """EDV = separation + decision impact + outcome impact + edge uncertainty + opportunity cost."""
    ig = score_question_information_gain(question, state)
    edv = ig

    if bss:
        opp_boost = 0.0
        if bss.opportunity_ranking:
            top = bss.opportunity_ranking[0]
            if top.label.lower()[:20] in question.lower():
                opp_boost = min(0.15, top.opportunity_cost * 0.2)
        edv += opp_boost

        if bss.readiness.blocking_reasons:
            if any("constraint" in b for b in bss.readiness.blocking_reasons):
                if any(w in question.lower() for w in ("budget", "constraint", "timeline", "system")):
                    edv += 0.12
            if any("intervention_evidence" in b for b in bss.readiness.blocking_reasons):
                if any(w in question.lower() for w in ("track", "handoff", "crm", "invoice", "approval")):
                    edv += 0.12

        edge = bss.causal_graph.most_uncertain_edge()
        if edge and bss.confidence.competing_within_margin:
            for node in bss.causal_graph.nodes:
                if node.id in (edge.source_id, edge.target_id) and node.label.lower()[:15] in question.lower():
                    edv += 0.1
                    break

    return round(min(0.99, edv), 2)


def select_edv_question(
    bss: BusinessSystemsState,
    fact_graph: FactGraph,
    *,
    meta: SessionMetadata | None = None,
) -> tuple[str | None, float]:
    """Pick question maximizing expected decision value from business systems state."""
    from app.advisor.pipeline.progress_questions import (
        collect_progress_questions,
        is_generic_template_question,
        select_best_progress_question,
    )
    from app.advisor.pipeline.tension_engine import analyze_tensions, hypotheses_from_facts

    hypotheses = hypotheses_from_facts(fact_graph)
    skipped = set(meta.skipped_question_keys) if meta else set()
    tensions, gaps = analyze_tensions(fact_graph, hypotheses, skipped_keys=skipped)
    state = DiscoveryState(
        fact_graph=fact_graph,
        hypotheses=hypotheses,
        tensions=tensions,
        gaps=gaps,
    )

    candidates: list[tuple[float, str]] = list(
        collect_progress_questions(fact_graph, bss=bss, discovery=state, meta=meta)
    )

    disc = build_discriminative_question(hypotheses, fact_graph)
    if disc:
        candidates.append((score_expected_decision_value(disc, state, bss=bss), disc))

    for gap in gaps:
        if gap.suggested_probe:
            gain = gap.priority * 0.85
            candidates.append(
                (
                    score_expected_decision_value(gap.suggested_probe, state, bss=bss)
                    if gain > 0.4
                    else gain,
                    gap.suggested_probe,
                )
            )

    outcome_q = build_outcome_clarification_question(fact_graph)
    if outcome_q:
        candidates.append((score_expected_decision_value(outcome_q, state, bss=bss), outcome_q))

    if not candidates:
        progress_q, progress_score = select_best_progress_question(
            fact_graph, bss=bss, discovery=state, meta=meta, message=meta.pain_point or ""
        )
        if progress_q:
            candidates.append((progress_score, progress_q))

    if not candidates:
        return None, 0.0

    from app.advisor.pipeline.question_ledger import is_question_exhausted

    if meta:
        candidates = [
            (score, q)
            for score, q in candidates
            if not is_question_exhausted(q, meta)
        ]

    candidates = [
        (score, q) for score, q in candidates if not is_generic_template_question(q)
    ]
    if not candidates:
        progress_q, progress_score = select_best_progress_question(
            fact_graph, bss=bss, discovery=state, meta=meta, message=meta.pain_point or ""
        )
        return progress_q, progress_score

    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1], candidates[0][0]


def select_discovery_question(
    state: DiscoveryState,
    *,
    skipped_keys: set[str] | None = None,
) -> tuple[str | None, float]:
    """Pick the question that maximizes expected information gain."""
    skipped = skipped_keys or set()
    candidates: list[tuple[float, str]] = []

    disc = build_discriminative_question(state.hypotheses, state.fact_graph)
    if disc:
        gain = score_question_information_gain(disc, state)
        candidates.append((gain, disc))

    for gap in state.gaps:
        if gap.id == "gap_discriminative_metric" and disc:
            continue
        if gap.suggested_probe:
            gain = gap.priority * 0.85
            candidates.append((gain, gap.suggested_probe))

    if not state.fact_graph.timeline_phrase and len(state.hypotheses) >= 1 and "timeline" not in skipped:
        tq = build_timeline_question()
        candidates.append((0.45, tq))

    outcome_q = build_outcome_clarification_question(state.fact_graph)
    if outcome_q:
        candidates.append((0.5, outcome_q))

    if not candidates and state.hypotheses:
        hyp = state.hypotheses[0]
        probe = (
            f"What evidence would help confirm or rule out {hyp.metric_phrase} "
            f"as a driver of what you described?"
        )
        candidates.append((score_expected_decision_value(probe, state), probe))

    if not candidates:
        return None, 0.0

    candidates.sort(key=lambda x: x[0], reverse=True)
    best_gain, best_q = candidates[0]
    return best_q, best_gain


def run_discovery(
    meta: SessionMetadata,
    snapshot: HypothesisSnapshot,
    *,
    message: str = "",
    history: list[str] | None = None,
    graph: ConversationContextGraph | None = None,
) -> DiscoveryState:
    """Full evidence-driven discovery pass for one turn."""
    fact_graph = extract_fact_graph(
        meta, snapshot, message=message, history=history, graph=graph
    )
    hypotheses = hypotheses_from_facts(fact_graph)
    skipped = set(meta.skipped_question_keys) if meta else set()
    tensions, gaps = analyze_tensions(fact_graph, hypotheses, skipped_keys=skipped)
    state = DiscoveryState(
        fact_graph=fact_graph,
        hypotheses=hypotheses,
        tensions=tensions,
        gaps=gaps,
    )
    question, gain = select_discovery_question(state, skipped_keys=skipped)
    state.recommended_question = question
    state.question_gain_score = gain
    return state


def question_grounds_in_evidence(
    question: str,
    state: DiscoveryState,
) -> bool:
    """True when question tests at least one active hypothesis or addresses a gap."""
    if not question.strip():
        return False
    q = question.lower()
    for hyp in state.hypotheses[:4]:
        phrase = hyp.metric_phrase.lower()
        if phrase in q or any(len(w) > 5 and w in q for w in phrase.split()):
            return True
    for gap in state.gaps:
        if gap.suggested_probe and gap.suggested_probe.lower()[:30] in q:
            return True
    blob = state.fact_graph.blob().lower()
    if any(p in q for p in ("driver receives", "which driver", "coordinator", "routing", "assignment")):
        if any(s in blob for s in ("dispatch", "driver", "coordinator", "planning", "shipment")):
            return True
    if any(p in q for p in ("compliance", "priorit", "fifo", "handoff", "exception", "underwriting")):
        if any(s in blob for s in ("compliance", "underwriting", "loan", "application", "backlog")):
            return True
    if any(
        p in q
        for p in (
            "changed most materially",
            "which operational metric",
            "which changed",
            "reimbursement",
            "utilization",
            "labor cost",
            "shift materially",
            "after you",
        )
    ):
        if (
            state.hypotheses
            or state.fact_graph.facts_by_category("stakeholder_theory")
            or state.fact_graph.facts_by_category("organizational_change")
        ):
            return True
    if any(
        p in q
        for p in (
            "most profitable",
            "profit or cost",
            "offerings or channels",
            "visibility",
            "share of revenue goes to labor",
            "manual step would save",
            "track stock levels",
            "orders flow today",
            "roles absorb",
        )
    ):
        if any(
            s in blob
            for s in (
                "profit",
                "margin",
                "costing",
                "manual",
                "labor",
                "stock",
                "inventory",
                "order",
                "kitchen",
                "automate",
            )
        ):
            return True
    if state.hypotheses and any(
        p in q for p in ("changed most materially", "which changed", "first notice")
    ):
        return True
    return not state.hypotheses


def discovery_violations(
    question: str,
    meta: SessionMetadata,
    snapshot: HypothesisSnapshot,
    *,
    message: str = "",
    history: list[str] | None = None,
    graph: ConversationContextGraph | None = None,
) -> list[str]:
    """Validation: vocabulary grounding + template contamination checks."""
    violations: list[str] = []
    state = run_discovery(meta, snapshot, message=message, history=history, graph=graph)
    blob = build_conversation_text(
        meta, snapshot, message=message, history=history, graph=graph
    ).lower()
    q = question.lower()

    for term in contaminant_terms_in_text(question):
        if term not in blob and not any(term in h.metric_phrase.lower() for h in state.hypotheses):
            violations.append(f"template_contamination:{term}")

    if state.hypotheses and not question_grounds_in_evidence(question, state):
        violations.append("question_not_tied_to_evidence")

    # Flag domain-specific multi-word phrases not grounded in user vocabulary
    for term in re.findall(r"[a-z]{5,}(?:\s+[a-z]{4,})+", q):
        if term in blob:
            continue
        if is_contaminant_term(term):
            violations.append(f"ungrounded_phrase:{term}")
            continue
        if not term_in_vocabulary(term, state.fact_graph.vocabulary):
            if any(w in term for w in ("utilization", "reimbursement", "underwriting", "denial")):
                violations.append(f"ungrounded_phrase:{term}")

    return violations


def hedged_contributor_from_state(state: DiscoveryState) -> str:
    labels = [h.label for h in state.hypotheses[:3]]
    if not labels:
        return ""
    if len(labels) == 1:
        return f"One possibility is {labels[0]}."
    joined = ", ".join(labels[:-1]) + f", or {labels[-1]}"
    return f"Possible contributors include {joined}."
