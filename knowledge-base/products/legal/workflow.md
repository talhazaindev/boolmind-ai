---
Product: Legal Data Fusion
Category: workflow
Last Updated: 2026-06-01
---

# Legal Data Fusion — 6-Step Workflow

## Summary

Six-step orchestrated pipeline from raw legal datasets to harmonized golden records.

## Content

### Step 1 — Ingest

Select datasets from catalog or uploads (CSV, JSON, XLSX). Establishes pipeline inputs without transformation.

### Step 2 — Discovery

Standardizes structure to flat JSON, generates LLM semantic metadata per dataset (descriptions, types, examples), and runs basic diagnostics.

### Step 3 — Clustering

Groups datasets representing the same business concept using LLM semantic comparison and leader–follower clustering.

### Step 4 — Diagnosis

LLM agents detect redundant concepts, type mismatches, and incorrect semantic alignments with severity classification.

### Step 5 — Resolution

Human-in-the-loop review: accept mappings, apply fixes, define rules; may trigger reprocessing.

### Step 6 — Golden Record Fusion

LLM proposes Golden Schema per cluster, maps columns, merges records with conflict logging and source traceability.

## Related Documents

- features.md
- security.md
