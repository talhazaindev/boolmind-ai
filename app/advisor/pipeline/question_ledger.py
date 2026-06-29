"""Question ledger — track asked, answered, and declined questions; avoid repeats."""

from __future__ import annotations

import re

from app.advisor.pipeline.question_gate import question_topic_for_text
from app.advisor.types import SessionMetadata

_DECLINED_REPLY_SIGNALS: tuple[str, ...] = (
    "don't know",
    "dont know",
    "do not know",
    "not sure",
    "no idea",
    "can't say",
    "cant say",
    "cannot say",
    "hard to say",
    "doesn't apply",
    "doesnt apply",
    "not relevant",
    "why do you ask",
    "i don't remember",
    "i dont remember",
    "no clue",
    "not really",
    "haven't tracked",
    "havent tracked",
    "don't track",
    "dont track",
)

_TOPIC_ANSWER_HINTS: dict[str, tuple[str, ...]] = {
    "inventory_tracking": (
        "stockout",
        "stock out",
        "over order",
        "over-order",
        "overorder",
        "end of the day",
        "end of day",
        "kitchen staff",
        "day end",
        "rotten",
        "run out of stock",
        "run out",
        "overstock",
        "no way to track",
        "waste",
    ),
    "order_flow": (
        "waiter",
        "waiters",
        "paper bill",
        "paper",
        "delivery",
        "counter",
        "table service",
        "order entry",
        "kitchen coordination",
    ),
    "tools_stack": (
        "total manual",
        "entirely manual",
        "no digital",
        "no tool",
        "no software",
        "no system",
    ),
    "demand_forecast": (
        "assumption",
        "assumptions",
        "guess",
        "guesses",
        "no proper data",
        "no data",
        "informal estimate",
    ),
    "profitability": (
        "track sales",
        "paper bill",
        "sales and profit",
        "2 hours",
        "takes too long",
        "after closing",
    ),
    "integration": (
        "spreadsheet",
        "excel",
        "paper",
        "verbal",
    ),
}

_TOPIC_FAMILY_PATTERNS: dict[str, tuple[str, ...]] = {
    "inventory_tracking": (
        r"track stock",
        r"stock levels",
        r"run out or over-order",
        r"stockout",
        r"over-order key",
    ),
    "order_flow": (
        r"orders flow today",
        r"order-taking",
        r"order entry",
        r"mistakes or delays",
    ),
    "tools_stack": (
        r"digital tools",
        r"currently in use",
        r"entirely manual",
    ),
    "demand_forecast": (
        r"forecast demand",
        r"weekends or special",
    ),
    "solution_prioritization": (
        r"automate first",
        r"automate one workflow",
        r"had to pick one",
        r"highest-impact starting point",
    ),
    "profitability": (
        r"most profitable",
        r"profit or cost",
        r"visibility what",
    ),
}

_QUESTION_STEM_STOPWORDS = frozenset(
    {"today", "right", "most", "currently", "roughly", "about", "which", "where", "what", "how"}
)


def detect_answered_topics_from_context(blob: str) -> list[str]:
    """Infer answered topics from cumulative user vocabulary."""
    lower = blob.lower()
    answered: list[str] = []
    for key, hints in _TOPIC_ANSWER_HINTS.items():
        if any(h in lower for h in hints):
            answered.append(key)
    return answered


def question_topic_families(question: str | None) -> list[str]:
    """Topic families a question belongs to — for family-level exhaustion."""
    if not question:
        return []
    q = question.lower()
    sol_patterns = _TOPIC_FAMILY_PATTERNS.get("solution_prioritization", ())
    if any(re.search(pat, q, re.I) for pat in sol_patterns):
        return ["solution_prioritization"]
    families: list[str] = []
    for family, patterns in _TOPIC_FAMILY_PATTERNS.items():
        if any(re.search(pat, q, re.I) for pat in patterns):
            families.append(family)
    key = question_topic_key(question)
    if key and key not in families:
        families.append(key)
    return families


def question_stem(question: str | None) -> str:
    """Normalized stem for near-duplicate detection."""
    if not question:
        return ""
    q = normalize_question_fingerprint(question)
    tokens = [t for t in q.split() if t not in _QUESTION_STEM_STOPWORDS and len(t) > 3]
    return " ".join(tokens[:10])


def reply_addresses_question(message: str, question: str) -> bool:
    """True when a substantive reply supplies information the question sought."""
    if is_declined_reply(message):
        return False
    if len(message.strip()) < 15:
        return False
    blob = message.lower()
    for family in question_topic_families(question):
        hints = _TOPIC_ANSWER_HINTS.get(family, ())
        if hints and any(h in blob for h in hints):
            return True
    q_tokens = {
        t
        for t in re.findall(r"[a-z]{5,}", question.lower())
        if t not in _QUESTION_STEM_STOPWORDS
    }
    m_tokens = {
        t
        for t in re.findall(r"[a-z]{5,}", blob)
        if t not in _QUESTION_STEM_STOPWORDS
    }
    return len(q_tokens & m_tokens) >= 3


def question_stem_already_asked(question: str, meta: SessionMetadata) -> bool:
    stem = question_stem(question)
    if not stem or len(stem) < 12:
        return False
    for past_q_fp in meta.asked_question_fingerprints:
        past_stem = question_stem(past_q_fp)
        if not past_stem:
            continue
        if stem == past_stem or stem in past_stem or past_stem in stem:
            return True
        if stem[:32] == past_stem[:32]:
            return True
    return False


