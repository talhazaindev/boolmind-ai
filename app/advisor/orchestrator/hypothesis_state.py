"""Deterministic hypothesis snapshot — no reasoning_engine imports."""

from __future__ import annotations

import re

from app.advisor.orchestrator.conversation_progression import (
    HYPOTHESIS_EVIDENCE_THRESHOLD,
    compute_conversation_stage,
)
from app.advisor.pipeline.evidence_engine import compute_evidence_score, merge_evidence_peak
from app.advisor.pipeline.question_gate import known_discovery_topics, validate_follow_up_question
from app.advisor.pipeline.volume_patterns import extract_backlog_count, extract_volume_indicators
from app.advisor.pipeline.scale_context import extract_business_scale_phrases
from app.advisor.orchestrator.problem_dimension import detect_problem_dimension
from app.advisor.orchestrator.signals import ACTIVE_SIGNALS_VERSION, get_signal_registry
from app.advisor.orchestrator.signals.v1 import INFORMATION_GAIN_QUESTIONS
from app.advisor.orchestrator.strategy_diagnosis import infer_growth_blocker
from app.advisor.orchestrator.operations_diagnosis import infer_ops_bottleneck
from app.advisor.types import (
    DiagnoseDepth,
    HypothesisSnapshot,
    SessionMetadata,
)

_PLANNING_EVIDENCE = (
    "spreadsheet", "manual planning", "coordinator", "driver wait", "driver waits",
    "assignment", "dispatch delay", "planning",
)
_SCALE_PATTERN = re.compile(
    r"(\d[\d,]*)\s*"
    r"(?:loan\s+applications?|applications?|shipments|orders|deliveries|loans|cases|transactions)"
    r"\s*(per day|daily|a day)?",
    re.I,
)
_DRIVER_WAIT_PATTERN = re.compile(r"(\d+)\s*[-–]?\s*(\d+)?\s*minutes?", re.I)
_COORDINATOR_PATTERN = re.compile(r"(\d+)\s*coordinators?", re.I)


def _blob(meta: SessionMetadata, message: str, history: list[str]) -> str:
    parts = [
        meta.business_type or "",
        meta.industry or "",
        meta.pain_point or "",
        meta.goals or "",
        message,
        " ".join(history),
    ]
    return " ".join(parts).lower()


def _detect_business_vertical(message: str, history: list[str], meta: SessionMetadata) -> str | None:
    if meta.active_business_vertical:
        return meta.active_business_vertical
    blob = _blob(meta, message, history)
    if any(k in blob for k in ("logistics", "dispatch", "shipment", "fleet")):
        return "logistics"
    if any(k in blob for k in ("lending", "loan", "underwriting", "origination", "commercial lending")):
        return "financial_services"
    if "manufacturing" in blob or "factory" in blob:
        return "manufacturing"
    if meta.industry:
        return meta.industry
    return None


def _detect_business_model(meta: SessionMetadata, message: str, history: list[str]) -> str:
    if meta.business_model and meta.business_model != "unknown":
        return meta.business_model
    signals = get_signal_registry()
    blob = _blob(meta, message, history)
    scores: dict[str, int] = {}
    for model, keywords in signals.business_model_signals.items():
        scores[model] = sum(1 for kw in keywords if kw in blob)
    best = max(scores, key=lambda k: scores[k])
    if scores[best] > 0:
        return best
    return "unknown"


def _detect_system_context(message: str, history: list[str]) -> list[str]:
    blob = " ".join([message, *history]).lower()
    signals = get_signal_registry()
    found: list[str] = []
    for kw in signals.integration_keywords:
        if kw in blob and kw not in found:
            found.append(kw)
    if "spreadsheet" in blob and "spreadsheet" not in found:
        found.append("spreadsheet")
    if "manual" in blob and "manual" not in found:
        found.append("manual")
    return found


def _detect_scale_indicators(message: str, history: list[str]) -> list[str]:
    blob = " ".join([message, *history])
    signals = get_signal_registry()
    found: list[str] = []
    for pat in signals.scale_patterns:
        m = re.search(pat, blob, re.I)
        if m:
            found.append(m.group(0))
    m = _SCALE_PATTERN.search(blob)
    if m:
        found.append(m.group(0))
    found.extend(extract_volume_indicators(blob))
    found.extend(extract_business_scale_phrases(blob))
    return list(dict.fromkeys(found))


