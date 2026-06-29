"""Generic evidence extraction — facts from user text without industry taxonomies."""

from __future__ import annotations

import re
from typing import Iterable

from app.advisor.pipeline.discovery_models import ExtractedFact, FactGraph
from app.advisor.pipeline.volume_patterns import extract_volume_indicators
from app.advisor.types import ConversationContextGraph, HypothesisSnapshot, SessionMetadata

def _tag_strength(confidence: float, source: str = "user") -> str:
    if source == "user" and confidence >= 0.88:
        return "observed"
    if confidence >= 0.7:
        return "inferred"
    return "speculated"


_STOPWORDS = frozenset(
    {
        "about",
        "after",
        "also",
        "been",
        "being",
        "both",
        "from",
        "have",
        "that",
        "their",
        "there",
        "these",
        "they",
        "this",
        "through",
        "were",
        "what",
        "when",
        "where",
        "which",
        "while",
        "with",
        "would",
        "your",
    }
)

_GENERIC_VOCAB = frozenset(
    {
        "accuracy",
        "average",
        "changed",
        "cost",
        "customer",
        "declining",
        "delivery",
        "dropped",
        "efficiency",
        "growing",
        "margin",
        "materially",
        "metric",
        "performance",
        "pricing",
        "rate",
        "recent",
        "response",
        "retention",
        "revenue",
        "service",
        "time",
        "volume",
    }
)

# Template-leakage terms — not an industry taxonomy; blocks known catalog contamination.
_CONTAMINANT_TERMS = frozenset(
    {
        "chair utilization",
        "claim denial",
        "denial rate",
        "denial rates",
        "loan approval",
        "patient throughput",
        "reimbursement timing",
        "underwriting queue",
    }
)

_STAKEHOLDER_PATTERN = re.compile(
    r"(?P<role>sales|operations|customer service|finance|marketing|engineering|product|"
    r"leadership|ops|support|hr|it|design|production|account managers?)\s+"
    r"(?:says?|believes?|thinks?|points to|blames?)\s+"
    r"(?P<theory>[^.,;]+)",
    re.I,
)
_GENERIC_STAKEHOLDER_PATTERN = re.compile(
    r"\b(?P<role>[A-Za-z][\w\s]{2,28}?)\s+"
    r"(?:says?|believes?|thinks?|points to|blames?)\s+"
    r"(?P<theory>[^.,;]+)",
    re.I,
)
_INVALID_ROLES = frozenset(
    {
        "we",
        "revenue",
        "it",
        "that",
        "this",
        "order",
        "but",
        "and",
        "the",
        "our",
        "they",
    }
)
_DEPARTMENT_NAMES = frozenset(
    {
        "sales",
        "finance",
        "operations",
        "marketing",
        "engineering",
        "product",
        "support",
        "leadership",
        "ops",
        "hr",
        "it",
    }
)


def _is_substantive_theory(theory: str) -> bool:
    lower = theory.lower().strip()
    if len(lower) < 8:
        return False
    if lower in _DEPARTMENT_NAMES:
        return False
    words = lower.split()
    if len(words) == 1:
        return words[0] not in _DEPARTMENT_NAMES
    return True