_TIMELINE_QUESTION_MARKERS: tuple[str, ...] = (
    "first notice this shift",
    "which quarter or month",
    "when did you first",
    "roughly which quarter",
)


def normalize_question_fingerprint(question: str | None) -> str:
    """Stable fingerprint for deduplication."""
    if not question:
        return ""
    q = re.sub(r"\s+", " ", question.lower().strip())
    q = re.sub(r"[^\w\s\-\?]", "", q)
    return q[:96]


def is_declined_reply(message: str) -> bool:
    """True when the user signals they cannot or will not answer the last question."""
    lower = message.lower().strip()
    if len(lower) < 4:
        return True
    if any(sig in lower for sig in _DECLINED_REPLY_SIGNALS):
        return True
    if lower in ("no", "nope", "nah", "pass"):
        return True
    return False


def is_timeline_question(question: str | None) -> bool:
    if not question:
        return False
    q = question.lower()
    return any(marker in q for marker in _TIMELINE_QUESTION_MARKERS)


def question_topic_key(question: str | None) -> str:
    """Topic key for ledger — timeline questions always map to timeline."""
    if is_timeline_question(question):
        return "timeline"
    key = question_topic_for_text(question)
    return key or "custom"


def question_already_in_history(question: str, meta: SessionMetadata) -> bool:
    """True if this question (or near-duplicate) was asked recently."""
    fp = normalize_question_fingerprint(question)
    if not fp:
        return False
    if fp in meta.asked_question_fingerprints:
        return True
    prefix = fp[:48]
    return any(past.startswith(prefix) or prefix.startswith(past[:48]) for past in meta.asked_question_fingerprints)


def is_question_exhausted(question: str | None, meta: SessionMetadata) -> bool:
    """True when this question topic was answered, skipped, or recently asked."""
    if not question:
        return True
    key = question_topic_key(question)
    if key in meta.answered_question_keys:
        return True
    if key in meta.skipped_question_keys:
        return True
    for family in question_topic_families(question):
        if family in meta.answered_question_keys or family in meta.skipped_question_keys:
            return True
    if key in meta.open_question_keys and meta.consecutive_question_turns >= 2:
        return True
    if question_already_in_history(question, meta):
        return True
    if question_stem_already_asked(question, meta):
        return True
    return False


def filter_questions_by_ledger(
    candidates: list[str | None],
    meta: SessionMetadata,
) -> list[str]:
    """Drop exhausted or duplicate questions — preserve order."""
    kept: list[str] = []
    seen_fps: set[str] = set()
    for q in candidates:
        if not q or not q.strip():
            continue
        if is_question_exhausted(q, meta):
            continue
        fp = normalize_question_fingerprint(q)
        if fp in seen_fps:
            continue
        seen_fps.add(fp)
        kept.append(q)
    return kept


def record_questions_from_text(meta: SessionMetadata, text: str) -> SessionMetadata:
    """Record every question sentence sent to the user."""
    updated = meta
    for sentence in re.split(r"(?<=[.!?])\s+", text.strip()):
        if sentence.strip().endswith("?"):
            updated = record_asked_question(updated, sentence.strip())
    return updated


def record_asked_question(meta: SessionMetadata, question: str | None) -> SessionMetadata:
    """Append fingerprint and open key after a question is sent."""
    if not question:
        return meta
    fp = normalize_question_fingerprint(question)
    fingerprints = list(meta.asked_question_fingerprints)
    if fp and fp not in fingerprints:
        fingerprints.append(fp)
    key = question_topic_key(question)
    open_keys = list(meta.open_question_keys)
    if key not in open_keys:
        open_keys.append(key)
    return meta.model_copy(
        update={
            "asked_question_fingerprints": fingerprints[-12:],
            "open_question_keys": open_keys,
            "last_appended_question": question,
        }
    )


def process_ledger_on_user_turn(
    meta: SessionMetadata,
    message: str,
    history: list[str],
) -> tuple[list[str], list[str], list[str]]:
    """
    Update open / answered / skipped keys from the user's latest message.
    Returns (open_keys, answered_keys, skipped_keys).
    """
    from app.advisor.pipeline.question_tracker import detect_answered_question_keys

    skipped = list(meta.skipped_question_keys)
    answered = list(meta.answered_question_keys)
    open_keys = list(meta.open_question_keys)

    if meta.last_appended_question:
        last_key = question_topic_key(meta.last_appended_question)
        if last_key in meta.open_question_keys:
            if is_declined_reply(message):
                if last_key not in skipped:
                    skipped.append(last_key)
                open_keys = [k for k in open_keys if k != last_key]
            elif (
                last_key in detect_answered_question_keys(message, history)
                or reply_addresses_question(message, meta.last_appended_question)
            ):
                if last_key not in answered:
                    answered.append(last_key)
                for family in question_topic_families(meta.last_appended_question):
                    if family not in answered:
                        answered.append(family)
                open_keys = [k for k in open_keys if k != last_key]

    blob = " ".join([message, *history[-6:]]).lower()
    for key in detect_answered_topics_from_context(blob):
        if key not in answered:
            answered.append(key)
        open_keys = [k for k in open_keys if k != key]

    newly_answered = detect_answered_question_keys(message, history)
    for key in newly_answered:
        if key not in answered:
            answered.append(key)
        open_keys = [k for k in open_keys if k != key]

    return open_keys, answered, skipped
