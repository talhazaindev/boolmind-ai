---
Product: Boolmind Capabilities
Category: routing
Last Updated: 2026-06-08
---

# Product Fit Routing Rules

## Summary

Authoritative routing: which Boolmind offering fits a user need. The advisor must follow these rules to avoid mis-selling catalog products.

## Content

### Route to CUSTOM SOLUTIONS (product_fit: custom_solutions)

- Fleet management systems (track vehicles, maintenance, drivers)
- Driver workload optimization with ML
- Transportation / logistics operations platforms
- Bespoke mobile apps for field or fleet teams
- Industry-specific apps outside retail/clinical/legal/forecasting domains
- Manual processes needing a tailored automated platform

**Do NOT** recommend Retify, ECG, Legal, or Forecasting Engine as the primary fit for these cases. Boolmind **builds** custom solutions.

### Route to RETIFY

- Messy retail POS/ERP/e-commerce data needing unification
- SKU/store/customer entity matching across retail sources
- Retail analytics warehouse preparation

### Route to ECG

- Scanned ECG PDFs, waveforms, clinical document OCR
- EMR-ready cardiac parameter extraction

### Route to LEGAL

- Heterogeneous legal datasets, contracts, regulatory corpora
- Golden schema fusion for legal records

### Route to FORECASTING ENGINE

- Predict future sales/demand with time-series history
- Inventory stockout risk, promotion ROI, weather-driven demand
- Store/category hierarchical forecasting
- Cross-industry demand forecasting when time-series data exists

### Negative examples (critical)

| User need | WRONG fit | CORRECT fit |
|-----------|-----------|-------------|
| Fleet tracking + driver workload ML | Retify or Forecasting | Custom solutions |
| Transportation company scaling ops | ECG or Legal | Custom solutions |
| Retail POS data chaos | Forecasting only | Retify (then maybe Forecasting) |
| Holter PDF extraction | Retify | ECG |

When uncertain, use rag_query on capabilities namespace and ask clarifying questions.

## Related Documents

- company-capabilities.md
