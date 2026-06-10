# Synthetic Validation Dataset — Overview

**Project:** LMU MSBA × Cedars-Sinai AI Patient Billing Agent  
**Last updated:** June 2026

---

## What This Dataset Is

The synthetic validation dataset is the ground truth used to evaluate the
AI billing agent. It contains 52 labeled test cases, each representing a
realistic patient scenario with a known correct answer. When the agent
responds to a case, its output is compared against the labeled expected
response to measure accuracy.

The dataset was built entirely from scratch — no real patient records were
used. All cases are modeled against official Cedars-Sinai policy documents
and verified for clinical and financial accuracy.

---

## Why Synthetic

Real patient billing records contain Protected Health Information (PHI) —
identifiable patient data that cannot leave the hospital system under HIPAA.
Synthetic data was the only viable approach. Every case reflects real billing
scenarios, real FPL calculations, and real Cedars-Sinai policy, but uses
entirely fictional patient profiles.

---

## Contents

| File | Description |
|---|---|
| `synthetic_validation_dataset.csv` | 52 labeled test cases (answer key for agent evaluation) |
| `generate_final.py` | Reproducible generation script |
| `synthetic_bills/` | 10 JSON bills + 10 PDF bills (agent input format) |

---

## How It Was Built

**Step 1 — Research** ([research-docs/](../research-docs/))  
Comprehensive review of hospital billing fundamentals: revenue cycle, billing
code systems, FPL thresholds, Cedars-Sinai financial assistance policy, common
denial codes, and patient confusion points. This research defined what the
agent needs to know.

**Step 2 — Edge Case Planning** ([edge-cases/patient_billing_synthetic_edge_cases_v2.csv](edge-cases/patient_billing_synthetic_edge_cases_v2.csv))  
34 planned scenarios mapping every FPL boundary condition, insurance type,
document type, and safety constraint the agent must handle. This served as
the blueprint for the final dataset.

**Step 3 — Dataset Generation** ([generate_final.py](generate_final.py))  
A single Python script defines all 52 cases as structured data,
auto-derives the 4 evaluation metric flags per case, writes the CSV, and
runs a built-in FPL audit — recalculating every FPL value from income and
household size to catch errors.

**Step 4 — Synthetic Bills** ([synthetic_bills/](synthetic_bills/))  
10 Cedars-style hospital billing documents (JSON + PDF) created to support
the Document Parsing test cases. Each bill uses real revenue codes, real CPT
codes, and correct financial math.

---

## Dataset Summary

| Field | Value |
|---|---|
| Total cases | 52 |
| Fields per case | 23 |
| Evaluation metric flags | 4 (True/False per case) |
| Synthetic bills | 10 (JSON + PDF) |
| Payer types covered | 5 |
| Knowledge documents referenced | 15 |
| Errors found and corrected | 2 (DV-006, DV-007) |
| Outstanding errors | 0 |

---

## Category Breakdown

| Category | Cases | Scope |
|---|---|---|
| Billing Understanding | 18 | CPT/ICD-10 codes, EOBs, chargemaster, denial codes |
| Financial Assistance | 14 | FPL eligibility, Charity Care vs. Discount Plan routing |
| Safety & Privacy | 8 | PHI handling, legal limits, eligibility disclaimers |
| Action Planning | 7 | Appeals, collections, billing disputes, multi-payer routing |
| Document Parsing | 5 | Field extraction from uploaded JSON/PDF bills |

---

## Evaluation Metric Flags

Each case carries four True/False columns marking which metrics it tests:

| Flag | What it measures |
|---|---|
| `tests_semantic_correctness` | Does the agent explain the right thing? |
| `tests_precision_recall` | Does it extract the correct fields from a document? |
| `tests_hallucination_rate` | Does it fabricate unsupported information? |
| `tests_text_differentiation` | Is the response clear, plain-language, and actionable? |

---

## Synthetic Bills

10 billing documents (JSON + PDF pairs) covering:

- **Self-Pay:** ER visit and inpatient stay (Financial Assistance testing)
- **Medicaid:** ER and outpatient
- **Medicare:** inpatient and observation stay
- **Medicare Advantage:** inpatient and outpatient
- **Commercial:** outpatient and inpatient

JSON is the agent's structured input; PDF simulates what a patient would upload.

---

## FPL Reference (2026)

| Threshold | Assistance Tier |
|---|---|
| ≤ 400% FPL | Charity Care (free or heavily reduced) |
| 401–600% FPL | Discount Payment Plan |
| > 600% FPL | Standard billing (payment plans available) |

**Formula:** $15,960/yr for a 1-person household + $5,680 per additional person  
**Dataset range:** 0% – 689% FPL

---

## Validation Rubric

Before a case is included in the dataset, it must pass all of the following:

| Check | Criteria |
|---|---|
| **Realistic** | Could this scenario plausibly happen to a real Cedars-Sinai patient? |
| **Complete** | Are all required fields populated — no missing values |
| **Internally consistent** | Do FPL %, income, household size, and eligibility tier all agree? |
| **Grounded** | Is every expected response element traceable to a source document? |
| **Safe** | Does the safety_constraint field prevent overconfident or harmful guidance? |
| **Clear** | Is the edge condition being tested unambiguous? |
| **Useful** | Does this case test a meaningful agent capability? |

---

## Reproduction

```bash
cd synthetic-data/
python3 generate_final.py
```

Requires: `csv`, `json`, `os`, `shutil` (stdlib only — no external dependencies for CSV generation). PDF generation requires `reportlab`.
