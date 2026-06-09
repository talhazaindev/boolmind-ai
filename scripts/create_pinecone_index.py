#!/usr/bin/env python3
"""Create a Pinecone serverless index for local BGE embeddings (384 dimensions)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pinecone import Pinecone, ServerlessSpec

from app.core.config import settings


def main() -> int:
    parser = argparse.ArgumentParser(description="Create Pinecone index for BGE embeddings")
    parser.add_argument("--name", default=None, help="Index name (default: PINECONE_INDEX_NAME)")
    parser.add_argument("--dimension", type=int, default=None, help="Vector dimension (default: EMBEDDING_DIMENSION)")
    parser.add_argument("--region", default="us-east-1", help="AWS region for serverless index")
    parser.add_argument("--cloud", default="aws", choices=["aws", "gcp", "azure"])
    args = parser.parse_args()

    if not settings.pinecone_api_key:
        print("ERROR: PINECONE_API_KEY required in .env")
        return 1

    name = args.name or settings.pinecone_index_name
    dimension = args.dimension or settings.embedding_dimension

    pc = Pinecone(api_key=settings.pinecone_api_key)
    existing = [i.name for i in pc.list_indexes()]

    if name in existing:
        desc = pc.describe_index(name)
        print(f"Index '{name}' already exists.")
        print(f"  dimension: {desc.dimension}")
        print(f"  metric: {desc.metric}")
        if desc.dimension != dimension:
            print(
                f"  WARNING: index dimension is {desc.dimension} but EMBEDDING_DIMENSION={dimension}. "
                "Create a new index or fix .env."
            )
            return 1
        host = pc.describe_index(name).host
        print(f"  host: https://{host}")
        print("\nSet in .env:")
        print(f"  PINECONE_INDEX_NAME={name}")
        print(f"  PINECONE_HOST=https://{host}")
        return 0

    print(f"Creating index '{name}' (dimension={dimension}, metric=cosine)...")
    pc.create_index(
        name=name,
        dimension=dimension,
        metric="cosine",
        spec=ServerlessSpec(cloud=args.cloud, region=args.region),
    )
    desc = pc.describe_index(name)
    host = desc.host
    print(f"Created. Host: https://{host}")
    print("\nAdd to .env:")
    print(f"  PINECONE_INDEX_NAME={name}")
    print(f"  PINECONE_HOST=https://{host}")
    print(f"  EMBEDDING_PROVIDER=local")
    print(f"  EMBEDDING_DIMENSION={dimension}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
