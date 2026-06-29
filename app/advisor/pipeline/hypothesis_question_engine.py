"""
Hypothesis-Driven Question Engine.

Given scored matched archetypes and the current IssueTree state, this
engine selects the single best question to ask this turn.

Selection logic:
  1. If there is exactly one matched archetype with high similarity (>0.65):
     Use that archetype's discriminating_question directly (confirms/rules out).

  2. If there are 2-3 matched archetypes (or single match <= 0.65):
     Select discriminating questions in similarity order — the one whose
     answer would eliminate archetypes from contention.

  3. If no archetypes matched (similarity below threshold):
     Fall back to phase-based discovery questions keyed on DiagnosticPhase.

  4. If root cause is already confirmed (depth >= 75):
     Shift to impact/constraint questions from the confirmed archetype.

  5. Never ask a question already in the question_ledger (existing dedup).

This engine REPLACES the generic compose_contextual_question for archetype-
matched turns. It falls back to the existing composer when no question is selected.
"""

from __future__ import annotations

from typing import Optional

from app.advisor.knowledge.ontology_loader import _HIGH_CONFIDENCE_SIMILARITY
from app.advisor.knowledge.ontology_schema import BusinessArchetype
from app.advisor.pipeline.diagnostic_protocol import DiagnosticDepth, DiagnosticPhase, IssueTree
from app.advisor.pipeline.question_ledger import normalize_question_fingerprint

# Phase-based fallback questions when no archetype matches
# These are discovery questions, not hypothesis tests — they help identify the archetype.
_PHASE_FALLBACK_QUESTIONS: dict[DiagnosticPhase, list[str]] = {
    DiagnosticPhase.PROBLEM_IDENTIFICATION: [
        "Which single area of your business causes you the most day-to-day friction right now — sales, operations, finance, customer service, or something else?",
        "If you could solve one business problem tomorrow that would have the biggest impact, what would it be?",
        "What does a frustrating week look like for you or your team — what keeps going wrong?",
    ],
    DiagnosticPhase.SCOPE_CHARACTERISATION: [
        "How many people on your team are affected by this problem, and roughly how many hours per week do you think it costs them?",
        "Is this something that happens daily, weekly, or less often — and has it been getting worse as you've grown?",
        "Which department or role feels this pain the most — is it you as the owner, your ops team, your sales team, or your customers?",
    ],
    DiagnosticPhase.ROOT_CAUSE_HYPOTHESIS: [
        "When this problem happens, what's usually the trigger — a system that doesn't exist, a process that breaks down, or people not having the right information?",
        "Have you tried to fix this before — and if so, what happened?",
        "Is the core issue that information isn't captured anywhere, that it's captured but in the wrong place, or that nobody acts on it in time?",
    ],
    DiagnosticPhase.IMPACT_QUANTIFICATION: [
        "What's your best rough estimate of what this costs you — either in lost revenue, wasted staff hours, or customer complaints per month?",
        "Has this problem ever directly cost you a client, a sale, or a good employee?",
        "If you fixed this completely tomorrow, what would immediately get better — and what's the biggest thing that would change for your team?",
    ],
    DiagnosticPhase.CONSTRAINT_DISCOVERY: [
        "What's stopped you from solving this until now — budget, not knowing where to start, bad experiences with tech projects before, or something else?",
        "Have you looked at off-the-shelf tools for this? If so, why didn't they work for your situation?",
        "Is there a specific deadline or event driving the urgency to solve this now — or has it been a background problem for a while?",
    ],
    DiagnosticPhase.SOLUTION_READINESS: [
        "Are you at the stage of exploring what's possible, or do you have a budget and timeline and you're looking to move quickly?",
        "Who else would be involved in making this decision — is it just you, or do you need to bring in a partner, a finance person, or your board?",
        "What would success look like in 90 days — what specific thing would need to be true for you to say 'yes, that worked'?",
    ],
}


def _question_already_asked(question: str, already_asked: set[str]) -> bool:
    """True when this question (or its fingerprint) is in the ledger."""
    fp = normalize_question_fingerprint(question)
    return fp in already_asked


def select_hypothesis_question(
    matched_scored: list[tuple[float, BusinessArchetype]],
    issue_tree: IssueTree,
    depth: DiagnosticDepth,
    already_asked: set[str],
) -> Optional[str]:
    """
    Return the best next question string, or None to let existing composer handle it.

    Args:
        matched_scored: From ontology_loader.match_archetypes_scored().
        issue_tree: Current IssueTree state.
        depth: Current DiagnosticDepth.
        already_asked: Set of question fingerprints from question_ledger (for dedup).

    Returns:
        Question string, or None if falling back to existing composer.
    """
    try:
        if depth.score >= 75 or issue_tree.root_cause_confirmed:
            top_arch = matched_scored[0][1] if matched_scored else None
            if top_arch is not None:
                impact_q = _impact_or_constraint_question(top_arch, depth, already_asked)
                if impact_q:
                    return impact_q

        if not matched_scored:
            return _select_phase_fallback(depth.phase, already_asked)

        sorted_matches = sorted(matched_scored, key=lambda x: x[0], reverse=True)

        if len(sorted_matches) == 1:
            sim, arch = sorted_matches[0]
            if sim > _HIGH_CONFIDENCE_SIMILARITY:
                q = arch.discriminating_question
                if not _question_already_asked(q, already_asked):
                    return q
                return _impact_or_constraint_question(arch, depth, already_asked)

        for _sim, arch in sorted_matches:
            q = arch.discriminating_question
            if not _question_already_asked(q, already_asked):
                return q

        top_arch = sorted_matches[0][1]
        return _impact_or_constraint_question(top_arch, depth, already_asked)
    except Exception:
        return None


def _impact_or_constraint_question(
    arch: BusinessArchetype,
    depth: DiagnosticDepth,
    already_asked: set[str],
) -> Optional[str]:
    """After discriminating question answered, ask about impact or constraint."""
    del arch  # reserved for future archetype-specific impact questions
    if depth.phase == DiagnosticPhase.IMPACT_QUANTIFICATION:
        candidates = _PHASE_FALLBACK_QUESTIONS[DiagnosticPhase.IMPACT_QUANTIFICATION]
    elif depth.phase == DiagnosticPhase.CONSTRAINT_DISCOVERY:
        candidates = _PHASE_FALLBACK_QUESTIONS[DiagnosticPhase.CONSTRAINT_DISCOVERY]
    else:
        candidates = _PHASE_FALLBACK_QUESTIONS.get(depth.phase, [])

    for q in candidates:
        if not _question_already_asked(q, already_asked):
            return q
    return None


def _select_phase_fallback(
    phase: DiagnosticPhase, already_asked: set[str]
) -> Optional[str]:
    """Return the first phase-appropriate question not yet asked."""
    candidates = _PHASE_FALLBACK_QUESTIONS.get(phase, [])
    for q in candidates:
        if not _question_already_asked(q, already_asked):
            return q
    return None


def is_hypothesis_engine_question(question: str | None) -> bool:
    """True when the question was authored by the hypothesis question engine."""
    if not question or not question.strip():
        return False
    fp = normalize_question_fingerprint(question)
    for phase_questions in _PHASE_FALLBACK_QUESTIONS.values():
        for candidate in phase_questions:
            if normalize_question_fingerprint(candidate) == fp:
                return True
    try:
        from app.advisor.knowledge.ontology_loader import _load_archetypes

        for arch in _load_archetypes():
            if normalize_question_fingerprint(arch.discriminating_question) == fp:
                return True
    except Exception:
        return False
    return False
