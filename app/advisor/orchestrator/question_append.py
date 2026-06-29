"""Deterministic response finalization and redundant-question stripping."""

from __future__ import annotations

import re

from app.advisor.pipeline.question_gate import known_discovery_topics, question_violations
from app.advisor.pipeline.scale_context import is_volume_probe_question, scale_is_satisfied
from app.advisor.types import ConversationContextGraph, HypothesisSnapshot, SessionMetadata


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().strip())


def _sentences_with_questions(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p.strip() for p in parts if p.strip().endswith("?")]


def _strip_question_sentences(text: str) -> str:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    kept = [p.strip() for p in parts if p.strip() and not p.strip().endswith("?")]
    return " ".join(kept).strip()


def question_already_in_text(text: str, question: str) -> bool:
    norm_q = _normalize_text(question)
    if not norm_q:
        return False
    if norm_q in _normalize_text(text):
        return True
    for sent in _sentences_with_questions(text):
        if _normalize_text(sent) == norm_q:
            return True
    return False


def _dedupe_paragraphs(text: str) -> str:
    seen: set[str] = set()
    kept: list[str] = []
    for paragraph in re.split(r"\n\n+", text.strip()):
        block = paragraph.strip()
        if not block:
            continue
        norm = _normalize_text(block)
        if norm in seen:
            continue
        seen.add(norm)
        kept.append(block)
    return "\n\n".join(kept).strip()


def remove_matching_questions(body: str, question: str) -> str:
    """Remove question sentences that duplicate the appended follow-up."""
    if not body.strip() or not question.strip():
        return body
    norm_q = _normalize_text(question)
    parts = re.split(r"(?<=[.!?])\s+", body.strip())
    kept = [
        p.strip()
        for p in parts
        if p.strip() and not (p.strip().endswith("?") and _normalize_text(p) == norm_q)
    ]
    return " ".join(kept).strip()


def strip_redundant_questions(
    body: str,
    snapshot: HypothesisSnapshot,
    meta: SessionMetadata,
    *,
    appended_question: str | None = None,
    graph: ConversationContextGraph | None = None,
    message: str = "",
    history: list[str] | None = None,
) -> str:
    """Remove body questions that duplicate appended Q, known facts, or policy violations."""
    if not body.strip():
        return body

    body = _dedupe_paragraphs(body)

    if appended_question:
        body = remove_matching_questions(body, appended_question)
        body = _strip_question_sentences(body)

    known = known_discovery_topics(snapshot, meta)
    kept_parts: list[str] = []
    for paragraph in re.split(r"\n\n+", body.strip()):
        block = paragraph.strip()
        if not block:
            continue
        if re.search(r"^\s*\d+[\.)]\s", block, re.M):
            continue
        questions = _sentences_with_questions(block)
        if questions:
            drop = False
            for q in questions:
                violations = question_violations(
                    q,
                    snapshot,
                    meta,
                    graph,
                    message=message,
                    history=history,
                )
                if violations or (
                    is_volume_probe_question(q)
                    and scale_is_satisfied(
                        meta,
                        snapshot,
                        message=message,
                        history=history,
                        graph=graph,
                    )
                ):
                    drop = True
                    break
                if any(
                    v.startswith("topic_already_known") or v == "scale_already_answered"
                    for v in violations
                ):
                    drop = True
                    break
            if drop:
                non_q = _strip_question_sentences(block)
                if non_q:
                    kept_parts.append(non_q)
                continue
        kept_parts.append(block)
    return _dedupe_paragraphs("\n\n".join(kept_parts).strip())


def finalize_response(body: str, required_question: str | None) -> str:
    body = _dedupe_paragraphs(body.rstrip())
    if not required_question:
        return body
    rq = required_question.strip()
    if question_already_in_text(body, rq):
        return body
    body = _strip_question_sentences(body)
    return f"{body}\n\n{rq}" if body else rq
