---
namespace: business_intelligence
dimension: throughput
hypothesis_id: exception_handling_gap
pattern: automation_failure
---

# Automation Failure Modes

Common pattern: automation deployed → misses exceptions → analysts lose trust → revert to email/manual.

**Exception handling gap** — edge cases (unusual document types, multi-entity financials, non-standard formats) not routed to human review.

**Trust collapse** — one visible failure causes team to bypass tool entirely.

**Change management** — adoption poor when workflow change not paired with exception path.

Differentiating question: Was failure mostly unusual document types, or standard items the system misread?

Do not recommend automation until exception routing is understood.
