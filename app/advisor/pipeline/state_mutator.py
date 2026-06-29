"""L4 — apply extracted facts after conflict check."""

from __future__ import annotations

from app.advisor.orchestrator.deterministic_extractors import deterministic_meta_extractors
from app.advisor.pipeline.types import ConflictReport
from app.advisor.types import SessionMetadata


def mutate_session_metadata(
    frozen_meta: SessionMetadata,
    message: str,
    history: list[str],
    conflict_report: ConflictReport,
) -> SessionMetadata:
    """Apply deterministic extractors; guard vertical fields when conflict blocks update."""
    extracted = deterministic_meta_extractors(message, history, frozen_meta)
    extracted.message_count = (frozen_meta.message_count or 0) + 1

    if conflict_report.blocks_vertical_update:
        extracted.industry = frozen_meta.industry
        extracted.active_business_vertical = frozen_meta.active_business_vertical

    extracted.conflict_hold = conflict_report.conflict_hold
    return extracted
