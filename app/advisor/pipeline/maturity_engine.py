"""Business maturity inference — why this problem now."""

from __future__ import annotations

from app.advisor.pipeline.business_systems_models import (
    BusinessMaturity,
    EvidenceStrength,
    MaturityAssessment,
)
from app.advisor.pipeline.discovery_models import FactGraph

_EARLY_SIGNALS = ("startup", "founding", "just launched", "small team", "few employees", "chaos")
_GROWING_SIGNALS = ("growing", "scaling up", "hiring", "expanding", "series a", "series b")
_SCALING_SIGNALS = ("rapid growth", "multiple locations", "headcount doubled", "outgrew")
_MATURE_SIGNALS = ("established", "mature", "years in business", "stable", "profitable")
_ENTERPRISE_SIGNALS = ("enterprise", "bureaucracy", "layers of approval", "global", "fortune")


def infer_maturity(fact_graph: FactGraph) -> MaturityAssessment:
    blob = fact_graph.blob()
    scores: dict[BusinessMaturity, float] = {
        "EARLY": 0.0,
        "GROWING": 0.0,
        "SCALING": 0.0,
        "MATURE": 0.0,
        "ENTERPRISE": 0.0,
    }
    signal_map = {
        "EARLY": _EARLY_SIGNALS,
        "GROWING": _GROWING_SIGNALS,
        "SCALING": _SCALING_SIGNALS,
        "MATURE": _MATURE_SIGNALS,
        "ENTERPRISE": _ENTERPRISE_SIGNALS,
    }
    matched_signals: list[str] = []
    fact_ids: list[str] = []
    for stage, signals in signal_map.items():
        for sig in signals:
            if sig in blob:
                scores[stage] += 0.25
                matched_signals.append(sig)
                for f in fact_graph.facts:
                    if sig in f.normalized:
                        fact_ids.append(f.id)

    for fact in fact_graph.facts_by_category("scale"):
        blob_n = fact.normalized
        if any(s in blob_n for s in ("employee", "arr", "revenue", "location")):
            scores["GROWING"] += 0.15
            fact_ids.append(fact.id)

    if not any(scores.values()):
        scores["GROWING"] = 0.4

    best = max(scores, key=lambda k: scores[k])
    confidence = min(0.9, scores[best] + 0.2)
    strength: EvidenceStrength = "observed" if len(fact_ids) >= 2 else "inferred"
    if confidence < 0.35:
        strength = "speculated"

    return MaturityAssessment(
        stage=best,
        confidence=round(confidence, 2),
        evidence_strength=strength,
        signals=matched_signals[:5],
        evidence_fact_ids=list(dict.fromkeys(fact_ids))[:6],
    )


def maturity_adjusts_intervention_type(
    intervention_type: str,
    maturity: MaturityAssessment,
    symptom: str,
) -> float:
    """Return multiplier for intervention type preference."""
    blob_symptom = symptom.lower()
    if "approval" in blob_symptom or "slow" in blob_symptom:
        if maturity.stage in ("EARLY", "GROWING") and intervention_type == "PROCESS":
            return 1.2
        if maturity.stage in ("MATURE", "ENTERPRISE") and intervention_type == "PROCESS":
            return 1.15
    if maturity.stage == "EARLY" and intervention_type == "TECHNOLOGY":
        return 0.85
    return 1.0
