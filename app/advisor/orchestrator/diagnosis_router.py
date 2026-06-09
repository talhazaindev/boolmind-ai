"""Route to the correct diagnostic framework based on problem dimension."""

from __future__ import annotations

from app.advisor.orchestrator.operations_diagnosis import (
    build_operations_diagnosis_block,
    should_diagnose_operations,
)
from app.advisor.orchestrator.problem_dimension import detect_problem_dimension
from app.advisor.orchestrator.profitability_diagnosis import (
    build_profitability_diagnosis_block,
    should_diagnose_profitability,
)
from app.advisor.orchestrator.strategy_diagnosis import (
    build_diagnosis_block,
    should_insight_before_tactics,
)
from app.advisor.orchestrator.workforce_diagnosis import (
    build_workforce_diagnosis_block,
    should_diagnose_workforce,
)
from app.advisor.types import SessionMetadata


def should_diagnose(
    meta: SessionMetadata,
    message: str = "",
    history: list[str] | None = None,
) -> bool:
    return (
        should_diagnose_workforce(meta, message, history)
        or should_diagnose_profitability(meta, message, history)
        or should_diagnose_operations(meta, message, history)
        or should_insight_before_tactics(meta, message, history)
    )


def build_diagnosis_block_for_dimension(
    meta: SessionMetadata,
    message: str = "",
    history: list[str] | None = None,
) -> str:
    dimension = detect_problem_dimension(meta, message, history)
    if dimension == "workforce" or should_diagnose_workforce(meta, message, history):
        return build_workforce_diagnosis_block(meta, message, history)
    if dimension == "profitability" or should_diagnose_profitability(meta, message, history):
        return build_profitability_diagnosis_block(meta, message, history)
    if dimension == "throughput" or should_diagnose_operations(meta, message, history):
        return build_operations_diagnosis_block(meta, message, history)
    return build_diagnosis_block(meta, message, history)