def _extract_confirmed_facts(message: str, history: list[str]) -> list[str]:
    blob = " ".join([message, *history[-4:]]).lower()
    facts: list[str] = []
    if "logistics" in blob:
        facts.append("logistics company")
    if any(k in blob for k in ("lending", "loan application", "commercial lending", "underwriting")):
        facts.append("commercial lending operation")
    m = _SCALE_PATTERN.search(blob)
    if m:
        facts.append(m.group(0).strip())
    for vol in extract_volume_indicators(blob):
        if vol not in facts:
            facts.append(vol)
    backlog = extract_backlog_count(blob)
    if backlog:
        facts.append(backlog)
    if "compliance" in blob and "manual" in blob:
        facts.append("compliance reviews are manual")
    elif "compliance" in blob:
        facts.append("compliance in workflow")
    if any(p in blob for p in ("automation", "automated", "automating")):
        if any(p in blob for p in ("fail", "poor adoption", "exception", "revert", "went back")):
            facts.append("prior automation failed due to exceptions")
    if "spreadsheet" in blob:
        facts.append("manual spreadsheet planning")
    cm = _COORDINATOR_PATTERN.search(blob)
    if cm:
        facts.append(f"{cm.group(1)} coordinators")
    dw = _DRIVER_WAIT_PATTERN.search(blob)
    if dw and ("driver" in blob or "wait" in blob):
        facts.append(f"drivers wait {dw.group(0)}")
    if any(p in blob for p in _PLANNING_EVIDENCE):
        facts.append("planning is manual bottleneck")
    return list(dict.fromkeys(facts))


def _resolve_unknowns(
    meta: SessionMetadata,
    message: str,
    history: list[str],
    scale_indicators: list[str],
    primary_bottleneck: str | None,
) -> tuple[list[str], list[str]]:
    """Return (resolved, still_unresolved)."""
    blob = _blob(meta, message, history)
    resolved: list[str] = []
    unknowns: list[str] = []

    if meta.industry or meta.business_type or "logistics" in blob or "manufacturing" in blob:
        resolved.append("business_context")
    else:
        unknowns.append("business_context")

    if meta.pain_point or primary_bottleneck:
        resolved.append("pain_point")
    else:
        unknowns.append("pain_point")

    if meta.goals or any(g in blob for g in ("improve", "reduce", "optimize", "efficiency")):
        resolved.append("goals")
    else:
        unknowns.append("goals")

    if scale_indicators or meta.data_context:
        resolved.append("scale")
    else:
        unknowns.append("scale")

    if any(
        p in blob
        for p in (
            "manual compliance",
            "compliance reviews are manual",
            "compliance is manual",
            "compliance team",
            "compliance analysts",
            "compliance review",
            "compliance reviews",
        )
    ):
        resolved.append("compliance_process")
    else:
        unknowns.append("compliance_process")

    if any(p in blob for p in ("fifo", "prioritiz", "risk tier", "reviewed first")):
        resolved.append("compliance_prioritization")
    else:
        unknowns.append("compliance_prioritization")

    if "backlog" in blob:
        resolved.append("backlog_size")
    else:
        unknowns.append("backlog_size")

    if any(p in blob for p in ("automation", "automated")) and any(
        p in blob for p in ("fail", "poor", "adoption", "exception", "revert")
    ):
        resolved.append("automation_history")
    elif "automation" in blob or "automate" in blob:
        unknowns.append("automation_history")

    if any(p in blob for p in ("underwriting", "underwriter")) or (
        "analyst" in blob and any(k in blob for k in ("underwriting", "loan", "lending"))
    ):
        resolved.append("underwriting_process")
    elif any(k in blob for k in ("lending", "loan", "approval")):
        unknowns.append("underwriting_process")

    # Planning delay evidence resolves generic bottleneck unknown
    planning_known = (
        primary_bottleneck in ("dispatch", "planning", "throughput", "delivery")
        or any(p in blob for p in _PLANNING_EVIDENCE)
        or ("driver" in blob and "wait" in blob)
    )
    if planning_known:
        resolved.append("bottleneck")
        resolved.append("planning_delay")
    elif not meta.ops_bottleneck and not meta.growth_blocker:
        unknowns.append("bottleneck")

    if "spreadsheet" in blob or "erp" in blob or "tms" in blob:
        resolved.append("integration")
    elif "integration" not in resolved:
        unknowns.append("integration")

    return list(dict.fromkeys(resolved)), unknowns


def _count_confirmed_bottlenecks(
    resolved: list[str],
    primary_bottleneck: str | None,
    meta: SessionMetadata,
) -> int:
    count = meta.confirmed_bottleneck_count
    if "planning_delay" in resolved or "bottleneck" in resolved:
        count = max(count, 1)
    if primary_bottleneck and primary_bottleneck != "unknown":
        count = max(count, 1)
    if "planning_delay" in resolved and primary_bottleneck:
        count = max(count, 2)
    return count


