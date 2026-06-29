---
Product: Forecasting Engine
Category: technical-faq
Last Updated: 2026-06-08
---

# Forecasting Engine Technical FAQ

## Summary

Common technical questions about deployment, data inputs, and integrations.

## Content

**What data do I need?** Historical sales transactions (date, store, SKU, quantity, revenue), optional inventory levels, promotion calendars, and store attributes. Minimum 12–24 months of history recommended for retail.

**Can it run on-prem?** Yes—Docker-based deployment with PostgreSQL; cloud and hybrid options available.

**How does it differ from Retify?** Retify unifies and cleans multi-format retail data into a warehouse. Forecasting Engine consumes structured time-series data (often from a warehouse Retify built) to predict future demand.

**Does it optimize driver routes or fleet workload?** No. Transportation fleet management and driver scheduling require **custom applied-AI solutions** from Boolmind—not this product.

**Integrations:** CSV/Parquet bulk load, REST APIs, optional connectors to POS/ERP exports and weather providers.

**Latency:** Batch forecast jobs for planning cycles; near-real-time refresh for operational dashboards depending on deployment.

## Related Documents

- features.md
- retail-use-cases.md
