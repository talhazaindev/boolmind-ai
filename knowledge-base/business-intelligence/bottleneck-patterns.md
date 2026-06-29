---
namespace: business_intelligence
dimension: throughput
universal_stage: quality_gate
hypothesis_id: queue_saturation
pattern: manual_handoff
---

# Bottleneck Patterns (Industry-Agnostic)

**Queue saturation** — backlog grows faster than processing capacity; common at quality_gate and compliance review.

**Manual handoff** — information passes via email or spreadsheets between teams; each handoff adds delay and error risk.

**Capacity ceiling** — headcount cannot match volume growth; analysts or coordinators become the bottleneck.

**Data re-entry** — same facts entered in multiple systems; doubles handling time.

**Prioritization gap** — no rules for which items in queue get processed first (FIFO vs risk tier vs size).

**Rework loop** — exceptions bounce back to earlier stages instead of being routed to specialists.

Differentiating question: Is the delay mostly queue volume, or rework caused by exceptions?
