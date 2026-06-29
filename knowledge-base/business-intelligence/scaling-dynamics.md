---
namespace: business_intelligence
dimension: throughput
pattern: scaling_dynamics
---

# Scaling Dynamics

When volume grows faster than capacity, queues form even if per-unit processing time is unchanged (Little's Law intuition).

**Backlog math:** backlog size ÷ daily volume ≈ days of work sitting in queue.

**Delay delta:** current turnaround minus historical baseline = new delay to explain.

Use these inferences in acknowledgment before asking the next question — it shows you listened to their numbers.

Signs of scaling failure: manual processes that worked at lower volume, coordinator/planner headcount not keeping pace, peak-period spikes exposing planning gaps.
