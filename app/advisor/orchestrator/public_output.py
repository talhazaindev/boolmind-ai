"""Strip model thinking blocks and internal narration from user-visible output."""

from __future__ import annotations

import re

_THINKING_BLOCK_RE = re.compile(
    r"<\s*(?:think(?:ing)?|redacted_thinking)\s*>.*?<\s*/\s*(?:think(?:ing)?|redacted_thinking)\s*>",
    re.IGNORECASE | re.DOTALL,
)
_OPEN_TAG_RE = re.compile(
    r"<\s*(?:think(?:ing)?|redacted_thinking)\s*>",
    re.IGNORECASE,
)
_CLOSE_TAG_RE = re.compile(
    r"<\s*/\s*(?:think(?:ing)?|redacted_thinking)\s*>",
    re.IGNORECASE,
)

_NARRATION_START_RE = re.compile(
    r"(?:^|\n\n)\s*"
    r"(?:"
    r"(?:Okay|Ok|Alright|Right),?\s+the user\b"
    r"|The user (?:asked|might|is|wants|seems)\b"
    r"|I need to (?:provide|list|make sure|ensure)\b"
    r"|Let me (?:check|think|review|make sure)\b"
    r"|I should (?:also|make sure|list|provide)\b"
    r"|Make sure (?:I(?:'m| am)|not to)\b"
    r")",
    re.IGNORECASE | re.MULTILINE,
)

_META_NARRATION_MARKERS = (
    "internal reasoning",
    "provided knowledge",
    "knowledge base",
    "move the conversation forward",
    "without mentioning any specific features",
    "make sure i'm not",
    "keep it simple and business-focused",
    "technical jargon",
    "high-level understanding",
    "brief descriptions",
)

_LABEL_BLOCK_RE = re.compile(
    r"(?:^|\n\n)\s*"
    r"(?:Observation|Evidence|Inference|Tradeoff)\s*:\s*",
    re.IGNORECASE | re.MULTILINE,
)

_CATALOG_HEADER_RE = re.compile(
    r"(?:^|\n\n)\s*(?:Legal Data Fusion|Retify|ECG Document Intelligence)\s*\n",
    re.IGNORECASE | re.MULTILINE,
)


def is_internal_narration_block(text: str) -> bool:
    """True when a paragraph is model self-talk, not user-facing copy."""
    stripped = text.strip()
    if not stripped:
        return False
    if _NARRATION_START_RE.search(stripped):
        return True
    lower = stripped.lower()
    if stripped.startswith("-") or stripped.startswith("*"):
        return False
    meta_hits = sum(1 for marker in _META_NARRATION_MARKERS if marker in lower)
    if meta_hits >= 2:
        return True
    if meta_hits >= 1 and not lower.startswith("boolmind"):
        first_sentence = re.split(r"[.!?]\s+", lower, maxsplit=1)[0]
        if not first_sentence.startswith("boolmind"):
            return True
    return False


def _strip_internal_narration(text: str, *, strip_edges: bool = True) -> str:
    if not text.strip():
        return ""
    parts = re.split(r"\n\n+", text)
    kept: list[str] = []
    for part in parts:
        block = part.strip()
        if not block or is_internal_narration_block(block):
            continue
        kept.append(block)
    joined = "\n\n".join(kept)
    if strip_edges:
        return joined.strip()
    if not kept:
        return ""
  # Preserve trailing paragraph separator from the source text.
    if text.endswith("\n\n") or text.endswith("\n"):
        return joined + "\n\n"
    return joined


def _strip_diagnostic_labels(text: str) -> str:
    if not _LABEL_BLOCK_RE.search(text):
        return text
    parts = re.split(r"\n\n+", text)
    kept: list[str] = []
    for part in parts:
        block = part.strip()
        if re.match(r"^(Observation|Evidence|Inference|Tradeoff)\s*:", block, re.I):
            content = re.sub(
                r"^(Observation|Evidence|Inference|Tradeoff)\s*:\s*",
                "",
                block,
                count=1,
                flags=re.I,
            ).strip()
            if content:
                kept.append(content)
            continue
        kept.append(block)
    return "\n\n".join(kept)


def sanitize_public_output(text: str) -> str:
    """Remove thinking blocks and internal narration from a complete response."""
    if not text:
        return ""
    cleaned = _THINKING_BLOCK_RE.sub("", text)
    while True:
        match = _OPEN_TAG_RE.search(cleaned)
        if not match:
            break
        cleaned = cleaned[: match.start()]
    cleaned = _CLOSE_TAG_RE.sub("", cleaned)
    cleaned = _CATALOG_HEADER_RE.sub("\n\n", cleaned)
    cleaned = _strip_diagnostic_labels(cleaned)
    return _dedupe_paragraphs(_strip_internal_narration(cleaned, strip_edges=True))


