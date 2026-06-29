"""Loads the business problem ontology from YAML and provides
embedding-based archetype matching against user conversation context.

Matching strategy:
  1. Concatenate all symptom strings for each archetype into a single text.
  2. At startup, embed all archetype symptom texts (cached in module memory).
  3. At match time, embed the current user message + last 3 user turns.
  4. Cosine similarity against the symptom embeddings.
  5. Filter by vertical_bias (if present) and scale range.
  6. Return top-3 matches above a 0.35 similarity threshold.

This runs ONCE per turn, after L2 fact extraction, before BSS.
If embedding fails or times out (>500ms), return empty list — caller
must handle gracefully and continue without archetypes.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path
from typing import Optional

import yaml

from app.advisor.knowledge.ontology_schema import BusinessArchetype
from app.advisor.rag.embed import embed_query

_ONTOLOGY_PATH = Path(__file__).parent / "ontology.yaml"
_SIMILARITY_THRESHOLD = 0.35
_HIGH_CONFIDENCE_SIMILARITY = 0.65
_MAX_MATCHES = 3
_EMBED_TIMEOUT_SECONDS = 0.5
_SYNC_BRIDGE_TIMEOUT_SECONDS = 1.0

# Module-level cache: populated on first call, reused across turns
_archetypes: list[BusinessArchetype] = []
_archetype_embeddings: list[list[float]] = []  # parallel to _archetypes
_cache_loaded: bool = False


def _load_archetypes() -> list[BusinessArchetype]:
    """Parse YAML and return typed BusinessArchetype instances."""
    raw = yaml.safe_load(_ONTOLOGY_PATH.read_text(encoding="utf-8"))
    result: list[BusinessArchetype] = []
    for entry in raw.get("archetypes", []):
        result.append(BusinessArchetype(**entry))
    return result


def archetype_to_dict(arch: BusinessArchetype) -> dict[str, object]:
    """Serialize a BusinessArchetype for JSON/session persistence."""
    return asdict(arch)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Pure-Python cosine similarity. Used only for archetype matching (small vectors)."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


async def _ensure_cache() -> None:
    """Embed all archetype symptom texts and cache. Runs once."""
    global _archetypes, _archetype_embeddings, _cache_loaded
    if _cache_loaded:
        return
    _archetypes = _load_archetypes()
    embeddings: list[list[float]] = []
    for arch in _archetypes:
        symptom_text = " | ".join(arch.symptoms)
        try:
            vec = await asyncio.wait_for(
                asyncio.to_thread(embed_query, symptom_text),
                timeout=_EMBED_TIMEOUT_SECONDS * 10,  # more lenient at startup
            )
            embeddings.append(vec)
        except Exception:
            embeddings.append([])  # empty = will never match
    _archetype_embeddings = embeddings
    _cache_loaded = True


async def match_archetypes_scored(
    current_message: str,
    recent_user_turns: list[str],
    vertical: Optional[str] = None,
    employee_count: Optional[int] = None,
) -> list[tuple[float, BusinessArchetype]]:
    """
    Return up to 3 archetypes with similarity scores, ordered descending.

    Returns [] on timeout or error — callers must handle this gracefully.
    """
    await _ensure_cache()

    query_parts = recent_user_turns[-3:] + [current_message, current_message]
    query_text = " | ".join(query_parts)

    try:
        query_vec = await asyncio.wait_for(
            asyncio.to_thread(embed_query, query_text),
            timeout=_EMBED_TIMEOUT_SECONDS,
        )
    except Exception:
        return []

    scored: list[tuple[float, BusinessArchetype]] = []
    for arch, arch_vec in zip(_archetypes, _archetype_embeddings):
        if not arch_vec:
            continue

        if arch.vertical_bias and vertical and vertical not in arch.vertical_bias:
            continue

        if employee_count is not None:
            if employee_count < arch.scale_min:
                continue
            if arch.scale_max is not None and employee_count > arch.scale_max:
                continue

        sim = _cosine_similarity(query_vec, arch_vec)
        if sim >= _SIMILARITY_THRESHOLD:
            scored.append((sim, arch))

    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[:_MAX_MATCHES]


async def match_archetypes(
    current_message: str,
    recent_user_turns: list[str],
    vertical: Optional[str] = None,
    employee_count: Optional[int] = None,
) -> list[BusinessArchetype]:
    """
    Return up to 3 archetypes most similar to the current conversation context.

    Args:
        current_message: The user's current message text.
        recent_user_turns: Last 3 user messages (oldest first).
        vertical: Detected vertical from session metadata (optional filter).
        employee_count: Detected scale (optional filter).

    Returns:
        List of matched BusinessArchetype, ordered by similarity descending.
        Returns [] on timeout or error — callers must handle this gracefully.
    """
    scored = await match_archetypes_scored(
        current_message=current_message,
        recent_user_turns=recent_user_turns,
        vertical=vertical,
        employee_count=employee_count,
    )
    return [arch for _, arch in scored]


def match_archetypes_scored_sync(
    current_message: str,
    recent_user_turns: list[str],
    vertical: Optional[str] = None,
    employee_count: Optional[int] = None,
) -> list[tuple[float, BusinessArchetype]]:
    """
    Synchronous wrapper for match_archetypes_scored — safe from sync TurnPipeline.run
    even when called inside a running async event loop.
    """
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(
                asyncio.run,
                match_archetypes_scored(
                    current_message=current_message,
                    recent_user_turns=recent_user_turns,
                    vertical=vertical,
                    employee_count=employee_count,
                ),
            ).result(timeout=_SYNC_BRIDGE_TIMEOUT_SECONDS)
    except Exception:
        return []


def match_archetypes_sync(
    current_message: str,
    recent_user_turns: list[str],
    vertical: Optional[str] = None,
    employee_count: Optional[int] = None,
) -> list[BusinessArchetype]:
    """
    Synchronous wrapper for match_archetypes — safe from sync TurnPipeline.run
    even when called inside a running async event loop.
    """
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(
                asyncio.run,
                match_archetypes(
                    current_message=current_message,
                    recent_user_turns=recent_user_turns,
                    vertical=vertical,
                    employee_count=employee_count,
                ),
            ).result(timeout=_SYNC_BRIDGE_TIMEOUT_SECONDS)
    except Exception:
        return []
