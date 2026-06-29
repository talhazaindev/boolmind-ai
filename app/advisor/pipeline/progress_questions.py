"""Evidence-grounded progress questions — maximize conversation advancement from user facts."""

from __future__ import annotations

import re

from app.advisor.pipeline.business_systems_models import BusinessSystemsState
from app.advisor.pipeline.discovery_models import DiscoveryState, ExtractedFact, FactGraph
from app.advisor.pipeline.question_ledger import (
    detect_answered_topics_from_context,
    question_topic_families,
)
from app.advisor.types import SessionMetadata

_DEFAULT_TIMELINE = "recent months"
_GENERIC_HANDOFFS = (
    "timing, error rates, handoffs between teams, or how work is prioritized"
)

_CHANGE_VERBS = (
    "changed",
    "restructured",
    "revised",
    "updated",
    "introduced",
    "implemented",
    "redesigned",
    "rolled out",
    "switched",
)


def has_high_signal_progress(fact_graph: FactGraph) -> bool:
    """True when user gave structural facts that warrant change/competing-lever questions."""
    if fact_graph.facts_by_category("organizational_change"):
        return True
    if len(fact_graph.facts_by_category("stakeholder_theory")) >= 2:
        return True
    if (
        fact_graph.facts_by_category("stated_hypothesis")
        and (
            fact_graph.facts_by_category("organizational_change")
            or any("opened" in f.normalized for f in fact_graph.facts_by_category("scale"))
        )
    ):
        return True
    return False


def is_generic_template_question(question: str | None) -> bool:
    """True for legacy catalog fallbacks that do not reference user evidence."""
    if not question or not question.strip():
        return True
    q = question.lower().strip()
    if _GENERIC_HANDOFFS in q:
        return True
    if q.startswith("what has changed most recently"):
        return True
    if "throughput, cost per unit, or conversion rate" in q:
        return True
    if q.startswith("what tools do you use"):
        return True
    return False


def _shorten(text: str, max_len: int = 72) -> str:
    cleaned = text.strip().rstrip(".")
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[: max_len - 3].rsplit(" ", 1)[0] + "..."


def _symptom_phrases(fact_graph: FactGraph, limit: int = 3) -> list[str]:
    phrases: list[str] = []
    for fact in fact_graph.facts_by_category("symptom"):
        phrase = _shorten(fact.text, 48)
        if phrase not in phrases:
            phrases.append(phrase)
    for fact in fact_graph.facts_by_category("outcome"):
        phrase = _shorten(fact.text, 48)
        if phrase not in phrases:
            phrases.append(phrase)
    return phrases[:limit]


def _metric_probe_phrases(fact_graph: FactGraph) -> list[str]:
    """Operational metrics implied by user vocabulary — not industry templates."""
    blob = fact_graph.blob()
    probes: list[str] = []
    pairs: tuple[tuple[str, str], ...] = (
        (r"\bturnover\b", "staff turnover or retention"),
        (r"\bcomplaint", "client or customer complaints"),
        (r"\bwait time", "wait times or backlog"),
        (r"\bmargin", "margin or unit economics"),
        (r"\butilization|capacity|throughput", "utilization or throughput"),
        (r"\bproductivity|volume per", "productivity per person"),
        (r"\bcompensation|incentive|commission", "compensation or incentive metrics"),
        (r"\bscheduling|appointment", "appointments per period or scheduling load"),
        (r"\brevenue", "revenue per unit or location"),
    )
    for pattern, label in pairs:
        if re.search(pattern, blob, re.I) and label not in probes:
            probes.append(label)
    return probes[:4]


def build_change_impact_question(
    change: ExtractedFact,
    fact_graph: FactGraph,
) -> str | None:
    """Ask whether symptoms shifted after a stated organizational change."""
    metrics = _metric_probe_phrases(fact_graph)
    if not metrics:
        symptoms = _symptom_phrases(fact_graph)
        if not symptoms:
            return None
        metrics = symptoms[:3]

    period = fact_graph.timeline_phrase or _DEFAULT_TIMELINE
    change_summary = _shorten(change.text, 56)
    change_phrase = re.sub(
        r"^(?:(?:we|they)\s+)?(?:(?:recently|just)\s+)?(?:have\s+)?",
        "",
        change_summary,
        flags=re.I,
    ).strip()
    if not change_phrase:
        change_phrase = change_summary
    joined = ", ".join(metrics[:-1]) + f", or {metrics[-1]}" if len(metrics) > 1 else metrics[0]
    return (
        f"After you {change_phrase.lower()}, did {joined} "
        f"shift materially over the last {period}?"
    )


