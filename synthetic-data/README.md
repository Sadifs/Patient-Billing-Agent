# Synthetic Validation Dataset

Evaluation data for the Cedars-Sinai Patient Billing Agent — Sprint 1.

## Contents

| File | Description |
|------|-------------|
| `synthetic_validation_dataset.csv` | 52 labeled test cases (answer key for agent evaluation) |
| `generate_final.py` | Reproducible generation script |
| `synthetic_bills/` | 10 JSON bills + 10 PDF bills (agent input format) |

## Dataset summary

- **52 test cases** across 5 scenario categories
- **5 insurance types**: Commercial (11), Medicare (4), Medicare Advantage (3), Medicaid (4), Uninsured (6), N/A (24)
- **20 fields per case**: patient query, expected response, extracted fields, next steps, FPL calculation, evaluation metric, source doc reference
- **All 15 knowledge-docs/ files** referenced as grounding sources
- **FPL calculations** verified against 2026 HHS federal poverty thresholds

## Categories

| Category | Cases | What it tests |
|----------|-------|---------------|
| Financial Assistance | 14 | FPL eligibility, Charity Care vs. Discount Payment tiers |
| Billing Understanding | 18 | CPT/ICD-10 codes, EOB reading, chargemaster, denial codes |
| Document Parsing | 5 | Bill extraction from JSON/PDF/image inputs |
| Action Planning | 7 | Collections, appeals, multi-payer routing |
| Safety & Privacy | 8 | PHI handling, legal limits, eligibility disclaimers |

## Evaluation metrics (Cedars-defined)

1. **Hallucination Rate** — did the agent state something not in the source documents?
2. **Precision & Recall** — did it extract the correct fields from the bill?
3. **Text Differentiation** — did it tailor the response to this specific patient?

## Bill files

10 synthetic billing documents (JSON + PDF pairs) covering:
- Commercial: outpatient and inpatient
- Medicare: inpatient and observation stay
- Medicare Advantage: inpatient and outpatient
- Medicaid: ER and outpatient
- Uninsured: ER and inpatient (for FAP testing)

Generated with `reportlab`. JSON is the agent's structured input; PDF simulates what a patient would upload.

## Reproduction

```bash
cd synthetic-data/
python3 generate_final.py
```

Requires: `csv`, `json`, `os`, `shutil` (stdlib only — no external dependencies for CSV generation). PDF generation requires `reportlab`.
