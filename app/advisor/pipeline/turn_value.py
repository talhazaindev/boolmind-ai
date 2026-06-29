"""Per-turn user value — working picture, friction points, and draft workflow visuals."""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

from app.advisor.pipeline.discovery_models import FactGraph
from app.advisor.pipeline.progress_questions import discovery_saturated
from app.advisor.types import ConversationContextGraph, SessionMetadata

_GATHERING_TURNS = 2

_DRAFT_CONFIRM_SIGNALS: tuple[str, ...] = (
    "that's right",
    "thats right",
    "looks good",
    "looks right",
    "accurate",
    "that's correct",
    "thats correct",
    "exactly",
    "yes that's",
    "yes thats",
    "spot on",
    "you got it",
    "that's it",
    "thats it",
    "sounds right",
    "that matches",
    "final now",
    "we can move on",
    "move forward",
)

_WORKFLOW_STAGE_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\b(order|intake|application|ticket|request|booking|enquiry|inquiry)\b", "Intake"),
    (r"\b(plan|schedule|dispatch|assign|route|triage)\b", "Planning"),
    (r"\b(kitchen|production|fulfillment|processing|underwriting|manufactur|assembly)\b", "Processing"),
    (r"\b(review|compliance|approval|quality|inspection|verify)\b", "Review / QA"),
    (r"\b(handoff|hand off|coordinate|coordination|transfer)\b", "Handoff"),
    (r"\b(deliver|delivery|ship|dispatch|serve|fulfil|fulfill)\b", "Delivery"),
    (r"\b(stock|inventory|warehouse|replenish)\b", "Inventory"),
    (r"\b(report|reconcil|closing|accounting|record|track sales)\b", "Reporting"),
    (r"\b(manual|paper|spreadsheet|email|phone|verbal)\b", "Manual capture"),
)

_PAIN_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bstockout|run out|shortage\b", "Stockouts or shortages"),
    (r"\bwaste|rotten|spoil|over.?order\b", "Waste from over-ordering"),
    (r"\b2 hours|too long|slow|delay|wait\b", "Time lost to manual steps"),
    (r"\berror|mistake|inaccura\b", "Errors from manual handoffs"),
    (r"\bno (?:proper )?data|guess|assumption\b", "Decisions without reliable data"),
    (r"\bbacklog\b", "Backlog buildup"),
    (r"\blabor|staff time|headcount\b", "High labor on repetitive work"),
)


class TurnVisual(BaseModel):
    """Structured visual for the chat UI."""

    visual_type: str = "diagram"
    title: str = ""
    mermaid: str = ""
    caption: str = ""
    is_draft: bool = True


class TurnValueArtifact(BaseModel):
    """Deterministic value payload for one advisor turn."""

    deliver: bool = False
    working_summary: str = ""
    friction_points: list[str] = Field(default_factory=list)
    draft_note: str = ""
    as_is_visual: TurnVisual | None = None
    opportunity_line: str = ""
    prompt_block: str = ""


def should_deliver_turn_value(meta: SessionMetadata) -> bool:
    """After the first 1–2 gathering turns, every turn must add user-visible value."""
    return (meta.message_count or 0) > _GATHERING_TURNS


def detect_draft_confirmation(message: str) -> bool:
    lower = message.lower().strip()
    return any(sig in lower for sig in _DRAFT_CONFIRM_SIGNALS)


def _sanitize_mermaid_label(text: str, max_len: int = 28) -> str:
    cleaned = re.sub(r"[^\w\s\-/&]", "", text.strip())
    cleaned = re.sub(r"\s+", " ", cleaned)
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[: max_len - 3].rsplit(" ", 1)[0] + "..."


def infer_workflow_steps(
    fact_graph: FactGraph,
    graph: ConversationContextGraph | None = None,
) -> list[str]:
    """Industry-agnostic as-is steps from user vocabulary and context graph."""
    blob = fact_graph.blob()
    steps: list[str] = []
    seen: set[str] = set()

    if graph and graph.workflow_stages:
        for name, state in graph.workflow_stages.items():
            label = _sanitize_mermaid_label(name.replace("_", " ").title())
            if label and label not in seen:
                seen.add(label)
                steps.append(label)

    for pattern, label in _WORKFLOW_STAGE_PATTERNS:
        if re.search(pattern, blob, re.I) and label not in seen:
            seen.add(label)
            steps.append(label)

    if len(steps) < 2:
        for fact in fact_graph.facts_by_category("symptom")[:2]:
            phrase = _sanitize_mermaid_label(fact.text, 24)
            if phrase and phrase not in seen:
                seen.add(phrase)
                steps.append(phrase)

    return steps[:6]


