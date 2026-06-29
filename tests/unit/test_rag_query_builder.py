"""RAG query builder tests."""

from app.advisor.orchestrator.rag_query_builder import (
    INTENT_TO_RAG_QUERY,
    build_rag_spec,
    resolve_rag_intent,
)
from app.advisor.orchestrator.product_fit_mapper import map_product_fit
from app.advisor.types import SessionMetadata


def test_every_mapped_intent_has_template() -> None:
    for intent in INTENT_TO_RAG_QUERY:
        assert resolve_rag_intent(intent)


def test_build_rag_spec_deterministic() -> None:
    meta = SessionMetadata(pain_point="delays", industry="logistics")
    fit = map_product_fit(meta, "What is Retify?", [])
    a = build_rag_spec("general", "What is Retify?", meta, fit, None)
    b = build_rag_spec("general", "What is Retify?", meta, fit, None)
    assert a == b
    assert "query" in a and "namespace" in a
