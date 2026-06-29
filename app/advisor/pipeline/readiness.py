"""L5 — readiness assessment."""

from __future__ import annotations

from app.advisor.orchestrator.tool_gating import compute_rule_based_readiness
from app.advisor.types import ReadinessFlags, SessionMetadata


def assess_readiness(meta: SessionMetadata) -> ReadinessFlags:
    """Deterministic readiness on critical path."""
    return compute_rule_based_readiness(meta)