_DIVIDED_PATTERN = re.compile(
    r"(?:some think it's|others think it's|some believe|another camp thinks?)\s+([^.,;]+)",
    re.I,
)
_OUTCOME_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"(?:customer )?retention (?:has )?dropped from [\d.]+%? to [\d.]+%?", "retention decline"),
    (r"retention (?:has )?dropped", "retention decline"),
    (r"[\w-]+ approvals? (?:have )?fallen from [\d.]+%? to [\d.]+%?", "approval decline"),
    (r"revenue (?:grew|increased|is (?:up|growing))[^.]{0,50}", "revenue growth"),
    (r"revenue is (?:up|growing)[^.]{0,40}", "revenue growth"),
    (r"(?:operating )?margins? (?:fell|dropped|declined|shrunk)[^.]{0,60}", "margin decline"),
    (r"margins? (?:fell|dropped|declined) from [\d.]+%? to [\d.]+%?", "margin compression"),
    (r"profitability (?:has )?been declining", "profitability decline"),
    (r"margins? (?:keep )?(?:shrinking|declining)", "margin decline"),
    (r"(?:churn|turnover) (?:has |is )?(?:increased|rising|up)", "churn increase"),
    (r"(?:client |customer )?complaints? (?:have |has )?(?:increased|rising|up)", "complaints increase"),
    (r"(?:wait times?|backlog) (?:have |has )?(?:increased|doubled|grown|lengthened)", "wait time increase"),
    (r"cash flow (?:is )?(?:unstable|tight|strained)", "cash instability"),
    (r"revenue (?:is )?growing[^.]{0,30}cash", "revenue cash divergence"),
)
_ORGANIZATIONAL_CHANGE_PATTERN = re.compile(
    r"(?:(?:we|they)\s+)?(?:(?:recently|just)\s+)?(?:have\s+)?"
    r"(?:changed|restructured|revised|updated|introduced|implemented|"
    r"redesigned|rolled out|switched)\s+(?:our\s+|the\s+)?(?P<subject>[^.,;]{5,90})",
    re.I,
)
_EXPANSION_PATTERN = re.compile(
    r"(?P<span>(?:opened|launched|added)\s+(?:\d+\s+)?(?:new\s+)?"
    r"(?:locations?|sites?|offices?|stores?|clinics?|branches?|markets?)[^.]{0,40})",
    re.I,
)
_STATED_BELIEF_ROLES = frozenset(
    {
        "management",
        "leadership",
        "executives",
        "the team",
        "our team",
        "leadership team",
    }
)
_SYMPTOM_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"(fulfillment reliability[^.,]{0,40}(?:slipping|worsening))", "fulfillment symptom"),
    (r"(response times? (?:are |is )?(?:driving|causing|getting)[^.,]{0,40})", "response symptom"),
)
_CONSTRAINT_PATTERNS: tuple[str, ...] = (
    r"we (?:can't|cannot) [^.]{5,60}",
    r"limited (?:by|to) [^.]{5,60}",
    r"constraint (?:is|on) [^.]{5,60}",
)
_TIMELINE_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"last two quarters?", "two quarters"),
    (r"last three quarters?", "three quarters"),
    (r"last (\d+) quarters?", "quarters"),
    (r"last (\d+) months?", "months"),
    (r"18\s*months?", "18 months"),
    (r"over the last (?:few )?quarters?", "the last few quarters"),
    (r"last quarter", "the last quarter"),
    (r"six months?", "six months"),
)
_CONTEXT_PATTERN = re.compile(
    r"(?:we're|we are) (?:a |an )?([^.]{10,120}?)(?:\.|,|revenue|but)",
    re.I,
)


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower().strip())[:56].strip("_")
    return slug or "fact"


def _clean_theory(raw: str) -> str:
    theory = raw.strip().rstrip(".")
    theory = re.sub(r"\s+are the real issue$", "", theory, flags=re.I)
    theory = re.sub(r"\s+are driving dissatisfaction$", "", theory, flags=re.I)
    return theory.strip()


def _metric_phrase(theory: str) -> str:
    cleaned = _clean_theory(theory)
    cleaned = re.sub(r"^(?:that |the )", "", cleaned, flags=re.I)
    if len(cleaned) > 72:
        return cleaned[:69].rsplit(" ", 1)[0] + "..."
    return cleaned


def _tokenize_vocab(text: str) -> set[str]:
    words = set(re.findall(r"[a-z]{4,}", text.lower()))
    return words - _STOPWORDS


def build_conversation_text(
    meta: SessionMetadata,
    snapshot: HypothesisSnapshot,
    *,
    message: str = "",
    history: list[str] | None = None,
    graph: ConversationContextGraph | None = None,
) -> str:
    parts = [
        meta.business_type or "",
        meta.industry or "",
        meta.pain_point or "",
        message,
        " ".join(history or []),
        " ".join(snapshot.confirmed_facts),
        " ".join(snapshot.scale_indicators),
    ]
    if graph:
        parts.extend(graph.pain_points)
        if graph.industry:
            parts.append(graph.industry)
    return " ".join(p for p in parts if p).strip()


