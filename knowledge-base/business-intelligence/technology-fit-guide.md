# Technology Fit Guide

Used by `technology_fit_engine.py` when recommendation readiness passes. Technology is ranked **after** process, policy, and organizational interventions.

## WHY technology may help
- Repeatable workflow with clear handoffs and measurable volume
- Data already exists but is fragmented across spreadsheets or email
- Constraint profile does not block automation (budget, timeline, regulatory)
- Maturity stage supports tooling (not EARLY-only manual culture)

## WHY NOT technology (yet)
- Root cause is incentive conflict or policy gap — fix politics/process first
- Missing intervention evidence (lead tracking, approval process, collections workflow)
- Regulatory constraint blocks automated decisioning
- Low maturity + high organizational dependency

## Output
`TechnologyFit` records `why_fit`, `why_not`, and `confidence` for each technology-class intervention candidate. Process-first ranking in `intervention_mapper.py` ensures TECHNOLOGY and AI_AUTOMATION score below PROCESS, POLICY, and ORGANIZATIONAL types unless maturity and constraints strongly favor tooling.