def sanitize_streaming_output(text: str) -> str:
    """Streaming-safe sanitize: removes narration/thinking without trimming SSE tail."""
    if not text:
        return ""
    cleaned = _THINKING_BLOCK_RE.sub("", text)
    while True:
        match = _OPEN_TAG_RE.search(cleaned)
        if not match:
            break
        cleaned = cleaned[: match.start()]
    cleaned = _CLOSE_TAG_RE.sub("", cleaned)
    return _dedupe_paragraphs(_strip_internal_narration(cleaned, strip_edges=False))


def _normalize_for_dedup(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _is_near_duplicate(a: str, b: str) -> bool:
    na, nb = _normalize_for_dedup(a), _normalize_for_dedup(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    min_len = min(len(na), len(nb), 200)
    if min_len >= 60 and na[:min_len] == nb[:min_len]:
        return True
    if na.startswith("boolmind offers") and nb.startswith("boolmind offers"):
        catalog_terms = ("retify", "ecg", "legal", "forecasting")
        shared = sum(1 for term in catalog_terms if term in na and term in nb)
        if shared >= 2:
            return True
        word_overlap = len(set(na.split()) & set(nb.split()))
        if word_overlap >= 5:
            return True
    return False


def _dedupe_paragraphs(text: str, *, strip_edges: bool = True) -> str:
    base = text.strip() if strip_edges else text
    if not base.strip():
        return ""
    parts = re.split(r"\n\n+", base.strip())
    kept: list[str] = []
    for part in parts:
        block = part.strip()
        if not block:
            continue
        if any(_is_near_duplicate(block, prev) for prev in kept):
            continue
        kept.append(block)
    joined = "\n\n".join(kept)
    if strip_edges:
        return joined.strip()
    if not kept:
        return ""
    if text.endswith("\n\n") or (text.endswith("\n") and not text.endswith("\n\n")):
        return joined + "\n\n"
    return joined


class _ThinkingTagFilter:
    """Remove thinking tags from a token stream."""

    def __init__(self) -> None:
        self._buffer = ""
        self._in_thinking = False

    def feed(self, chunk: str) -> str:
        if not chunk:
            return ""
        self._buffer += chunk
        emitted: list[str] = []

        while self._buffer:
            if self._in_thinking:
                close = _CLOSE_TAG_RE.search(self._buffer)
                if close is None:
                    break
                self._buffer = self._buffer[close.end() :]
                self._in_thinking = False
                continue

            close_match = _CLOSE_TAG_RE.match(self._buffer)
            if close_match:
                self._buffer = self._buffer[close_match.end() :]
                continue

            open_match = _OPEN_TAG_RE.search(self._buffer)
            if open_match is None:
                safe, self._buffer = self._split_partial_tag(self._buffer)
                if safe:
                    emitted.append(safe)
                break

            if open_match.start() > 0:
                emitted.append(self._buffer[: open_match.start()])
            self._buffer = self._buffer[open_match.end() :]
            self._in_thinking = True

        return "".join(emitted)

    def flush(self) -> str:
        if self._in_thinking:
            self._buffer = ""
            self._in_thinking = False
            return ""
        safe, self._buffer = self._split_partial_tag(self._buffer, keep_all=True)
        return safe

    @staticmethod
    def _is_partial_tag_prefix(fragment: str) -> bool:
        if not fragment.startswith("<"):
            return False
        lower = fragment.lower()
        candidates = (
            "<think",
            "<thinking",
            "<redacted_thinking",
            "</think",
            "</thinking",
            "</redacted_thinking",
        )
        return any(
            candidate.startswith(lower) or lower.startswith(candidate[: len(lower)])
            for candidate in candidates
        )

    @staticmethod
    def _split_partial_tag(text: str, *, keep_all: bool = False) -> tuple[str, str]:
        if keep_all:
            return text, ""
        last_lt = text.rfind("<")
        if last_lt == -1:
            return text, ""
        suffix = text[last_lt:]
        if _ThinkingTagFilter._is_partial_tag_prefix(suffix):
            return text[:last_lt], suffix
        return text, ""


class PublicOutputFilter:
    """Stream filter: strip thinking tags only (full sanitize runs post-stream)."""

    def __init__(self) -> None:
        self._thinking = _ThinkingTagFilter()

    def feed(self, chunk: str) -> str:
        return self._thinking.feed(chunk)

    def flush(self) -> str:
        return self._thinking.flush()