def extract_organizational_changes(text: str) -> list[ExtractedFact]:
    """Policy, compensation, pricing, or operating-model changes stated by the user."""
    facts: list[ExtractedFact] = []
    seen: set[str] = set()
    for m in _ORGANIZATIONAL_CHANGE_PATTERN.finditer(text):
        subject = m.group("subject").strip().rstrip(".")
        span = m.group(0).strip()
        if len(subject) < 5 or span.lower() in seen:
            continue
        seen.add(span.lower())
        facts.append(
            ExtractedFact(
                id=f"org_change_{_slug(subject)}",
                category="organizational_change",
                text=span,
                confidence=0.92,
                evidence_strength="observed",
            )
        )
    return facts


def _valid_stakeholder_role(role: str) -> bool:
    role_clean = role.lower().strip()
    if role_clean in _INVALID_ROLES or len(role_clean) < 2:
        return False
    if any(w in role_clean for w in ("because", "considering", "evaluating", "exploring")):
        return False
    if len(role_clean.split()) > 3:
        return False
    return True


def extract_stated_hypotheses(text: str) -> list[ExtractedFact]:
    """User or leadership beliefs about cause — not competing stakeholder theories."""
    facts: list[ExtractedFact] = []
    seen: set[str] = set()
    patterns = (
        _STAKEHOLDER_PATTERN,
        _GENERIC_STAKEHOLDER_PATTERN,
    )
    for pattern in patterns:
        for m in pattern.finditer(text):
            role = m.group("role").lower().strip()
            theory = _clean_theory(m.group("theory"))
            if role not in _STATED_BELIEF_ROLES or not _is_substantive_theory(theory):
                continue
            if theory in seen:
                continue
            seen.add(theory)
            facts.append(
                ExtractedFact(
                    id=f"belief_{_slug(theory)}",
                    category="stated_hypothesis",
                    text=theory,
                    stakeholder=role,
                    confidence=0.85,
                    evidence_strength="inferred",
                )
            )
    considering = re.search(
        r"(?:considering|evaluating|exploring)\s+[^.]{8,100}"
        r"(?:because|since)\s+[^.]{5,80}(?:believes?|thinks?)\s+(?P<belief>[^.,;]+)",
        text,
        re.I,
    )
    if considering:
        belief = _clean_theory(considering.group("belief"))
        if _is_substantive_theory(belief) and belief not in seen:
            facts.append(
                ExtractedFact(
                    id=f"belief_{_slug(belief)}",
                    category="stated_hypothesis",
                    text=belief,
                    stakeholder="management",
                    confidence=0.82,
                    evidence_strength="inferred",
                )
            )
    return facts


def extract_stakeholder_theories(text: str) -> list[ExtractedFact]:
    facts: list[ExtractedFact] = []
    seen: set[str] = set()

    def _add(role: str, theory_raw: str, confidence: float) -> None:
        role_clean = role.lower().strip()
        if not _valid_stakeholder_role(role_clean):
            return
        if role_clean in _STATED_BELIEF_ROLES:
            return
        theory = _clean_theory(theory_raw)
        if not _is_substantive_theory(theory) or theory in seen:
            return
        seen.add(theory)
        facts.append(
            ExtractedFact(
                id=f"theory_{_slug(role_clean)}_{_slug(theory)}",
                category="stakeholder_theory",
                text=theory,
                stakeholder=role_clean,
                confidence=confidence,
            )
        )

    collected: list[tuple[str, str, float]] = []
    for m in _STAKEHOLDER_PATTERN.finditer(text):
        collected.append((m.group("role"), m.group("theory"), 0.92))
    for m in _GENERIC_STAKEHOLDER_PATTERN.finditer(text):
        role = m.group("role").lower().strip()
        if role in _STATED_BELIEF_ROLES or not _valid_stakeholder_role(role):
            continue
        collected.append((m.group("role"), m.group("theory"), 0.88))
    for clause in re.split(r",\s*and\s*|,\s*", text):
        m = re.match(
            r"(?P<role>sales|operations|customer service|finance|marketing|engineering|product|"
            r"leadership|ops|support|hr|it|design|production|account managers?)\s+"
            r"(?:says?|believes?|thinks?|points to|blames?)\s+(?P<theory>.+)",
            clause.strip(),
            re.I,
        )
        if m:
            theory = m.group("theory").strip().split(".")[0].strip()
            collected.append((m.group("role"), theory, 0.9))
    collected.sort(key=lambda x: len(x[1]), reverse=True)
    for role, theory_raw, confidence in collected:
        _add(role, theory_raw, confidence)
    for m in _DIVIDED_PATTERN.finditer(text):
        theory = _clean_theory(m.group(1))
        if len(theory) < 4 or theory in seen:
            continue
        seen.add(theory)
        facts.append(
            ExtractedFact(
                id=f"theory_divided_{_slug(theory)}",
                category="stakeholder_theory",
                text=theory,
                stakeholder="leadership",
                confidence=0.88,
            )
        )
    return facts


