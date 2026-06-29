"""Business Problem Ontology schema for Boolmind Advisor.

Each BusinessArchetype links observed symptoms to root causes, solution
categories, Boolmind services, and templated outcome framing. The ontology
is the diagnostic backbone: instead of asking generic discovery questions,
the advisor matches archetypes and asks hypothesis-testing questions.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class BusinessArchetype:
    """
    A single business problem pattern.

    Attributes:
        id: Unique snake_case identifier.
        name: Human-readable name of the archetype.
        symptoms: Natural-language phrases a business owner might say.
                  Used for embedding-based matching.
        vertical_bias: Verticals where this archetype is more common.
                       Empty list means universal.
        scale_min: Minimum employee count where this applies (inclusive).
        scale_max: Maximum employee count. None = no upper limit.
        root_cause: The underlying business/process failure.
        it_lever: The category of IT intervention that resolves this.
        boolmind_services: Which Boolmind service lines address this.
        discriminating_question: A single question that confirms OR rules
                                 out this archetype. Must be specific —
                                 never generic ("tell me more").
        outcome_frame: Templated outcome statement. Supports {vertical}
                       and {metric} placeholders.
        case_hook: One-line proof point (anonymised). Used in LLM narration.
        priority: 1=high, 2=medium, 3=low. Controls recommendation ranking.
    """

    id: str
    name: str
    symptoms: list[str]
    root_cause: str
    it_lever: str
    boolmind_services: list[str]
    discriminating_question: str
    outcome_frame: str
    vertical_bias: list[str] = field(default_factory=list)
    scale_min: int = 1
    scale_max: Optional[int] = None
    case_hook: str = ""
    priority: int = 2
