#!/usr/bin/env python3
"""Verify Pinecone API key, index name, and host DNS resolution."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pinecone import Pinecone

from app.advisor.rag.pinecone_index import get_pinecone_index, resolve_pinecone_host, verify_host_resolves
from app.core.config import settings


def main() -> int:
    if not settings.pinecone_api_key:
        print("FAIL: PINECONE_API_KEY missing")
        return 1
    print(f"Index name: {settings.pinecone_index_name}")
    print(f"Embedding dim (env): {settings.embedding_dimension}")

    try:
        pc = Pinecone(api_key=settings.pinecone_api_key)
        desc = pc.describe_index(settings.pinecone_index_name)
        print(f"API dimension: {desc.dimension}")
        print(f"API metric: {desc.metric}")
        host = resolve_pinecone_host(pc)
        print(f"Resolved host: {host}")
        verify_host_resolves(host)
        print("DNS: OK")
        idx = get_pinecone_index(pc)
        stats = idx.describe_index_stats()
        print(f"Index stats: {stats}")
        print("\nOK — Pinecone is reachable.")
        return 0
    except Exception as e:
        print(f"\nFAIL: {e}")
        print("\nFix:")
        print("  1. python scripts/create_pinecone_index.py")
        print("  2. Set PINECONE_INDEX_NAME to match the new 384-dim index")
        print("  3. Remove or fix PINECONE_HOST (optional — host is resolved from API)")
        print("  4. Check internet / VPN / firewall for *.pinecone.io")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