def _overall_confidence(
    meta: SessionMetadata,
    snapshot: HypothesisSnapshot,
    message: str,
    history: list[str],
    resolved: list[str],
) -> float:
    turn_score = compute_evidence_score(
        meta, snapshot, message, history, resolved=resolved
    )
    return merge_evidence_peak(meta.evidence_score_peak, turn_score)


def _diagnose_depth(meta: SessionMetadata, stage: str) -> DiagnoseDepth:
    if meta.message_count <= 6 or stage in ("DISCOVERY", "CONSTRAINT_MAPPING"):
        return "early"
    if meta.message_count <= 12 or stage == "BOTTLENECK_ISOLATION":
        return "mid"
    return "late"


def _rank_bottleneck_hypotheses(
    blob: str,
    primary_bottleneck: str | None,
) -> dict[str, float]:
    """Candidate bottleneck hypotheses with confidence scores."""
    scores: dict[str, float] = {}
    if "compliance" in blob and "manual" in blob:
        scores["manual_compliance_review"] = 0.72
    elif "compliance" in blob and any(
        p in blob for p in ("hours", "days", "review", "risk team", "move between")
    ):
        scores["manual_compliance_review"] = 0.61
        scores["manual_handoff"] = 0.58
        scores["prioritization_gap"] = 0.49
    if "backlog" in blob:
        scores["compliance_queue_backlog"] = max(scores.get("manual_compliance_review", 0.0), 0.68)
    if any(p in blob for p in ("automation failed", "poor adoption", "exception", "went back to email")):
        scores["document_collection_failures"] = 0.58
    if any(p in blob for p in ("underwriting", "analyst", "manual")) and "document" in blob:
        scores["underwriting_capacity"] = 0.45
    if any(p in blob for p in _PLANNING_EVIDENCE) or ("driver" in blob and "wait" in blob):
        scores["manual_planning"] = 0.75
    if primary_bottleneck and primary_bottleneck != "unknown":
        scores[primary_bottleneck] = max(scores.get(primary_bottleneck, 0.0), 0.7)
    return scores


def _question_candidate_keys(
    snapshot: HypothesisSnapshot,
    resolved: list[str],
    meta: SessionMetadata,
) -> list[str]:
    """Ordered diagnostic question keys — highest information gain first."""
    if snapshot.hypothesis_status == "conflicted":
        return ["business_clarification"]

    facts_blob = " ".join(snapshot.confirmed_facts).lower()
    has_logistics = (
        snapshot.active_business_vertical == "logistics"
        or "logistics" in facts_blob
    )
    has_financial = (
        snapshot.active_business_vertical == "financial_services"
        or any(k in facts_blob for k in ("lending", "loan", "compliance", "underwriting"))
    )
    planning_known = (
        "planning_delay" in resolved
        or "planning is manual" in facts_blob
        or snapshot.primary_bottleneck in ("dispatch", "planning", "throughput")
    )
    driver_wait_known = "driver" in facts_blob or "wait" in facts_blob

    keys: list[str] = []

    if has_financial:
        facts_blob = " ".join(snapshot.confirmed_facts).lower()
        if "backlog_size" in resolved and "backlog_composition" not in resolved:
            keys.append("backlog_composition")
        if "automation_history" in resolved and "exception_types" not in resolved:
            keys.append("exception_types")
        if "compliance_prioritization" not in resolved and (
            "compliance" in facts_blob or snapshot.primary_bottleneck == "approvals"
        ):
            keys.append("compliance_prioritization")
        if "underwriting_process" not in resolved:
            keys.append("underwriting_process")

    if has_logistics and planning_known and driver_wait_known:
        keys.append("assignment_logic")
    if has_logistics and planning_known:
        keys.append("routing_constraints")
    if has_logistics and "scale" in resolved:
        keys.append("planning_tools")
    if "business_context" in snapshot.unresolved_unknowns:
        keys.append("business_context")
    if "workflow_steps" not in resolved and has_logistics:
        keys.append("workflow_steps")

    signals = get_signal_registry()
    for unknown in snapshot.unresolved_unknowns:
        if unknown in signals.unknown_to_question and unknown not in keys:
            keys.append(unknown)

    return list(dict.fromkeys(keys))


