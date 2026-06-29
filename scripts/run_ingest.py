#!/usr/bin/env python3
"""Ingest knowledge-base markdown into Pinecone namespaces."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Project root on path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pinecone import Pinecone

from app.advisor.rag.chunk import chunk_markdown_file
from app.advisor.rag.embed import embed_texts
from app.advisor.rag.pinecone_index import get_pinecone_index, resolve_pinecone_host
from app.core.config import settings

NAMESPACE_MAP = {
    "retify": "products/retify",
    "ecg": "products/ecg",
    "legal": "products/legal",
    "forecasting": "products/forecasting",
    "capabilities": "capabilities",
    "business_intelligence": "business-intelligence",
    "general": "general",
    "architecture": "architecture-mappings",
}


def ingest_namespace(pc: Pinecone, namespace: str, source_dir: Path) -> tuple[int, int]:
    if not source_dir.exists():
        print(f"  skip {namespace}: {source_dir} not found")
        return 0, 0

    chunks = []
    for path in sorted(source_dir.rglob("*.md")):
        file_chunks = chunk_markdown_file(path, namespace)
        chunks.extend(file_chunks)
        print(f"  {path.name}: {len(file_chunks)} chunks")

    if not chunks:
        return 0, 0

    index = get_pinecone_index(pc)

    try:
        index.delete(delete_all=True, namespace=namespace)
        print(f"  cleared namespace: {namespace}")
    except Exception as e:
        err = str(e).lower()
        if "not found" in err or "404" in err:
            print(f"  namespace {namespace} is new (nothing to clear)")
        else:
            print(f"  warning clearing {namespace}: {e}")

    texts = [c.text for c in chunks]
    vectors = embed_texts(texts)
    batch_size = 100
    upserted = 0
    for i in range(0, len(chunks), batch_size):
        batch_chunks = chunks[i : i + batch_size]
        batch_vectors = vectors[i : i + batch_size]
        records = []
        for j, (chunk, vec) in enumerate(zip(batch_chunks, batch_vectors)):
            vid = f"{namespace}-{chunk.source_doc}-{chunk.chunk_index}-{i + j}"
            records.append(
                {
                    "id": vid,
                    "values": vec,
                    "metadata": {
                        "text": chunk.text[:4000],
                        "source_doc": chunk.source_doc,
                        "section_title": chunk.section_title,
                        "product_name": chunk.product_name,
                        "namespace": namespace,
                        "last_updated": chunk.last_updated,
                        "chunk_index": chunk.chunk_index,
                    },
                }
            )
        index.upsert(vectors=records, namespace=namespace)
        upserted += len(records)
    return len(chunks), upserted


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest knowledge base into Pinecone")
    parser.add_argument(
        "--namespace",
        default="retify",
        help="Namespace to ingest (retify, ecg, legal, business_intelligence, general, all)",
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=None,
        help="Override source directory",
    )
    args = parser.parse_args()

    if not settings.pinecone_configured:
        print("ERROR: PINECONE_* required in .env")
        return 1
    if not settings.embeddings_configured:
        print("ERROR: embeddings not configured (EMBEDDING_PROVIDER=local or OPENAI_API_KEY)")
        return 1
    print(
        f"Embedding provider: {settings.embedding_provider} "
        f"(dim={settings.embedding_dimension})"
    )

    kb_root = settings.advisor_knowledge_base_path or ROOT / "knowledge-base"
    pc = Pinecone(api_key=settings.pinecone_api_key)
    try:
        host = resolve_pinecone_host(pc)
        print(f"Pinecone index: {settings.pinecone_index_name} @ {host}")
    except Exception as e:
        print(f"ERROR: Cannot resolve Pinecone index: {e}")
        return 1

    targets = list(NAMESPACE_MAP.keys()) if args.namespace == "all" else [args.namespace]
    total_chunks = 0
    total_vectors = 0

    for ns in targets:
        rel = NAMESPACE_MAP.get(ns, ns)
        source = args.source if args.source else kb_root / rel
        print(f"\nIngesting namespace={ns} from {source}")
        c, v = ingest_namespace(pc, ns, source)
        total_chunks += c
        total_vectors += v

    print(f"\nDone: {total_chunks} chunks, {total_vectors} vectors upserted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