def extract_outcomes(text: str) -> list[ExtractedFact]:
    lower = text.lower()
    facts: list[ExtractedFact] = []
    for pattern, label in _OUTCOME_PATTERNS:
        m = re.search(pattern, lower, re.I)
        if m:
            span = m.group(0).strip()
            facts.append(
                ExtractedFact(
                    id=f"outcome_{_slug(label)}",
                    category="outcome",
                    text=span,
                    confidence=0.9,
                    evidence_strength=_tag_strength(0.9),  # type: ignore[arg-type]
                )
            )
    return facts


def extract_symptoms(text: str) -> list[ExtractedFact]:
    lower = text.lower()
    facts: list[ExtractedFact] = []
    seen: set[str] = set()
    for pattern, _ in _SYMPTOM_PATTERNS:
        for m in re.finditer(pattern, lower, re.I):
            span = m.group(1 if m.lastindex else 0).strip()
            if len(span) < 8 or span in seen:
                continue
            seen.add(span)
            facts.append(
                ExtractedFact(
                    id=f"symptom_{_slug(span)}",
                    category="symptom",
                    text=span,
                    confidence=0.75,
                    evidence_strength=_tag_strength(0.75),  # type: ignore[arg-type]
                )
            )
    # Generic problem phrases from user vocabulary (no industry catalog)
    for m in re.finditer(
        r"([a-z][^.!?]{10,80}(?:fail|delay|slow|bottleneck|rework|variance|problem|issue|wait|slipping)s?[^.!?]*)",
        lower,
        re.I,
    ):
        span = m.group(1).strip()
        if span in seen or len(span) < 12:
            continue
        if re.search(r"\b(?:says?|believes?|thinks?|blames?)\b", span):
            continue
        seen.add(span)
        facts.append(
            ExtractedFact(
                id=f"symptom_{_slug(span)}",
                category="symptom",
                text=span,
                confidence=0.7,
                evidence_strength="inferred",
            )
        )
    return facts


def extract_constraints(text: str) -> list[ExtractedFact]:
    lower = text.lower()
    facts: list[ExtractedFact] = []
    for pattern in _CONSTRAINT_PATTERNS:
        m = re.search(pattern, lower, re.I)
        if m:
            span = m.group(0).strip()
            facts.append(
                ExtractedFact(
                    id=f"constraint_{_slug(span)}",
                    category="constraint",
                    text=span,
                    confidence=0.8,
                )
            )
    return facts


def extract_scale_facts(text: str) -> list[ExtractedFact]:
    facts: list[ExtractedFact] = []
    for vol in extract_volume_indicators(text):
        facts.append(
            ExtractedFact(
                id=f"scale_{_slug(vol)}",
                category="scale",
                text=vol,
                confidence=0.85,
            )
        )
    for pattern in (
        r"(\d[\d,]*)\s*[-–]?\s*(?:location|store|clinic|site|office|branch|market)s?",
        r"(\d[\d,]*)\s*(?:employees|staff|people|workers|locations|clinics|sites|centers)",
    ):
        m = re.search(pattern, text, re.I)
        if m:
            facts.append(
                ExtractedFact(
                    id=f"scale_{_slug(m.group(0))}",
                    category="scale",
                    text=m.group(0).strip(),
                    confidence=0.85,
                )
            )
            break
    exp = _EXPANSION_PATTERN.search(text)
    if exp:
        span = exp.group("span").strip()
        facts.append(
            ExtractedFact(
                id=f"scale_{_slug(span)}",
                category="scale",
                text=span,
                confidence=0.88,
                evidence_strength="observed",
            )
        )
    pct = re.search(r"(?:up|growing|increased)\s+(\d+)%", text, re.I)
    if pct:
        facts.append(
            ExtractedFact(
                id=f"scale_pct_{pct.group(1)}",
                category="scale",
                text=pct.group(0).strip(),
                confidence=0.7,
            )
        )
    return facts