def _pick_next_question_key(
    candidate_keys: list[str],
    meta: SessionMetadata,
    *,
    snapshot: HypothesisSnapshot | None = None,
) -> str | None:
    answered = set(meta.answered_question_keys)
    open_set = set(meta.open_question_keys)
    skipped = set(meta.skipped_question_keys)
    timeout = meta.consecutive_question_turns >= 2
    known: set[str] = set()
    if snapshot is not None:
        known = known_discovery_topics(snapshot, meta)

    for key in candidate_keys:
        if key in answered or key in known or key in skipped:
            continue
        if key in open_set and not timeout:
            continue
        return key
    return None


def _question_text_for_key(key: str) -> str | None:
    if key in INFORMATION_GAIN_QUESTIONS:
        return INFORMATION_GAIN_QUESTIONS[key]
    signals = get_signal_registry()
    return signals.unknown_to_question.get(key)


def select_required_question(
    snapshot: HypothesisSnapshot,
    resolved: list[str],
    meta: SessionMetadata,
) -> str | None:
    if snapshot.hypothesis_status == "conflicted":
        return snapshot.conflict_detail or INFORMATION_GAIN_QUESTIONS["business_clarification"]

    key = _pick_next_question_key(
        _question_candidate_keys(snapshot, resolved, meta),
        meta,
        snapshot=snapshot,
    )
    question: str | None = None
    if key:
        question = _question_text_for_key(key)
    validated, _violations = validate_follow_up_question(question, snapshot, meta)
    if (
        validated
        and question
        and validated.strip() == question.strip()
    ):
        return validated
    if question and key and key in INFORMATION_GAIN_QUESTIONS:
        return question
    if validated:
        return validated
    from app.advisor.pipeline.evidence_extractor import extract_fact_graph
    from app.advisor.pipeline.progress_questions import select_best_progress_question

    fg = extract_fact_graph(meta, snapshot)
    grounded, _ = select_best_progress_question(
        fg, meta=meta, message=meta.goals or meta.pain_point or ""
    )
    return grounded


