---
namespace: business_intelligence
pattern: hypothesis_ranking
---

# Hypothesis Ranking Guide

Generate 3–5 competing root-cause hypotheses from symptoms. Rank by confidence but keep top 2 close enough to require a discriminating question.

Confidence rules:
- User-stated fact (volume, backlog, manual step) → confidence ≥ 0.7
- Inferred from pattern → confidence 0.45–0.65
- Speculative → below 0.4; do not ask about until higher hypotheses ruled out

Reject hypothesis when user provides contradicting evidence. Narrow gap between #1 and #2 before solutioning.

Shared hypothesis IDs: queue_saturation, exception_handling_gap, manual_handoff, capacity_ceiling, data_reentry, prioritization_gap, ocr_accuracy.
