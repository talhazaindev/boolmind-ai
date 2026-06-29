#!/usr/bin/env python3
"""
One-time script to embed and upsert case evidence into Pinecone.

Run with: python scripts/seed_case_evidence.py

Uses the case_hook field from each archetype as the primary evidence text,
supplemented with structured metadata for filtered retrieval.

Each Pinecone vector has metadata:
  archetype_id: str
  service_tags: list[str]
  vertical_tags: list[str]
  it_lever: str
  outcome_frame: str
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pinecone import Pinecone

from app.advisor.knowledge.ontology_loader import _load_archetypes
from app.advisor.rag.embed import embed_query
from app.advisor.rag.namespaces import CASE_EVIDENCE_NAMESPACE
from app.advisor.rag.pinecone_index import get_pinecone_index, resolve_pinecone_host
from app.core.config import settings

_BATCH_SIZE = 100


async def seed() -> int:
    if not settings.pinecone_configured:
        print("ERROR: PINECONE_* required in .env")
        return 1
    if not settings.embeddings_configured:
        print("ERROR: embeddings not configured (EMBEDDING_PROVIDER=local or OPENAI_API_KEY)")
        return 1

    pc = Pinecone(api_key=settings.pinecone_api_key)
    try:
        host = resolve_pinecone_host(pc)
        print(f"Pinecone index: {settings.pinecone_index_name} @ {host}")
    except Exception as e:
        print(f"ERROR: Cannot resolve Pinecone index: {e}")
        return 1

    archetypes = _load_archetypes()
    index = get_pinecone_index(pc)

    try:
        index.delete(delete_all=True, namespace=CASE_EVIDENCE_NAMESPACE)
        print(f"Cleared namespace: {CASE_EVIDENCE_NAMESPACE}")
    except Exception as e:
        err = str(e).lower()
        if "not found" not in err and "404" not in err:
            print(f"Warning clearing {CASE_EVIDENCE_NAMESPACE}: {e}")

    vectors: list[dict[str, object]] = []
    for arch in archetypes:
        if not arch.case_hook:
            continue
        text = (
            f"{arch.name}: {arch.case_hook} | Root cause: {arch.root_cause} "
            f"| Solution: {arch.it_lever}"
        )
        vec = await asyncio.to_thread(embed_query, text)
        vectors.append(
            {
                "id": f"case_{arch.id}",
                "values": vec,
                "metadata": {
                    "archetype_id": arch.id,
                    "archetype_name": arch.name,
                    "case_text": arch.case_hook,
                    "outcome_frame": arch.outcome_frame,
                    "service_tags": arch.boolmind_services,
                    "vertical_tags": arch.vertical_bias,
                    "it_lever": arch.it_lever,
                    "priority": arch.priority,
                },
            }
        )

    upserted = 0
    for i in range(0, len(vectors), _BATCH_SIZE):
        batch = vectors[i : i + _BATCH_SIZE]
        index.upsert(vectors=batch, namespace=CASE_EVIDENCE_NAMESPACE)
        upserted += len(batch)

    print(
        f"Seeded {upserted} case evidence vectors into namespace "
        f"'{CASE_EVIDENCE_NAMESPACE}'"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(seed()))
