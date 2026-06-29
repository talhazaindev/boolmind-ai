"""Conversation context graph — structured live model of user business state."""

from __future__ import annotations

import re

from app.advisor.orchestrator.inference_builder import build_derived_inferences
from app.advisor.orchestrator.problem_dimension import detect_problem_dimension
from app.advisor.pipeline.volume_patterns import extract_backlog_count, extract_volume_indicators
from app.advisor.types import (
    ConversationContextGraph,
    HypothesisSnapshot,
    MetricValue,
    PriorAttempt,
    SessionMetadata,
    StageState,
    UniversalWorkflowStage,
)

_TURNAROUND_RE = re.compile(
    r"(?:from|went from)\s+(\d+)\s+days?\s+to\s+(?:nearly\s+)?(\d+)\s+days?",
    re.I,
)
_TURNAROUND_SINGLE_RE = re.compile(
    r"(\d+)\s+days?\s+(?:on average|average|turnaround|approval)",
    re.I,
)

_SYSTEM_KEYWORDS: dict[str, str] = {
    "spreadsheet": "spreadsheet",
    "excel": "spreadsheet",
    "email": "email",
    "erp": "erp",
    "sap": "erp",
    "salesforce": "crm",
    "crm": "crm",
    "los": "loan_origination_system",
    "origination system": "loan_origination_system",
    "tms": "tms",
}


def _parse_volume_number(text: str) -> float | None:
    m = re.search(r"(\d[\d,]*)", text.replace(",", ""))
    return float(m.group(1)) if m else None


def _extract_quote_hooks(message: str, max_hooks: int = 3) -> list[str]:
    hooks: list[str] = []
    lower = message.lower()
    patterns = (
        r"went back to email",
        r"missed exceptions",
        r"poor adoption",
        r"manual compliance",
        r"backlog of (?:about )?\d+",
        r"\d+\s+loan applications",
        r"driver wait",
        r"spreadsheet",
    )
    for pat in patterns:
        m = re.search(pat, lower, re.I)
        if m:
            hooks.append(m.group(0).strip())
    if len(hooks) < max_hooks:
        for sentence in re.split(r"[.!?]\s+", message.strip()):
            s = sentence.strip()
            if 20 <= len(s) <= 120 and any(
                k in s.lower()
                for k in ("manual", "delay", "backlog", "automation", "compliance")
            ):
                hooks.append(s[:100])
    return list(dict.fromkeys(hooks))[:max_hooks]


def _regex_extract_workflow_stages(blob: str) -> dict[str, StageState]:
    stages: dict[str, StageState] = {}
    if any(k in blob for k in ("intake", "application received", "order received")):
        stages["intake"] = StageState(mode="digital" if "digital" in blob else None, confidence=0.7)
    if any(k in blob for k in ("document", "gather", "verify", "plan", "route")):
        stages["preparation"] = StageState(mode="manual" if "manual" in blob else None, confidence=0.75)
    if any(k in blob for k in ("underwriting", "analyst", "dispatch", "analysis")):
        stages["execution"] = StageState(mode="manual" if "manual" in blob else None, confidence=0.75)
    if any(k in blob for k in ("compliance", "qc", "inspection", "review queue")):
        stages["quality_gate"] = StageState(mode="manual", confidence=0.8)
    if any(k in blob for k in ("approval", "delivery", "decision")):
        stages["delivery"] = StageState(confidence=0.65)
    if any(k in blob for k in ("exception", "revert", "went back", "missing doc")):
        stages["exception_loop"] = StageState(mode="active", confidence=0.7)
    return stages


def _regex_extract_metrics(blob: str, message: str) -> dict[str, MetricValue]:
    metrics: dict[str, MetricValue] = {}
    for vol in extract_volume_indicators(blob):
        n = _parse_volume_number(vol)
        if n:
            metrics["daily_volume"] = MetricValue(value=n, unit="per_day", confidence=0.95)
            break
    backlog_phrase = extract_backlog_count(blob)
    if backlog_phrase:
        n = _parse_volume_number(backlog_phrase)
        if n:
            metrics["backlog"] = MetricValue(value=n, unit="applications", confidence=0.92)
    m = _TURNAROUND_RE.search(message)
    if m:
        metrics["turnaround_days_baseline"] = MetricValue(value=float(m.group(1)), unit="days")
        metrics["turnaround_days_current"] = MetricValue(value=float(m.group(2)), unit="days")
    else:
        m2 = _TURNAROUND_SINGLE_RE.search(blob)
        if m2:
            metrics["turnaround_days_current"] = MetricValue(value=float(m2.group(1)), unit="days")
    return metrics