def build_as_is_mermaid(steps: list[str]) -> str:
    if len(steps) < 2:
        return ""
    lines = ["flowchart LR"]
    for idx, step in enumerate(steps):
        lines.append(f'  s{idx}["{_sanitize_mermaid_label(step)}"]')
    for idx in range(len(steps) - 1):
        lines.append(f"  s{idx} --> s{idx + 1}")
    return "\n".join(lines)


def infer_friction_points(fact_graph: FactGraph) -> list[str]:
    blob = fact_graph.blob()
    points: list[str] = []
    for pattern, label in _PAIN_PATTERNS:
        if re.search(pattern, blob, re.I) and label not in points:
            points.append(label)
    for fact in fact_graph.facts_by_category("symptom")[:2]:
        text = fact.text.strip()
        if text and text not in points and len(text) < 80:
            points.append(text)
    return points[:4]


def _working_summary(fact_graph: FactGraph, meta: SessionMetadata) -> str:
    blob = fact_graph.blob()
    vertical = (
        meta.industry
        or meta.business_type
        or meta.active_business_vertical
        or "your operation"
    )
    manual = bool(re.search(r"manual|paper|spreadsheet|no (?:tool|system|software)", blob, re.I))
    automate = bool(re.search(r"automat", blob, re.I))

    opener = f"From what you've shared so far, this looks like a {vertical} workflow"
    if manual:
        opener += " that still relies heavily on manual steps"
    opener += "."

    if automate and manual:
        opener += (
            " You're aiming to automate repetitive work without losing control "
            "of quality — that's a sensible direction to explore."
        )
    elif discovery_saturated(fact_graph, meta):
        opener += (
            " The pattern that stands out is fragmented handoffs creating delays, "
            "errors, and blind spots in the data you need to run the business."
        )
    return opener


def _opportunity_line(fact_graph: FactGraph, steps: list[str]) -> str:
    frictions = infer_friction_points(fact_graph)
    if not frictions:
        return ""
    if len(steps) >= 2:
        return (
            f"A draft opportunity: connecting {steps[0].lower()} to {steps[-1].lower()} "
            f"with shared data could reduce {frictions[0].lower()} — still a hypothesis until you confirm."
        )
    return (
        f"A draft opportunity: addressing {frictions[0].lower()} first may unlock "
        f"the fastest payoff — we'll refine once you react to the sketch below."
    )


def build_turn_value(
    fact_graph: FactGraph,
    meta: SessionMetadata,
    *,
    graph: ConversationContextGraph | None = None,
    draft_confirmed: bool = False,
) -> TurnValueArtifact:
    """Build hedged insight + optional draft diagram for this turn."""
    if not should_deliver_turn_value(meta):
        return TurnValueArtifact(deliver=False)

    steps = infer_workflow_steps(fact_graph, graph)
    frictions = infer_friction_points(fact_graph)
    summary = _working_summary(fact_graph, meta)

    draft_note = ""
    if not draft_confirmed:
        draft_note = (
            "Working draft only — not a final design. "
            "Correct anything that doesn't match your reality."
        )

    mermaid = build_as_is_mermaid(steps)
    visual: TurnVisual | None = None
    if mermaid:
        visual = TurnVisual(
            title="How your workflow looks today (draft)",
            mermaid=mermaid,
            caption=draft_note or "Draft sketch from your description so far.",
            is_draft=not draft_confirmed,
        )

    opportunity = ""
    if discovery_saturated(fact_graph, meta) and not draft_confirmed:
        opportunity = _opportunity_line(fact_graph, steps)

    friction_block = ""
    if frictions:
        bullets = "\n".join(f"- {p}" for p in frictions)
        friction_block = f"Likely friction points (unconfirmed):\n{bullets}"

    prompt_parts = [
        "TURN VALUE REQUIRED (user must get something useful this turn):",
        "1. Open with the WORKING SUMMARY below in your own words (hedge — not confirmed facts).",
        summary,
    ]
    if friction_block:
        prompt_parts.append(f"2. Mention 1–2 friction points briefly:\n{friction_block}")
    if opportunity:
        prompt_parts.append(f"3. One tentative opportunity line (not a final recommendation):\n{opportunity}")
    if visual:
        prompt_parts.append(
            "4. Say you're sharing a draft workflow sketch to make this easier to react to — "
            "the diagram is rendered separately; do NOT paste mermaid syntax in your body."
        )
    if not draft_confirmed:
        prompt_parts.append(
            "5. Invite correction: ask whether the draft matches their reality before going deeper."
        )
    else:
        prompt_parts.append(
            "5. User confirmed the working picture — you may go deeper on design, still avoid final commitments."
        )
    prompt_parts.append(
        "6. Do NOT present Boolmind products or final architecture unless solutioning_allowed."
    )

    return TurnValueArtifact(
        deliver=True,
        working_summary=summary,
        friction_points=frictions,
        draft_note=draft_note,
        as_is_visual=visual,
        opportunity_line=opportunity,
        prompt_block="\n".join(prompt_parts),
    )