def extract_timeline(text: str) -> tuple[str | None, list[ExtractedFact]]:
    lower = text.lower()
    facts: list[ExtractedFact] = []
    phrase: str | None = None
    for pattern, default_phrase in _TIMELINE_PATTERNS:
        m = re.search(pattern, lower, re.I)
        if m:
            span = m.group(0).strip()
            if "quarter" in pattern and m.lastindex:
                phrase = f"{m.group(1)} quarters" if m.group(1).isdigit() else default_phrase
            elif "month" in pattern and m.lastindex:
                phrase = f"{m.group(1)} months"
            else:
                phrase = default_phrase
            facts.append(
                ExtractedFact(
                    id=f"timeline_{_slug(span)}",
                    category="timeline",
                    text=span,
                    confidence=0.9,
                )
            )
            break
    return phrase, facts


def extract_context(text: str) -> list[ExtractedFact]:
    facts: list[ExtractedFact] = []
    m = _CONTEXT_PATTERN.search(text)
    if m:
        ctx = m.group(1).strip()
        if len(ctx) >= 8:
            facts.append(
                ExtractedFact(
                    id=f"context_{_slug(ctx)}",
                    category="context",
                    text=ctx,
                    confidence=0.8,
                )
            )
    return facts


def extract_fact_graph(
    meta: SessionMetadata,
    snapshot: HypothesisSnapshot,
    *,
    message: str = "",
    history: list[str] | None = None,
    graph: ConversationContextGraph | None = None,
) -> FactGraph:
    """Build structured fact graph from conversation — no predefined cause libraries."""
    text = build_conversation_text(
        meta, snapshot, message=message, history=history, graph=graph
    )
    facts: list[ExtractedFact] = []
    facts.extend(extract_context(text))
    facts.extend(extract_outcomes(text))
    facts.extend(extract_symptoms(text))
    facts.extend(extract_organizational_changes(text))
    facts.extend(extract_stated_hypotheses(text))
    facts.extend(extract_stakeholder_theories(text))
    facts.extend(extract_constraints(text))
    facts.extend(extract_scale_facts(text))
    timeline_phrase, timeline_facts = extract_timeline(text)
    facts.extend(timeline_facts)

    _FACT_CATEGORY_PRIORITY: dict[str, int] = {
        "organizational_change": 55,
        "stated_hypothesis": 52,
        "stakeholder_theory": 50,
        "outcome": 40,
        "constraint": 35,
        "scale": 30,
        "symptom": 20,
        "timeline": 15,
        "context": 10,
    }
    by_normalized: dict[str, ExtractedFact] = {}
    for fact in facts:
        existing = by_normalized.get(fact.normalized)
        if existing is None:
            by_normalized[fact.normalized] = fact
            continue
        if _FACT_CATEGORY_PRIORITY.get(fact.category, 0) > _FACT_CATEGORY_PRIORITY.get(
            existing.category, 0
        ):
            by_normalized[fact.normalized] = fact
    unique = list(by_normalized.values())

    vocab: set[str] = set(_GENERIC_VOCAB)
    for fact in unique:
        vocab.update(_tokenize_vocab(fact.text))
    vocab.update(_tokenize_vocab(text))

    outcomes = [f for f in unique if f.category == "outcome"]
    primary_outcome = outcomes[0].text if outcomes else None

    return FactGraph(
        facts=unique,
        vocabulary=vocab,
        primary_outcome=primary_outcome,
        timeline_phrase=timeline_phrase,
        source_text=text,
    )


def is_contaminant_term(term: str) -> bool:
    return term.lower() in _CONTAMINANT_TERMS


def contaminant_terms_in_text(text: str) -> list[str]:
    lower = text.lower()
    return [t for t in _CONTAMINANT_TERMS if t in lower]


def term_in_vocabulary(term: str, vocabulary: Iterable[str]) -> bool:
    vocab = set(vocabulary)
    lower = term.lower()
    if lower in vocab:
        return True
    return any(word in vocab for word in lower.split() if len(word) > 4)