def build_competing_lever_question(
    stated: ExtractedFact,
    fact_graph: FactGraph,
) -> str | None:
    """Discriminate between a user-stated lever and other high-signal facts."""
    changes = fact_graph.facts_by_category("organizational_change")
    expansions = [f for f in fact_graph.facts if f.category == "scale" and "opened" in f.normalized]
    metrics = _metric_probe_phrases(fact_graph)
    if not metrics and not changes:
        return None

    belief = _shorten(stated.text, 64)
    if changes:
        change = _shorten(changes[0].text, 56)
        metric_join = ", ".join(metrics[:3]) if metrics else "the symptoms you described"
        return (
            f"Before focusing on {belief}, did {metric_join} change materially "
            f"after you {change.lower()}?"
        )
    if expansions:
        expansion = _shorten(expansions[0].text, 40)
        return (
            f"Management points to {belief} — since {expansion.lower()}, "
            f"which shifted more: capacity or workload, or {belief} specifically?"
        )
    return None


def build_symptom_prioritization_question(fact_graph: FactGraph) -> str | None:
    """Prioritize among outcomes/symptoms the user already named."""
    phrases = _symptom_phrases(fact_graph, limit=4)
    if len(phrases) < 2:
        return None
    joined = ", ".join(phrases[:-1]) + f", or {phrases[-1]}"
    return f"To focus on the right lever — which is hurting most right now: {joined}?"


def build_single_hypothesis_probe(
    label: str,
    fact_graph: FactGraph,
) -> str | None:
    """Evidence probe for one active hypothesis grounded in user vocabulary."""
    if not label.strip():
        return None
    symptoms = _symptom_phrases(fact_graph, limit=2)
    if symptoms:
        return (
            f"To test whether {_shorten(label, 56)} is driving this — "
            f"what changed first: {symptoms[0]}, or something else?"
        )
    period = fact_graph.timeline_phrase or _DEFAULT_TIMELINE
    return (
        f"Over the last {period}, what evidence would confirm or rule out "
        f"{_shorten(label, 56)} as a driver?"
    )


def discovery_saturated(
    fact_graph: FactGraph,
    meta: SessionMetadata | None = None,
) -> bool:
    """True when core operational context is rich enough to shift toward solution design."""
    blob = fact_graph.blob()
    topics = set(detect_answered_topics_from_context(blob))
    if meta:
        topics.update(meta.answered_question_keys)
    core = {"order_flow", "inventory_tracking", "tools_stack"}
    if len(core & topics) >= 2:
        return True
    if meta and len(meta.answered_question_keys) >= 4:
        return True
    if meta and meta.message_count >= 6:
        return True
    if meta and meta.message_count >= 2 and "order_flow" in topics:
        if re.search(r"automat", blob, re.I) and len(topics) >= 3:
            return True
    return False


def is_solution_prioritization_question(question: str | None) -> bool:
    if not question:
        return False
    q = question.lower()
    markers = (
        "automate first",
        "automate one workflow",
        "had to pick one",
        "highest-impact starting point",
        "more urgent",
    )
    return any(m in q for m in markers)


def build_solution_prioritization_question(fact_graph: FactGraph) -> str | None:
    """Move from discovery probes to automation prioritization."""
    blob = fact_graph.blob().lower()
    pains: list[str] = []
    if re.search(r"order|waiter|paper|kitchen", blob):
        pains.append("order-taking and kitchen handoff")
    if re.search(r"stock|inventory|stockout|waste|rotten", blob):
        pains.append("inventory and stockouts")
    if re.search(r"manual|2 hours|after closing|day end", blob):
        pains.append("end-of-day reporting")
    if not pains:
        return None
    if len(pains) == 1:
        return (
            f"Given what you've described, if you could automate one workflow first — "
            f"{pains[0]} — would that be the highest-impact starting point, "
            f"or is something else more urgent?"
        )
    joined = ", ".join(pains[:-1]) + f", or {pains[-1]}"
    return (
        f"You've outlined pain across {joined}. "
        f"Which single workflow would you automate first if you had to pick one?"
    )


