---
Product: ECG Document Intelligence
Category: compliance
Last Updated: 2026-06-01
---

# ECG Compliance and Clinical Data Handling

## Summary

Healthcare compliance considerations for ECG document processing deployments.

## Content

ECG Document Intelligence is designed for healthcare environments where PHI may be present. Deployments should use encrypted transit and storage, access controls, and audit logging aligned with HIPAA requirements. FDA classification of the deployment context depends on intended use (clinical decision support vs. administrative extraction) — customers should validate with their regulatory team. No PHI should be sent to optional external AI services when compliance mode restricts external calls.

## Related Documents

- technical-faq.md
