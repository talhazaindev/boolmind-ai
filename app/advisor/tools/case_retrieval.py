"""
Case evidence retrieval for matched archetypes.

Called during pre-flight tool execution when an archetype is matched
and the conversation is in mid/late patience phase.

Returns up to 2 case snippets most relevant to the matched archetype + vertical.
Injects into the GROUNDING prompt block alongside RAG content.

Fallback: if Pinecone times out or returns empty, returns [] silently.
"""

from __future__ import annotations

import asyncio
from typing import Any

from app.advisor.knowledge.ontology_schema import BusinessArchetype
from app.advisor.rag.embed import embed_query
from app.advisor.rag.namespaces import CASE_EVIDENCE_NAMESPACE
from app.advisor.rag.pinecone_index import get_pinecone_index

_RETRIEVAL_TIMEOUT = 1.5  # seconds


async def retrieve_case_evidence(
    matched_archetypes: list[BusinessArchetype],
    vertical: str | None = None,
    top_k: int = 2,
) -> list[dict[str, str]]:
    """
    Retrieve case evidence snippets for the matched archetypes.

    Returns:
        List of dicts with keys: case_text, outcome_frame, archetype_name.
        Empty list on timeout or error.
    """
    if not matched_archetypes:
        return []

    primary = matched_archetypes[0]
    query_text = f"{primary.name} {primary.root_cause} {' '.join(primary.symptoms[:3])}"
    if vertical:
        query_text += f" {vertical}"

    try:
        vec = await asyncio.wait_for(
            asyncio.to_thread(embed_query, query_text),
            timeout=_RETRIEVAL_TIMEOUT,
        )
        index = get_pinecone_index()
        result: Any = await asyncio.to_thread(
            index.query,
            vector=vec,
            top_k=top_k,
            namespace=CASE_EVIDENCE_NAMESPACE,
            include_metadata=True,
            filter={"archetype_id": {"$in": [a.id for a in matched_archetypes]}},
        )
        snippets: list[dict[str, str]] = []
        for match in result.matches or []:
            meta = match.metadata or {}
            snippets.append(
                {
                    "case_text": str(meta.get("case_text", "")),
                    "outcome_frame": str(meta.get("outcome_frame", "")),
                    "archetype_name": str(meta.get("archetype_name", "")),
                }
            )
        return snippets
    except Exception:
        return []
