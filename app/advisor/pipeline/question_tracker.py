"""Open-question ledger — avoid repeating unanswered diagnostic prompts."""

from __future__ import annotations

import re

from app.advisor.pipeline.question_gate import question_topic_for_text
from app.advisor.pipeline.question_ledger import process_ledger_on_user_turn
from app.advisor.types import HypothesisSnapshot, SessionMetadata

_ANSWER_SIGNALS: dict[str, tuple[str, ...]] = {
    "routing_constraints": (
        "territory",
        "vehicle capacity",
        "capacity",
        "sla",
        "customer tier",
        "customer priority",
        "time window",
        "delivery window",
    ),
    "assignment_logic": (
        "availability",
        "geography",
        "closest",
        "vehicle type",
        "priority",
        "first-come",
        "round robin",
        "rule",
        "criteria",
    ),
    "planning_tools": (
        "spreadsheet",
        "excel",
        "tms",
        "erp",
        "sap",
        "software",
        "system",
        "platform",
        "tool",
    ),
    "workflow_steps": (
        "intake",
        "manual step",
        "step",
        "workflow",
        "handoff",
        "departure",
    ),
    "scale": (
        r"\d[\d,]*\s*(shipments|orders|deliveries|applications|loans|cases)",
        r"\d[\d,]*\s*(loan\s+)?applications?\s*(per day|daily|a day)",
        r"\d+\s*(per day|daily|a day)",
    ),
    "business_context": (
        "logistics",
        "manufacturing",
        "company",
        "business",
        "operation",
    ),
    "pain_point": (
        "delay",
        "bottleneck",
        "wait",
        "error",
        "backlog",
        "inefficien",
    ),
    "backlog_size": (
        "backlog",
        r"backlog of \d+",
        r"\d+.*backlog",
    ),
    "compliance_process": (
        "compliance",
        "manual review",
        "compliance team",
    ),
    "automation_history": (
        "automation",
        "automated",
        "poor adoption",
        "went back to email",
        "exceptions",
    ),
    "integration": (
        "erp",
        "crm",
        "sap",
        "salesforce",
        "spreadsheet",
        "manual routing",
        "coordination",
    ),
    "profitability": (
        "track margin",
        "track food cost",
        "margin per item",
        "cost per dish",
        "we know which items",
        "we can see profit",
        "profit per item",
        "know our margins",
    ),
    "order_flow": (
        "dine-in",
        "takeout",
        "delivery",
        "counter",
        "table service",
        "phone order",
        "kitchen receive",
        "which table",
        "waiter",
        "waiters",
        "paper bill",
        "order entry",
        "kitchen coordination",
    ),
    "inventory_tracking": (
        "stockout",
        "stock out",
        "over order",
        "over-order",
        "end of day",
        "end of the day",
        "kitchen staff",
        "day end",
        "rotten",
        "run out of stock",
        "run out",
        "overstock",
        "no way to track",
        "waste",
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
    "timeline": (
        "last month",
        "last quarter",
        "january",
        "february",
        "march",
        "april",
        "may",
        "june",
        "july",
        "august",
        "september",
        "october",
        "november",
        "december",
        "q1",
        "q2",
        "q3",
        "q4",
        "20\\d{2}",
    ),
}

_POST_DELIVERABLE_CTA = (
    "Would you like an implementation roadmap, a rough cost estimate, "
    "or to book a consultation to walk through this design?"
)


def question_key_for_text(question: str | None) -> str | None:
    if not question:
        return None
    topic = question_topic_for_text(question)
    return topic if topic else "custom"


_DEFLECTION_SIGNALS = (
    "not sure",
    "don't know",
    "dont know",
    "why do you ask",
    "can you explain",
)


def _is_substantive_reply(message: str) -> bool:
    stripped = message.strip()
    if len(stripped) < 12:
        return False
    lower = stripped.lower()
    return not any(sig in lower for sig in _DEFLECTION_SIGNALS)


def detect_answered_question_keys(message: str, history: list[str]) -> list[str]:
    """Return question keys the user likely answered in this turn."""
    blob = " ".join([message, *history[-3:]]).lower()
    answered: list[str] = []
    for key, signals in _ANSWER_SIGNALS.items():
        for sig in signals:
            if sig.startswith(r"\d") or "(" in sig:
                if re.search(sig, blob, re.I):
                    answered.append(key)
                    break
            elif sig in blob:
                answered.append(key)
                break
    return list(dict.fromkeys(answered))


def register_asked_question(meta: SessionMetadata, question: str | None) -> list[str]:
    """Mark a question as pending (open) after append."""
    key = question_key_for_text(question)
    if not key or key == "custom":
        return list(meta.open_question_keys)
    open_keys = list(meta.open_question_keys)
    if key not in open_keys:
        open_keys.append(key)
    return open_keys


def apply_answered_questions(
    meta: SessionMetadata,
    message: str,
    history: list[str],
) -> tuple[list[str], list[str], list[str]]:
    """Move keys from open → answered/skipped when user supplies or declines evidence."""
    return process_ledger_on_user_turn(meta, message, history)


def post_deliverable_cta() -> str:
    return _POST_DELIVERABLE_CTA


def should_suppress_diagnostic_question(
    execution_mode: str,
    *,
    has_deliverable: bool = False,
) -> bool:
    """After a deliverable, never append discovery/diagnostic questions."""
    if execution_mode == "ARCHITECTURE":
        return True
    if has_deliverable and execution_mode in ("ARCHITECTURE", "SALES"):
        return True
    return False