def build_readiness_constraint_question(fact_graph: FactGraph) -> str | None:
    """After prioritization, probe constraints that shape a viable solution."""
    blob = fact_graph.blob().lower()
    if not re.search(r"automat|manual|restaurant|kitchen|order|stock", blob, re.I):
        return None
    return (
        "To shape a practical rollout — what matters most right now: "
        "keeping staff workflows familiar during the change, hitting a budget range, "
        "or going live before a busy season?"
    )


def _solution_already_asked(meta: SessionMetadata | None) -> bool:
    if not meta:
        return False
    if "solution_prioritization" in meta.skipped_question_keys:
        return True
    if "solution_prioritization" in meta.answered_question_keys:
        return True
    if meta.last_appended_question and is_solution_prioritization_question(
        meta.last_appended_question
    ):
        return True
    markers = (
        "automate first",
        "pick one",
        "highest-impact",
        "outlined pain across",
        "automate one workflow",
    )
    for fp in meta.asked_question_fingerprints:
        if any(m in fp for m in markers):
            return True
    return False


def _topic_satisfied(families: list[str], answered: set[str]) -> bool:
    return bool(families) and all(f in answered for f in families)


def build_operational_depth_questions(
    fact_graph: FactGraph,
    meta: SessionMetadata | None = None,
) -> list[tuple[float, str]]:
    """Higher-value operational probes from user vocabulary — any industry."""
    blob = fact_graph.blob()
    answered = set(detect_answered_topics_from_context(blob))
    if meta:
        answered.update(meta.answered_question_keys)
        answered.update(meta.skipped_question_keys)

    if discovery_saturated(fact_graph, meta):
        return []

    candidates: list[tuple[float, str]] = []

    def _add(score: float, question: str) -> None:
        families = question_topic_families(question)
        if _topic_satisfied(families, answered):
            return
        candidates.append((score, question))

    if re.search(r"profitab|profitable|margin|costing|unit economics", blob, re.I):
        if re.search(r"manual|spreadsheet|clear picture|can'?t see|cannot see|don'?t know which", blob, re.I):
            _add(
                0.89,
                "Today, can you see which offerings or channels are most profitable — "
                "even roughly — or is that visibility what's missing?",
            )

    if re.search(r"automat|manual", blob, re.I) and re.search(
        r"order|kitchen|table|waiter|serving|stock|inventory", blob, re.I
    ):
        _add(
            0.87,
            "How do orders flow today — counter, table service, phone, delivery — "
            "and where do mistakes or delays happen most?",
        )

    if re.search(r"labor cost|staff|waiter|kitchen|headcount", blob, re.I) and re.search(
        r"manual|automat", blob, re.I
    ):
        _add(
            0.85,
            "Which roles absorb the most manual time right now — taking orders, "
            "kitchen coordination, or stock counting?",
        )

    if re.search(r"stock|inventory", blob, re.I) and re.search(r"manual|spreadsheet", blob, re.I):
        _add(
            0.84,
            "How do you track stock levels today — and how often do you run out "
            "or over-order key items?",
        )

    return candidates