def update_hypothesis_snapshot(
    meta: SessionMetadata,
    message: str,
    history: list[str],
    *,
    is_conflicted: bool = False,
    conflict_detail: str | None = None,
) -> HypothesisSnapshot:
    """Thin adapter — projects BusinessSystemsState into HypothesisSnapshot."""
    from app.advisor.pipeline.business_systems_engine import run_business_systems_reasoning

    base = HypothesisSnapshot(signals_version=ACTIVE_SIGNALS_VERSION)
    bss = run_business_systems_reasoning(meta, base, message=message, history=history)
    blob = _blob(meta, message, history)

    business_model = _detect_business_model(meta, message, history)
    if bss.business_model.revenue_mechanisms:
        rm = bss.business_model.revenue_mechanisms[0]
        if rm == "subscription":
            business_model = "saas"
        elif rm == "unit_sales":
            business_model = "local_retail"
        elif rm == "project_fee":
            business_model = "service"

    vertical = _detect_business_vertical(message, history, meta)
    if not vertical and bss.business_context.inferred_industries:
        vertical = bss.business_context.inferred_industries[0].label

    primary_bottleneck: str | None = None
    if any(p in blob for p in _PLANNING_EVIDENCE) or ("driver" in blob and "wait" in blob):
        primary_bottleneck = "planning"
    elif bss.confidence.root_causes:
        label = bss.confidence.root_causes[0].label[:60]
        primary_bottleneck = label.replace(" bottleneck", "").replace("_", " ")
    elif bss.value_chain.active and bss.value_chain.breakdown_stage:
        stage = bss.value_chain.breakdown_stage
        if stage == "scheduling":
            primary_bottleneck = "planning"
        else:
            primary_bottleneck = stage.replace("_", " ")
    elif bss.capability_gaps:
        gap = bss.capability_gaps[0]
        primary_bottleneck = gap.specialization_label or gap.universal_id.replace("_", " ")

    scale_indicators = _detect_scale_indicators(message, history)
    system_context = _detect_system_context(message, history)
    confirmed_facts = _extract_confirmed_facts(message, history)
    if not confirmed_facts:
        confirmed_facts = [f.label for f in bss.causal_graph.nodes if f.kind == "outcome"][:5]

    resolved, unresolved = _resolve_unknowns(
        meta, message, history, scale_indicators, primary_bottleneck
    )
    confidence_scores = _rank_bottleneck_hypotheses(blob, primary_bottleneck)
    for rc in bss.confidence.root_causes[:4]:
        confidence_scores[rc.cause_id] = rc.confidence

    stage_map = {
        "DISCOVERY": "DISCOVERY",
        "DIAGNOSIS": "CONSTRAINT_MAPPING",
        "VALIDATION": "BOTTLENECK_ISOLATION",
        "RECOMMENDATION_READINESS": "HYPOTHESIS_VALIDATION",
        "SOLUTION": "SOLUTION_ALIGNMENT",
    }
    conv_stage = stage_map.get(bss.reasoning_stage, "DISCOVERY")

    overall = _overall_confidence(meta, base, message, history, resolved)
    if bss.pattern_matches:
        overall = max(overall, bss.pattern_matches[0].confidence)
    if bss.confidence.top_confidence > 0:
        overall = max(overall, bss.confidence.top_confidence)
    if scale_indicators:
        overall = max(overall, 0.82)
    elif primary_bottleneck and any(p in blob for p in _PLANNING_EVIDENCE):
        overall = max(overall, 0.80)

    if overall >= 0.80 and primary_bottleneck:
        conv_stage = "HYPOTHESIS_VALIDATION"  # type: ignore[assignment]

    interim = HypothesisSnapshot(
        signals_version=ACTIVE_SIGNALS_VERSION,
        active_business_vertical=vertical,
        primary_bottleneck=primary_bottleneck,
        confirmed_facts=confirmed_facts,
        resolved_unknowns=resolved,
        unresolved_unknowns=unresolved,
        conversation_stage=conv_stage,  # type: ignore[arg-type]
        overall_confidence=overall,
        hypothesis_status="conflicted" if is_conflicted else "active",
        conflict_detail=conflict_detail,
    )
    from app.advisor.pipeline.discovery_engine import run_discovery, select_discovery_question
    from app.advisor.pipeline.progress_questions import (
        has_high_signal_progress,
        is_generic_template_question,
        select_best_progress_question,
    )
    from app.advisor.pipeline.question_value import build_cash_flow_evidence_question

    discovery_state = run_discovery(meta, interim, message=message, history=history)
    disc_q, disc_gain = select_discovery_question(discovery_state)
    progress_q, progress_score = select_best_progress_question(
        discovery_state.fact_graph, bss=bss, discovery=discovery_state, meta=meta, message=message
    )
    cash_q = build_cash_flow_evidence_question(
        meta, interim, message=message, history=history
    )
    high_signal = has_high_signal_progress(discovery_state.fact_graph)
    catalog_q = select_required_question(interim, resolved, meta)

    if high_signal and progress_q and progress_score >= 0.65:
        required_question = progress_q
    elif catalog_q and not is_generic_template_question(catalog_q):
        required_question = catalog_q
    elif bss.recommended_question and not is_generic_template_question(bss.recommended_question):
        required_question = bss.recommended_question
    elif cash_q:
        required_question = cash_q
    elif disc_q and disc_gain >= 0.55:
        required_question = disc_q
    elif progress_q:
        required_question = progress_q
    else:
        required_question = bss.recommended_question or catalog_q or progress_q

    from app.advisor.pipeline.question_ledger import filter_questions_by_ledger
    from app.advisor.pipeline.progress_questions import is_generic_template_question

    resolved_qs = filter_questions_by_ledger(
        [required_question, progress_q, catalog_q, bss.recommended_question, disc_q],
        meta,
    )
    resolved_qs = [q for q in resolved_qs if not is_generic_template_question(q)]
    if resolved_qs:
        required_question = resolved_qs[0]

    confirmed_count = _count_confirmed_bottlenecks(resolved, primary_bottleneck, meta)
    solutioning_ok = (
        confirmed_count >= 1
        and overall >= HYPOTHESIS_EVIDENCE_THRESHOLD
        and conv_stage in ("HYPOTHESIS_VALIDATION", "SOLUTION_ALIGNMENT")
    )

    snapshot = HypothesisSnapshot(
        signals_version=ACTIVE_SIGNALS_VERSION,
        business_model=business_model,
        active_business_vertical=vertical,
        primary_bottleneck=primary_bottleneck,
        system_context=system_context,
        scale_indicators=scale_indicators,
        confirmed_facts=confirmed_facts,
        resolved_unknowns=resolved,
        unresolved_unknowns=unresolved,
        conversation_stage=conv_stage,  # type: ignore[arg-type]
        confidence_scores=confidence_scores,
        overall_confidence=overall,
        confirmed_bottleneck_count=confirmed_count,
        hypothesis_status="conflicted" if is_conflicted else "active",
        conflict_detail=conflict_detail,
        diagnose_depth=_diagnose_depth(meta, conv_stage),
        solutioning_allowed=solutioning_ok,
        required_question=required_question,
    )
    return snapshot