def _regex_extract_prior_attempts(blob: str) -> list[PriorAttempt]:
    attempts: list[PriorAttempt] = []
    if "automat" in blob and any(
        p in blob for p in ("fail", "poor adoption", "exception", "revert", "went back")
    ):
        reason = "missed exceptions" if "exception" in blob else "poor adoption"
        attempts.append(
            PriorAttempt(
                what="document collection automation",
                outcome="failed",
                reason=reason,
            )
        )
    return attempts


def merge_llm_extract(
    graph: ConversationContextGraph,
    llm_data: dict | None,
) -> ConversationContextGraph:
    """Merge LLM JSON extract; regex wins on numeric conflicts."""
    if not llm_data:
        return graph
    entities = llm_data.get("entities") or {}
    for key, val in entities.items():
        if key not in graph.metrics and val is not None:
            graph.metrics[key] = MetricValue(value=val, source="llm", confidence=0.75)
    for stage, mode in (llm_data.get("workflow_signals") or {}).items():
        if stage not in graph.workflow_stages:
            graph.workflow_stages[stage] = StageState(mode=str(mode), confidence=0.7)
    for item in llm_data.get("prior_attempts") or []:
        if isinstance(item, dict):
            graph.prior_attempts.append(
                PriorAttempt(
                    what=str(item.get("what", "")),
                    outcome=str(item.get("outcome", "")),
                    reason=item.get("reason"),
                )
            )
    hooks = llm_data.get("user_quote_hooks") or []
    graph.user_quote_hooks = list(
        dict.fromkeys([*graph.user_quote_hooks, *[str(h) for h in hooks]])
    )[:5]
    stage = llm_data.get("inferred_bottleneck_stage")
    if stage and graph.universal_stage == "unknown":
        graph.universal_stage = _coerce_universal_stage(str(stage))
    return graph


def _coerce_universal_stage(stage: str) -> UniversalWorkflowStage:
    normalized = stage.lower().replace(" ", "_").replace("-", "_")
    valid: tuple[UniversalWorkflowStage, ...] = (
        "intake",
        "preparation",
        "execution",
        "quality_gate",
        "delivery",
        "exception_loop",
        "unknown",
    )
    if normalized in valid:
        return normalized  # type: ignore[return-value]
    aliases = {
        "compliance": "quality_gate",
        "underwriting": "execution",
        "document_collection": "preparation",
        "planning": "preparation",
        "dispatch": "execution",
    }
    return aliases.get(normalized, "unknown")  # type: ignore[return-value]


def graph_from_meta(meta: SessionMetadata) -> ConversationContextGraph | None:
    if not meta.context_graph:
        return None
    try:
        return ConversationContextGraph.model_validate(meta.context_graph)
    except Exception:
        return None


def build_context_graph(
    meta: SessionMetadata,
    message: str,
    history: list[str],
    snapshot: HypothesisSnapshot,
    *,
    llm_data: dict | None = None,
) -> ConversationContextGraph:
    """Build or extend context graph from regex + optional LLM merge."""
    prior = graph_from_meta(meta)
    blob = " ".join([message, *history, meta.industry or "", meta.pain_point or ""]).lower()

    graph = prior or ConversationContextGraph()
    if snapshot.active_business_vertical:
        graph.industry = snapshot.active_business_vertical
    elif meta.industry:
        graph.industry = meta.industry

    graph.problem_dimension = detect_problem_dimension(meta, message, history)
    graph.workflow_stages.update(_regex_extract_workflow_stages(blob))
    for key, val in _regex_extract_metrics(blob, message).items():
        graph.metrics[key] = val
    graph.pain_points = list(
        dict.fromkeys([*graph.pain_points, *(snapshot.confirmed_facts[:5])])
    )[:8]
    graph.prior_attempts.extend(_regex_extract_prior_attempts(blob))
    graph.prior_attempts = list(
        {a.what: a for a in graph.prior_attempts}.values()
    )
    for kw, system in _SYSTEM_KEYWORDS.items():
        if kw in blob and system not in graph.systems:
            graph.systems.append(system)
    graph.user_quote_hooks = list(
        dict.fromkeys([*graph.user_quote_hooks, *_extract_quote_hooks(message)])
    )[:5]

    graph = merge_llm_extract(graph, llm_data)
    build_derived_inferences(graph)

    if graph.universal_stage == "unknown":
        from app.advisor.orchestrator.diagnostic_trees import locate_universal_stage

        graph.universal_stage = locate_universal_stage(graph, blob)

    graph.active_thread = meta.active_thread
    graph.thread_depth = meta.active_thread_depth
    return graph


def persist_graph(meta: SessionMetadata, graph: ConversationContextGraph) -> SessionMetadata:
    updated = meta.model_copy(deep=True)
    updated.context_graph = graph.model_dump()
    updated.active_thread = graph.active_thread
    updated.active_thread_depth = graph.thread_depth
    if graph.problem_dimension:
        updated.problem_dimension = graph.problem_dimension
    return updated