def collect_progress_questions(
    fact_graph: FactGraph,
    *,
    bss: BusinessSystemsState | None = None,
    discovery: DiscoveryState | None = None,
    meta: SessionMetadata | None = None,
) -> list[tuple[float, str]]:
    """Rank evidence-grounded questions that advance the conversation."""
    candidates: list[tuple[float, str]] = list(
        build_operational_depth_questions(fact_graph, meta=meta)
    )

    if discovery_saturated(fact_graph, meta):
        if not _solution_already_asked(meta):
            sol_q = build_solution_prioritization_question(fact_graph)
            if sol_q:
                candidates.insert(0, (0.96, sol_q))
        else:
            ready_q = build_readiness_constraint_question(fact_graph)
            if ready_q:
                candidates.insert(0, (0.9, ready_q))

    for change in fact_graph.facts_by_category("organizational_change"):
        q = build_change_impact_question(change, fact_graph)
        if q:
            score = 0.94
            if bss and bss.opportunity_ranking:
                score = min(0.99, score + 0.03)
            candidates.append((score, q))

    for stated in fact_graph.facts_by_category("stated_hypothesis"):
        q = build_competing_lever_question(stated, fact_graph)
        if q:
            candidates.append((0.91, q))

    if discovery:
        for gap in discovery.gaps:
            if gap.suggested_probe and gap.priority >= 0.5:
                candidates.append((gap.priority * 0.88, gap.suggested_probe))

    sym_q = build_symptom_prioritization_question(fact_graph)
    if sym_q:
        candidates.append((0.72, sym_q))

    if discovery and len(discovery.hypotheses) == 1:
        hyp = discovery.hypotheses[0]
        if hyp.source in ("stakeholder", "inferred") and (
            hyp.id.startswith("hyp_change_") or hyp.id.startswith("hyp_belief_")
        ):
            probe = build_single_hypothesis_probe(hyp.metric_phrase, fact_graph)
            if probe:
                candidates.append((0.68, probe))

    if bss and bss.causal_graph.most_uncertain_edge():
        edge = bss.causal_graph.most_uncertain_edge()
        if edge:
            labels = []
            for node in bss.causal_graph.nodes:
                if node.id in (edge.source_id, edge.target_id):
                    labels.append(node.label)
            if (
                len(labels) >= 2
                and all("driver of:" not in label.lower() for label in labels)
                and all(len(label.split()) >= 2 for label in labels)
            ):
                q = (
                    f"Which connection is stronger in your case — "
                    f"{_shorten(labels[0], 40)} leading to {_shorten(labels[1], 40)}, "
                    f"or a different path?"
                )
                candidates.append((0.55, q))

    # Deduplicate by normalized prefix
    seen: set[str] = set()
    unique: list[tuple[float, str]] = []
    for score, q in sorted(candidates, key=lambda x: x[0], reverse=True):
        key = q.lower()[:60]
        if key in seen:
            continue
        seen.add(key)
        unique.append((score, q))

    if meta:
        from app.advisor.pipeline.question_ledger import is_question_exhausted

        unique = [(s, q) for s, q in unique if not is_question_exhausted(q, meta)]
    return unique


def build_adaptive_follow_up(
    fact_graph: FactGraph,
    message: str = "",
    meta: SessionMetadata | None = None,
) -> tuple[str | None, float]:
    """Fresh probe from latest user vocabulary when standard candidates are exhausted."""
    blob = f"{fact_graph.blob()} {message.lower()}"

    if discovery_saturated(fact_graph, meta):
        if not _solution_already_asked(meta):
            sol_q = build_solution_prioritization_question(fact_graph)
            if sol_q:
                return sol_q, 0.92
        ready_q = build_readiness_constraint_question(fact_graph)
        if ready_q:
            return ready_q, 0.88

    if re.search(r"labor cost|reduce labor|staff cost|maximiz.*profit", blob, re.I):
        return (
            "Roughly what share of revenue goes to labor today — "
            "or is that part of the visibility you're trying to build?",
            0.83,
        )
    answered = set(detect_answered_topics_from_context(blob))
    if meta:
        answered.update(meta.answered_question_keys)
    if (
        re.search(r"stock|inventory", blob, re.I)
        and re.search(r"manual", blob, re.I)
        and "inventory_tracking" not in answered
    ):
        return (
            "How do you track stock levels today — and how often do you run out "
            "or over-order key items?",
            0.81,
        )
    if re.search(r"automate|automation|solution", blob, re.I) and re.search(r"manual", blob, re.I):
        return (
            "Which single manual step would save the most time if automated first?",
            0.8,
        )
    return None, 0.0


def select_best_progress_question(
    fact_graph: FactGraph,
    *,
    bss: BusinessSystemsState | None = None,
    discovery: DiscoveryState | None = None,
    meta: SessionMetadata | None = None,
    message: str = "",
) -> tuple[str | None, float]:
    """Highest-scoring progress question from user-grounded candidates."""
    ranked = collect_progress_questions(fact_graph, bss=bss, discovery=discovery, meta=meta)
    if ranked:
        return ranked[0][1], ranked[0][0]

    adaptive_q, adaptive_score = build_adaptive_follow_up(
        fact_graph, message=message, meta=meta
    )
    if adaptive_q and meta:
        from app.advisor.pipeline.question_ledger import is_question_exhausted

        if not is_question_exhausted(adaptive_q, meta):
            return adaptive_q, adaptive_score
    elif adaptive_q:
        return adaptive_q, adaptive_score

    phrases = _symptom_phrases(fact_graph, limit=3)
    if len(phrases) >= 2:
        joined = ", ".join(phrases[:-1]) + f", or {phrases[-1]}"
        return (
            f"Which of these matters most to fix first — {joined}?",
            0.55,
        )
    return None, 0.0
