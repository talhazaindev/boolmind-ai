"""Question value scoring — reject low-information discovery questions."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.advisor.orchestrator.problem_dimension import detect_problem_dimension
from app.advisor.types import ConversationContextGraph, HypothesisSnapshot, SessionMetadata

INFORMATION_GAIN_THRESHOLD: float = 0.55

_BINARY_HYPOTHESIS_PATTERNS: tuple[str, ...] = (
    r"\bis it more likely\b",
    r"\bis it more about\b",
    r"\bto narrow this down\b",
    r"\bwhich feels closer\b",
    r"\bdo you think\b",
    r"\bis the (?:real |primary )?issue\b",
    r"\bwhich system is (?:currently )?the bottleneck\b",
    r"\bis the bottleneck\b",
    r"\bprimary driver\b",
    r"\breal issue\b",
    r"\bor multiple\b",
    r"\bops, or\b",
    r"\bmore likely .{1,40}, or\b",
)

_DIAGNOSIS_DELEGATION_PATTERNS: tuple[str, ...] = (
    r"\bwhich (?:step|system|cause|factor) creates the most\b",
    r"\bwhere do delays or errors most often\b",
    r"\boptimizing for speed, cost\b",
)

_EVIDENCE_SEEKING_PATTERNS: tuple[str, ...] = (
    r"\bwhat changed\b",
    r"\bwhich metric\b",
    r"\bwhich changed most\b",
    r"\bwhich changed most materially\b",
    r"\bchanged most materially\b",
    r"\bhow (?:much|many|long)\b",
    r"\bwhen did\b",
    r"\broughly what (?:percentage|volume|share)\b",
    r"\bwhat percentage\b",
    r"\bhow are .{3,40} (?:prioritized|allocated|tracked|measured)\b",
    r"\bwalk me through\b",
    r"\bhow do .{3,40} (?:decide|determine|track)\b",
    r"\bover the last\b",
    r"\bwhich .{0,40}metric\b",
    r"\bleast predictable\b",
    r"\bdays-to-pay\b",
    r"\bhow have these shifted\b",
    r"\bhow do .{3,40} flow\b",
    r"\bwhere do mistakes or delays\b",
    r"\bwhich roles absorb\b",
    r"\bcan you see which offerings\b",
    r"\bhow do you track stock\b",
    r"\bshift materially\b",
    r"\bafter you\b",
)

_WEAK_ANSWER_TERMS: frozenset[str] = frozenset(
    {"ops", "multiple", "depends", "maybe", "both", "either", "not sure", "unclear"}
)

_CAUSE_SIGNALS: dict[str, tuple[str, ...]] = {
    "staffing_costs": (
        "staffing cost",
        "staffing costs",
        "labor cost",
        "headcount",
        "wage",
        "payroll",
    ),
    "scheduling_inefficiency": (
        "scheduling ineff",
        "dispatch scheduling",
        "route efficiency",
    ),
    "pricing_gap": (
        "pricing hasn't",
        "pricing has not",
        "pricing has",
        "undercharg",
        "market conditions",
        "hasn't kept up",
        "fee schedule",
    ),
    "reimbursement_delay": (
        "reimbursement",
        "insurance delay",
        "claims delay",
        "claim denial",
        "insurance reimbursement",
    ),
    "operating_expenses": (
        "operating expense",
        "overhead",
        "cost structure",
        "expenses rising",
    ),
    "labor_utilization": (
        "technician utilization",
        "utilization",
        "billable hours",
        "capacity utilization",
        "field hours",
    ),
    "invoicing_delay": (
        "invoicing delay",
        "invoice delay",
        "generate an invoice",
        "invoicing",
    ),
    "collections_friction": (
        "collections",
        "payment delay",
        "payment terms",
        "days-to-pay",
        "days to pay",
        "before payment clears",
    ),
    "payment_disputes": (
        "dispute",
        "disputes before payment",
        "disputes before",
    ),
    "fulfillment_reliability": (
        "fulfillment reliability",
        "fulfillment is slipping",
        "on-time delivery",
        "order accuracy",
        "stockout",
        "fill rate",
    ),
    "service_response_time": (
        "response times",
        "response time",
        "service responsiveness",
        "customer service believes",
    ),
    "pricing_competitiveness": (
        "pricing is the problem",
        "sales says pricing",
        "pricing hasn't",
        "pricing has not",
    ),
}

_CAUSE_METRIC_LABELS: dict[str, str] = {
    "staffing_costs": "labor costs per location",
    "scheduling_inefficiency": "scheduling efficiency or capacity utilization",
    "reimbursement_delay": "payment or reimbursement cycle times",
    "operating_expenses": "operating expenses excluding revenue growth",
    "labor_utilization": "utilization or billable hours",
    "pricing_gap": "pricing or average margin",
    "pricing_competitiveness": "pricing competitiveness or average margin",
    "fulfillment_reliability": "on-time delivery rate or order fill accuracy",
    "service_response_time": "customer service response times",
    "pricing": "pricing or fee schedules",
    "efficiency": "time spent on non-billable or low-value work",
    "utilization": "mix of high- vs low-margin services",
    "invoicing_delay": "time from closed-won to invoice sent",
    "collections_friction": "average days-to-pay or collection cycle time",
    "payment_disputes": "invoice dispute or rework rate before payment",
}

_CASH_FLOW_CAUSES = frozenset(
    {"invoicing_delay", "collections_friction", "payment_disputes"}
)

_ASSUMED_STAGE_PROBE_RE = re.compile(
    r"walk me through one typical item at the (\w+(?:\s+\w+)?)\s+step",
    re.I,
)


@dataclass(frozen=True)
class QuestionValueScore:
    information_gain: float
    user_observable: float
    diagnostic_leverage: float
    non_leading: float

    @property
    def total(self) -> float:
        return (
            self.information_gain * 0.4
            + self.user_observable * 0.25
            + self.diagnostic_leverage * 0.25
            + self.non_leading * 0.1
        )


def _blob(
    meta: SessionMetadata,
    snapshot: HypothesisSnapshot,
    *,
    message: str = "",
    history: list[str] | None = None,
    graph: ConversationContextGraph | None = None,
) -> str:
    parts = [
        meta.business_type or "",
        meta.industry or "",
        meta.pain_point or "",
        meta.goals or "",
        message,
        " ".join(history or []),
        " ".join(snapshot.confirmed_facts),
        " ".join(snapshot.scale_indicators),
    ]
    if graph:
        parts.extend(graph.pain_points)
    return " ".join(parts).lower()


def extract_competing_causes(blob: str) -> list[str]:
    """User-named competing causes from conversation text."""
    found: list[str] = []
    for cause_id, signals in _CAUSE_SIGNALS.items():
        if any(s in blob for s in signals):
            found.append(cause_id)
    if "pricing_gap" in found and "pricing_competitiveness" not in found:
        found.append("pricing_competitiveness")
    # Bare "scheduling" only when not field-service context with technician framing
    if "scheduling_inefficiency" not in found and re.search(
        r"\bscheduling\b", blob, re.I
    ):
        if not any(t in blob for t in ("technician", "hvac", "plumbing", "field")):
            found.append("scheduling_inefficiency")
    return list(dict.fromkeys(found))


def _metric_labels_for_causes(
    causes: list[str],
    meta: SessionMetadata,
    snapshot: HypothesisSnapshot,
    *,
    message: str = "",
    history: list[str] | None = None,
    graph: ConversationContextGraph | None = None,
) -> list[str]:
    from app.advisor.pipeline.domain_consistency import (
        detect_industry_context,
        metric_label_for_cause,
    )

    industry = detect_industry_context(
        meta, snapshot, message=message, history=history, graph=graph
    )
    labels: list[str] = []
    for cause_id in causes:
        label = metric_label_for_cause(
            cause_id,
            industry,
            fallback=_CAUSE_METRIC_LABELS.get(cause_id, cause_id.replace("_", " ")),
        )
        if label not in labels:
            labels.append(label)
    return labels


def _time_horizon_phrase(blob: str) -> str:
    if re.search(r"18\s*months?", blob, re.I):
        return "18 months"
    if "three quarter" in blob or "3 quarter" in blob:
        return "three quarters"
    if "six month" in blob or "6 month" in blob:
        return "six months"
    if re.search(r"12\s*months?", blob, re.I):
        return "twelve months"
    if "quarter" in blob:
        return "the last few quarters"
    return "recent months"


def build_metric_change_question(
    causes: list[str],
    blob: str,
    *,
    meta: SessionMetadata | None = None,
    snapshot: HypothesisSnapshot | None = None,
    message: str = "",
    history: list[str] | None = None,
    graph: ConversationContextGraph | None = None,
) -> str | None:
    """Evidence-seeking question when leadership cites multiple competing causes."""
    if len(causes) < 2:
        return None
    if meta is not None and snapshot is not None:
        labels = _metric_labels_for_causes(
            causes[:5], meta, snapshot, message=message, history=history, graph=graph
        )
    else:
        labels = [_CAUSE_METRIC_LABELS.get(c, c.replace("_", " ")) for c in causes[:5]]
    period = _time_horizon_phrase(blob)
    if len(labels) == 2:
        return (
            f"Over the last {period}, which changed most materially — "
            f"{labels[0]}, or {labels[1]}?"
        )
    joined = ", ".join(labels[:-1])
    return (
        f"Over the last {period}, which changed most materially — "
        f"{joined}, or {labels[-1]}?"
    )


def build_profitability_evidence_question(
    meta: SessionMetadata,
    snapshot: HypothesisSnapshot,
    *,
    message: str = "",
    history: list[str] | None = None,
    graph: ConversationContextGraph | None = None,
) -> str | None:
    blob = _blob(meta, snapshot, message=message, history=history, graph=graph)
    dimension = detect_problem_dimension(meta, message, history)
    if dimension not in ("profitability",) and "profit" not in blob and "margin" not in blob:
        return None

    causes = extract_competing_causes(blob)
    return build_metric_change_question(
        causes,
        blob,
        meta=meta,
        snapshot=snapshot,
        message=message,
        history=history,
        graph=graph,
    )


def build_cash_flow_evidence_question(
    meta: SessionMetadata,
    snapshot: HypothesisSnapshot,
    *,
    message: str = "",
    history: list[str] | None = None,
    graph: ConversationContextGraph | None = None,
) -> str | None:
    blob = _blob(meta, snapshot, message=message, history=history, graph=graph)
    if not any(
        k in blob
        for k in ("cash flow", "cash-flow", "invoice", "collections", "days-to-pay", "payment")
    ):
        return None

    causes = [c for c in extract_competing_causes(blob) if c in _CASH_FLOW_CAUSES]
    metric_q = build_metric_change_question(causes, blob)
    if metric_q:
        return metric_q

    if "invoice" in blob and any(k in blob for k in ("payment", "collect", "dispute", "crm")):
        period = _time_horizon_phrase(blob)
        return (
            f"Over the last {period}, how have these shifted — days from closed-won to "
            f"invoice sent, average days-to-pay, and the share of invoices disputed or "
            f"reworked before payment?"
        )
    if any(k in blob for k in ("cash flow", "cash-flow")) and any(
        k in blob for k in ("finance blames", "sales blames", "leadership")
    ):
        return (
            "Which cash-flow metric has become least predictable recently — invoice "
            "generation lag, dispute rate before send, days-to-pay, or collection write-offs?"
        )
    return None


def workflow_stage_denied(blob: str, stage: str) -> bool:
    stage_words = stage.replace("_", " ")
    denials = (
        f"no {stage_words}",
        f"no formal {stage_words}",
        f"don't have {stage_words}",
        f"do not have {stage_words}",
        f"not {stage_words}",
        f"probably not {stage_words}",
    )
    lower = blob.lower()
    return any(p in lower for p in denials)


def user_confirmed_workflow_stage(blob: str, stage: str) -> bool:
    if workflow_stage_denied(blob, stage):
        return False
    stage_words = stage.replace("_", " ")
    if stage_words in blob.lower():
        return True
    explicit = {
        "intake": ("intake", "onboarding step", "signup step"),
        "quality_gate": ("compliance review", "review queue", "qc step"),
        "delivery": ("delivery step", "fulfillment step"),
    }
    return any(term in blob.lower() for term in explicit.get(stage, ()))


def is_assumed_workflow_stage_question(question: str, blob: str) -> bool:
    m = _ASSUMED_STAGE_PROBE_RE.search(question.lower())
    if not m:
        return False
    stage_guess = m.group(1).replace(" ", "_")
    return not user_confirmed_workflow_stage(blob, stage_guess)


def build_ops_evidence_question(
    graph: ConversationContextGraph,
    snapshot: HypothesisSnapshot,
    *,
    message: str = "",
    history: list[str] | None = None,
) -> str | None:
    blob = _blob(
        SessionMetadata(),
        snapshot,
        message=message,
        history=history,
        graph=graph,
    )

    if ("marked as closed" in blob or "closed in the crm" in blob) and "invoice" in blob:
        return (
            "After a deal is marked closed in the CRM, walk me through what happens "
            "before cash is collected — where do delays, disputes, or rework most often appear?"
        )
    if "invoice" in blob and any(k in blob for k in ("payment", "collect", "dispute")):
        return (
            "From invoice generation through payment clearing, which step has the "
            "most variance recently — invoice prep, customer dispute, or collection follow-up?"
        )

    stage = graph.universal_stage
    if stage != "unknown" and user_confirmed_workflow_stage(blob, stage):
        return (
            f"Walk me through one typical item at the {stage.replace('_', ' ')} step — "
            "roughly how long does it sit there, and what happens next?"
        )
    return None


def compose_evidence_question(
    graph: ConversationContextGraph | None,
    snapshot: HypothesisSnapshot,
    meta: SessionMetadata,
    *,
    message: str = "",
    history: list[str] | None = None,
) -> str | None:
    """Highest-value evidence-seeking question — cash-flow signals, then discovery."""
    cash_q = build_cash_flow_evidence_question(
        meta, snapshot, message=message, history=history, graph=graph
    )
    if cash_q:
        return cash_q

    from app.advisor.pipeline.discovery_engine import run_discovery, select_discovery_question

    state = run_discovery(
        meta, snapshot, message=message, history=history, graph=graph
    )
    question, gain = select_discovery_question(state)
    if question and gain >= 0.55:
        return question

    profit_q = build_profitability_evidence_question(
        meta, snapshot, message=message, history=history, graph=graph
    )
    if profit_q:
        return profit_q
    if graph:
        ops_q = build_ops_evidence_question(
            graph, snapshot, message=message, history=history
        )
        if ops_q:
            return ops_q
    if question and gain >= 0.4:
        return question
    return None


def asks_user_to_diagnose(question: str) -> bool:
    q = question.lower()
    if any(re.search(pat, q, re.I) for pat in _EVIDENCE_SEEKING_PATTERNS):
        return False
    return any(re.search(pat, q, re.I) for pat in _BINARY_HYPOTHESIS_PATTERNS) or any(
        re.search(pat, q, re.I) for pat in _DIAGNOSIS_DELEGATION_PATTERNS
    )


def binary_hypothesis_choice(question: str) -> bool:
    q = question.lower()
    if any(re.search(pat, q, re.I) for pat in _EVIDENCE_SEEKING_PATTERNS):
        return False
    if any(re.search(pat, q, re.I) for pat in _BINARY_HYPOTHESIS_PATTERNS):
        return True
    # Short either/or between abstract labels (ops vs scheduling)
    if re.search(r"\bor\b", q) and any(
        term in q for term in ("ops", "multiple", "scheduling", "staffing", "bottleneck")
    ):
        if not any(re.search(pat, q, re.I) for pat in _EVIDENCE_SEEKING_PATTERNS):
            return True
    return False


def answer_likely_observable(question: str) -> bool:
    q = question.lower()
    if any(re.search(pat, q, re.I) for pat in _EVIDENCE_SEEKING_PATTERNS):
        return True
    if "which" in q and any(w in q for w in ("metric", "changed", "shifted", "variance")):
        return True
    if asks_user_to_diagnose(question):
        return False
    return "how" in q or "what" in q or "when" in q or "roughly" in q


def score_question_value(
    question: str,
    snapshot: HypothesisSnapshot,
    meta: SessionMetadata,
    graph: ConversationContextGraph | None = None,
) -> QuestionValueScore:
    q = question.lower()
    blob = _blob(meta, snapshot)

    if asks_user_to_diagnose(question) or binary_hypothesis_choice(question):
        return QuestionValueScore(0.1, 0.2, 0.1, 0.0)

    info = 0.35
    if any(re.search(pat, q, re.I) for pat in _EVIDENCE_SEEKING_PATTERNS):
        info = 0.9
    elif "which" in q and "metric" in q:
        info = 0.88
    elif "which" in q and "changed" in q:
        info = 0.85
    elif "walk me through" in q:
        info = 0.8

    observable = 0.85 if answer_likely_observable(question) else 0.25

    leverage = 0.4
    causes = extract_competing_causes(blob)
    if causes and any(label.split()[0] in q for label in (_CAUSE_METRIC_LABELS.get(c, c) for c in causes)):
        leverage = 0.9
    elif snapshot.confidence_scores and info >= 0.8:
        leverage = 0.75

    non_leading = 0.9
    if any(term in q for term in ("bottleneck", "root cause", "primary issue", "real issue")):
        non_leading = 0.2
    if re.search(r"\bthe problem is\b", q):
        non_leading = 0.1

    if graph and graph.active_thread and "priorit" in q:
        leverage = max(leverage, 0.8)

    return QuestionValueScore(info, observable, leverage, non_leading)


def is_acceptable_discovery_question(
    question: str | None,
    snapshot: HypothesisSnapshot,
    meta: SessionMetadata,
    graph: ConversationContextGraph | None = None,
) -> bool:
    if not question or not question.strip():
        return False
    if asks_user_to_diagnose(question) or binary_hypothesis_choice(question):
        return False
    if not answer_likely_observable(question):
        return False
    score = score_question_value(question, snapshot, meta, graph)
    return score.total >= INFORMATION_GAIN_THRESHOLD


def question_value_violations(
    question: str | None,
    snapshot: HypothesisSnapshot,
    meta: SessionMetadata,
    graph: ConversationContextGraph | None = None,
    *,
    message: str = "",
    history: list[str] | None = None,
) -> list[str]:
    if not question:
        return []
    from app.advisor.pipeline.progress_questions import is_solution_prioritization_question

    if is_solution_prioritization_question(question):
        return []
    from app.advisor.pipeline.hypothesis_question_engine import is_hypothesis_engine_question

    hypothesis_engine_q = is_hypothesis_engine_question(question)
    q_lower = question.lower()
    if any(
        p in q_lower
        for p in ("practical rollout", "budget range", "busy season", "workflows familiar")
    ):
        return []
    violations: list[str] = []
    if not hypothesis_engine_q and asks_user_to_diagnose(question):
        violations.append("asks_user_to_diagnose")
    if not hypothesis_engine_q and binary_hypothesis_choice(question):
        violations.append("binary_hypothesis_choice")
    if not hypothesis_engine_q and not answer_likely_observable(question):
        violations.append("answer_not_observable")

    from app.advisor.pipeline.scale_context import (
        is_volume_probe_question,
        scale_is_satisfied,
        scale_required_for_diagnosis,
    )

    from app.advisor.pipeline.domain_consistency import domain_terminology_violations

    blob = _blob(meta, snapshot, message=message, history=history, graph=graph)
    violations.extend(
        domain_terminology_violations(
            question,
            meta,
            snapshot,
            message=message,
            history=history,
            graph=graph,
        )
    )
    if is_volume_probe_question(question) and (
        scale_is_satisfied(meta, snapshot, message=message, history=history, graph=graph)
        or not scale_required_for_diagnosis(meta, snapshot, graph)
    ):
        violations.append("scale_not_required")
    if is_assumed_workflow_stage_question(question, blob):
        violations.append("assumed_workflow_stage")

    from app.advisor.pipeline.hypothesis_engine import hypothesis_relevance_violations

    violations.extend(
        hypothesis_relevance_violations(
            question,
            meta,
            snapshot,
            message=message,
            history=history,
            graph=graph,
        )
    )

    score = score_question_value(question, snapshot, meta, graph)
    if not hypothesis_engine_q and score.total < INFORMATION_GAIN_THRESHOLD:
        violations.append("low_information_gain")
    return violations
