# Synthetic Validation Dataset V2 — Overview

**Project:** LMU MSBA × Cedars-Sinai AI Patient Billing Agent  
**Last updated:** June 2026

---

## What This Dataset Is

V2 is an expanded synthetic billing dataset for evaluating the AI patient billing
agent. It pairs **15 Cedars-style patient statement JSON bills** with **15 labeled
validation cases** that include diversified patient financial profiles (household
size, income, FPL tier, language, documentation edge cases).

Bill JSON files contain **only what a patient would receive** — no FPL %, FAP flags,
or evaluation metadata. Ground truth lives in the validation CSV.

---

## V1 → V2 File Mapping


| V1 file                                       | V2 equivalent                                       |
| --------------------------------------------- | --------------------------------------------------- |
| `generate_final.py`                           | `generate_v2_bills.py` + `generate_v2_csv.py`       |
| `synthetic_validation_dataset.csv`            | `synthetic_validation_dataset_v2.csv`               |
| `synthetic_bills/`                            | `synthetic_bills_v2/` + `synthetic_bills_v2_agent/` |
| `billing_fundamentals_edge_cases.csv`         | `edge-cases/billing_fundamentals_edge_cases_v2.csv` |
| `patient_billing_synthetic_edge_cases_v1.csv` | `edge-cases/patient_billing_synthetic_edge_cases_v1.csv` |
| `patient_billing_synthetic_edge_cases_v2.csv` | `edge-cases/patient_billing_synthetic_edge_cases_v2.csv` |
| `README.md`                                   | `README.md` (this file)                             |


---

## Contents


| File                                          | Description                                                                  |
| --------------------------------------------- | ---------------------------------------------------------------------------- |
| `synthetic_validation_dataset_v2.csv`         | 15 labeled document-linked test cases (answer key)                           |
| `generate_v2_bills.py`                        | Generates 15 patient-facing JSON bills                                       |
| `generate_v2_csv.py`                          | Generates validation CSV with patient profiles + FPL audit                   |
| `synthetic_bills_v2/`                         | 15 JSON bills — evaluator copies (includes `_schema_version`, `_note`, etc.) |
| `synthetic_bills_v2_agent/`                   | 15 JSON bills — **pass these to the LLM** (metadata stripped)                |
| `edge-cases/billing_fundamentals_edge_cases_v2.csv` | Billing code / document-type edge case planning |
| `edge-cases/patient_billing_synthetic_edge_cases_v1.csv` | Early synthetic scenario planning (reference) |
| `edge-cases/patient_billing_synthetic_edge_cases_v2.csv` | FPL / FAP edge case planning blueprint |


---

## What V2 Adds vs V1

1. **Cedars-style bill schema v2.0** — guarantor block, summary of services, patient services contact
2. **15 bills** (up from 10) covering expanded insurance taxonomy (HDHP, dual eligible, TRICARE, Workers Comp, etc.)
3. **Diversified patient profiles** — each bill paired with household size, income, and FPL tier in the CSV
4. **Clean bill / dirty CSV split** — FAP ground truth is CSV-only; agent bills omit `_schema_version`, `_note`, and `_intentional_error_note`
5. **Math audit** — bills verified at generation; one intentionally incorrect bill tests error detection

---

## Dataset Summary


| Field                   | Value                                              |
| ----------------------- | -------------------------------------------------- |
| Total cases             | 15                                                 |
| Fields per case         | 23                                                 |
| Evaluation metric flags | 4 (True/False per case)                            |
| Synthetic bills         | 15 (JSON)                                          |
| FPL range covered       | 85% – 533% (+ N/A for Medi-Cal verify-first cases) |


---

## Category Breakdown


| Category              | Cases | Scope                                                                     |
| --------------------- | ----- | ------------------------------------------------------------------------- |
| Financial Assistance  | 5     | FPL routing, Charity Care vs Discount Payment, Spanish-speaking           |
| Billing Understanding | 5     | Observation status, copay discrepancy, wellness reclassification, TRICARE |
| Action Planning       | 3     | MA denial appeal, No Surprises Act, Workers Comp routing                  |
| Safety                | 1     | Medi-Cal verify-before-pay                                                |
| Document Parsing      | 1     | Intentionally incorrect bill math                                         |


---

## FPL Reference (2026)


| Threshold    | Assistance Tier                            |
| ------------ | ------------------------------------------ |
| ≤ 400% FPL   | Charity Care (free or heavily reduced)     |
| 401–600% FPL | Discount Payment Plan                      |
| > 600% FPL   | Standard billing (payment plans available) |


**Formula:** $15,960/yr for a 1-person household + $5,680 per additional person

---

## Reproduction

```bash
cd synthetic-data-v2/
python3 generate_v2_bills.py
python3 generate_v2_csv.py
```

Requires: `csv`, `json`, `os` (stdlib only).

---

## Evaluation Metric Flags


| Flag                         | What it measures                                       |
| ---------------------------- | ------------------------------------------------------ |
| `tests_semantic_correctness` | Does the agent explain the right thing?                |
| `tests_precision_recall`     | Does it extract the correct fields from a document?    |
| `tests_hallucination_rate`   | Does it fabricate unsupported information?             |
| `tests_text_differentiation` | Is the response clear, plain-language, and actionable? |


