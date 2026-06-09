"""Embedding providers for RAG (local BGE or OpenAI)."""

from __future__ import annotations

import logging
from typing import Literal

from app.core.config import settings

logger = logging.getLogger(__name__)

BATCH_SIZE = 64
_bge_model = None

EmbeddingProvider = Literal["local", "openai"]


def _get_bge_model():
    global _bge_model
    if _bge_model is None:
        from sentence_transformers import SentenceTransformer

        logger.info("Loading local embedding model: %s", settings.embedding_model)
        _bge_model = SentenceTransformer(settings.embedding_model)
    return _bge_model


def _embed_local_passages(texts: list[str]) -> list[list[float]]:
    model = _get_bge_model()
    prefixed = [f"passage: {t}" if not t.startswith("passage:") else t for t in texts]
    vectors = model.encode(
        prefixed,
        batch_size=BATCH_SIZE,
        normalize_embeddings=True,
        show_progress_bar=settings.debug,
    )
    return [v.tolist() for v in vectors]


def _embed_local_query(query: str) -> list[float]:
    model = _get_bge_model()
    text = query if query.startswith("query:") else f"query: {query}"
    vector = model.encode([text], normalize_embeddings=True)[0]
    return vector.tolist()


def _embed_openai(texts: list[str]) -> list[list[float]]:
    from openai import OpenAI

    if not settings.openai_configured:
        raise RuntimeError("OPENAI_API_KEY is not configured")
    client = OpenAI(api_key=settings.openai_api_key)
    all_embeddings: list[list[float]] = []
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        response = client.embeddings.create(
            model=settings.openai_embedding_model,
            input=batch,
        )
        all_embeddings.extend([item.embedding for item in response.data])
    return all_embeddings


def get_embedding_dimension() -> int:
    return settings.embedding_dimension


def embed_texts(texts: list[str], *, for_query: bool = False) -> list[list[float]]:
    """Embed document chunks (passages) or queries depending on provider."""
    if not texts:
        return []
    provider = settings.embedding_provider
    if provider == "openai":
        return _embed_openai(texts)
    if for_query and len(texts) == 1:
        return [_embed_local_query(texts[0])]
    return _embed_local_passages(texts)


def embed_query(query: str) -> list[float]:
    if settings.embedding_provider == "openai":
        return embed_texts([query], for_query=True)[0]
    return _embed_local_query(query)
