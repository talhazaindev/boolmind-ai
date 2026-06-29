"""Evidence-driven discovery models — facts, tensions, dynamic hypotheses."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.advisor.pipeline.business_systems_models import EvidenceStrength

FactCategory = Literal[
    "outcome",
    "symptom",
    "stakeholder_theory",
    "stated_hypothesis",
    "organizational_change",
    "constraint",
    "scale",
    "timeline",
    "context",
    "technology",
    "economic",
]

TensionKind = Literal[
    "competing_explanations",
    "outcome_contradiction",
    "missing_evidence",
]

HypothesisSource = Literal["stakeholder", "symptom", "outcome", "inferred"]


class ExtractedFact(BaseModel):
    """A single grounded claim from user text."""

    id: str
    category: FactCategory
    text: str
    normalized: str = ""
    source: str = "user"
    confidence: float = 0.85
    evidence_strength: EvidenceStrength = "inferred"
    stakeholder: str | None = None

    def model_post_init(self, __context: object) -> None:
        if not self.normalized:
            self.normalized = self.text.lower().strip()


class DynamicHypothesis(BaseModel):
    """Hypothesis derived from facts — not from a predefined cause catalog."""

    id: str
    label: str
    metric_phrase: str
    source: HypothesisSource
    confidence: float
    supporting_fact_ids: list[str] = Field(default_factory=list)
    evidence_strength: float = 0.0


class Tension(BaseModel):
    """Competing explanations, contradictions, or evidence gaps."""

    kind: TensionKind
    description: str
    hypothesis_ids: list[str] = Field(default_factory=list)
    fact_ids: list[str] = Field(default_factory=list)
    priority: float = 0.5


class EvidenceGap(BaseModel):
    """Unknown that would reduce uncertainty if resolved."""

    id: str
    description: str
    priority: float
    suggested_probe: str = ""


class FactGraph(BaseModel):
    """Structured evidence from conversation — input to discovery reasoning."""

    facts: list[ExtractedFact] = Field(default_factory=list)
    vocabulary: set[str] = Field(default_factory=set)
    primary_outcome: str | None = None
    timeline_phrase: str | None = None
    source_text: str = ""

    def facts_by_category(self, category: FactCategory) -> list[ExtractedFact]:
        return [f for f in self.facts if f.category == category]

    def blob(self) -> str:
        fact_blob = " ".join(f.normalized for f in self.facts)
        if self.source_text:
            return f"{fact_blob} {self.source_text.lower()}".strip()
        return fact_blob


class DiscoveryState(BaseModel):
    """Full evidence-driven discovery snapshot for one turn."""

    fact_graph: FactGraph = Field(default_factory=FactGraph)
    hypotheses: list[DynamicHypothesis] = Field(default_factory=list)
    tensions: list[Tension] = Field(default_factory=list)
    gaps: list[EvidenceGap] = Field(default_factory=list)
    recommended_question: str | None = None
    question_gain_score: float = 0.0
