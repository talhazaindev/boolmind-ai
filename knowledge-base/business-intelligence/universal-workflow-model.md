---
namespace: business_intelligence
dimension: throughput
pattern: universal_workflow
---

# Universal Workflow Model

Every business operation maps to six universal stages:

1. **intake** — request, order, application, or lead arrives
2. **preparation** — gather inputs, plan, verify, onboard
3. **execution** — core processing, analysis, dispatch, production
4. **quality_gate** — compliance, QC, review, approval checkpoint
5. **delivery** — outcome delivered to customer (approval, shipment, value)
6. **exception_loop** — rework, missing items, escalations, reversions to manual

Diagnostic rule: locate which stage has the longest queue or highest manual effort. Slowdowns rarely affect all stages equally — ask which stage feels worst before solutioning.

hypothesis_id: manual_handoff — teams coordinate outside systems between stages.
hypothesis_id: queue_saturation — volume exceeds capacity at quality_gate or execution.
