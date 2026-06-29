"""Namespace-aware hybrid retrieval."""

from __future__ import annotations

import logging
import re
from typing import Any

from app.advisor.constants import RAG_SPARSE_INTERNAL_NOTE, RAG_SPARSE_SCORE_THRESHOLD
from app.advisor.rag.embed import embed_query
from app.advisor.rag.namespaces import resolve_namespace
from app.advisor.rag.pinecone_index import get_pinecone_index

logger = logging.getLogger(__name__)

CONTEXT_TOKEN_CAP = 1500


def _get_index():
    return get_pinecone_index()


def _keyword_boost(query: str, text: str) -> float:
    boost = 0.0
    words = set(re.findall(r"\b[A-Za-z0-9][A-Za-z0-9_-]{2,}\b", query.lower()))
    lower = text.lower()
    for w in words:
        if w in lower:
            boost += 0.1
    return min(boost, 0.5)


def _query_namespace(
    index: Any,
    query_vector: list[float],
    ns: str,
    per_ns: int,
    query: str,
) -> list[tuple[float, dict[str, Any]]]:
    out: list[tuple[float, dict[str, Any]]] = []
    try:
        result = index.query(
            vector=query_vector,
            top_k=per_ns,
            include_metadata=True,
            namespace=ns,
        )
    except Exception as e:
        logger.warning("Pinecone query failed for namespace %s: %s", ns, e)
        return out
    for match in result.matches or []:
        meta = match.metadata or {}
        text = meta.get("text", "")
        score = float(match.score or 0) + _keyword_boost(query, text)
        out.append((score, meta))
    return out


def _merge_candidates(
    candidates: list[tuple[float, dict[str, Any]]],
    top_k: int,
) -> str:
    seen: set[str] = set()
    unique: list[tuple[float, dict[str, Any]]] = []
    for score, meta in sorted(candidates, key=lambda x: x[0], reverse=True):
        key = f"{meta.get('source_doc')}:{meta.get('chunk_index')}"
        if key in seen:
            continue
        seen.add(key)
        unique.append((score, meta))

    parts: list[str] = []
    total_chars = 0
    for _, meta in unique[:top_k]:
        text = meta.get("text", "")
        source = meta.get("source_doc", "unknown")
        section = meta.get("section_title", "")
        product = meta.get("product_name", "")
        block = f"[Source: {source} — {section} | Product: {product}]\n{text}"
        if total_chars + len(block) > CONTEXT_TOKEN_CAP * 4:
            break
        parts.append(block)
        total_chars += len(block)

    return "\n---\n".join(parts) if parts else ""


def retrieve(
    query: str,
    namespace_arg: str,
    active_product: str | None,
    top_k: int = 3,
    product_fit: str | None = None,
) -> str:
    fit = product_fit or active_product
    namespaces = resolve_namespace(namespace_arg, active_product, product_fit=fit)

    index = _get_index()
    query_vector = embed_query(query)
    per_ns = top_k * 2
    candidates: list[tuple[float, dict[str, Any]]] = []

    for ns in namespaces:
        candidates.extend(_query_namespace(index, query_vector, ns, per_ns, query))

    top_score = max((s for s, _ in candidates), default=0.0)
    needs_capabilities = (
        fit == "custom_solutions"
        or (
            namespace_arg == "auto"
            and fit not in (None, "undecided")
            and top_score < RAG_SPARSE_SCORE_THRESHOLD
            and "capabilities" not in namespaces
        )
    )

    if needs_capabilities and "capabilities" not in namespaces:
        for ns in ("capabilities", "general"):
            if ns not in namespaces:
                candidates.extend(_query_namespace(index, query_vector, ns, per_ns, query))

    if len(candidates) < 2 and "general" not in namespaces:
        candidates.extend(_query_namespace(index, query_vector, "general", per_ns, query))

    result = _merge_candidates(candidates, top_k)
    return result if result else RAG_SPARSE_INTERNAL_NOTE
