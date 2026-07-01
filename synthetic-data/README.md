# Synthetic Validation Dataset — Overview

**Project:** LMU MSBA × Cedars-Sinai AI Patient Billing Agent  
**Last updated:** July 2026

---

## What This Dataset Is

The synthetic validation dataset is the ground truth used to evaluate the AI
billing agent. It contains **70 labeled test cases** across two dataset versions:

| Version | Cases | Focus |
|---------|-------|-------|
| **V1** | 42 | Text-input scenarios, billing literacy, FAP routing, safety |
| **V2** | 28 | Document-linked bills with diversified patient financial profiles |

Ten v1 document cases (DV-001 – DV-010) were superseded by v2 bills and
are excluded from v1 to keep the combined total at **70 patients**.

When the agent responds to a case, its output is compared against the labeled
expected response to measure accuracy.

All cases use fictional patient profiles — no real PHI.

---

## Contents

| File / Folder | Description |
|---|---|
| `synthetic_validation_dataset.csv` | **Master — 70 labeled test cases (v1 + v2 combined). Use this.** |
| `generate_v2_bills.py` | Regenerates v2 bill JSON for bills 01–15 (evaluator + agent copies) |
| `generate_v2_csv.py` | Regenerates v2 validation CSV for bills 01–15 |
| `generate_new_bills.py` | Generates v2 bills 16–25 (reproducible) |
| `generate_v2_pdfs.py` | Generates PDFs for all v2 bills from JSON |
| `edge-cases/` | Planning CSVs for v1 and v2 edge scenarios (reference) |
| `synthetic_bills_v2/` | V2 — 28 evaluator bills (JSON + PDF, full metadata) |
| `synthetic_bills_v2_agent/` | V2 — 28 LLM-safe bills (JSON, metadata stripped) |

---

## V1 vs V2

### V1 (42-case CSV, text-input only)

- Text-input and document-parsing scenarios
- No bill files — all cases are text-based patient questions
- Covers billing understanding, FAP routing, safety, action planning

### V2 (`synthetic_bills_v2/` + 28-case CSV)

- Cedars-style patient statement schema v2.0 (guarantor, summary of services, patient services contact)
- **28 bills** with expanded insurance taxonomy (HDHP, dual eligible, TRICARE, Workers Comp, COB, collections, FAP-approved, surprise billing, payment plans, Medi-Cal share of cost, etc.)
- Diversified patient profiles in CSV (household size, income, FPL tier)
- Bill JSON has **no FAP ground truth** — evaluation metadata lives in CSV only
- `synthetic_bills_v2_agent/` strips `_schema_version`, `_note`, `_intentional_error_note` before LLM use

---

## Dataset Summary

| Field | V1 | V2 | Combined |
|---|---|---|---|
| Total cases | 42 | 28 | **70** |
| Fields per case | 23 | 23 | 23 |
| Synthetic bills | 0 | 28 (JSON+PDF) | 28 unique bill sets |
| FPL range | 0% – 689% | 85% – 533% | 0% – 689% |

---

## Category Breakdown (Combined)

| Category | V1 | V2 | Total |
|---|---|---|---|
| Financial Assistance | 12 | 11 | 23 |
| Billing Understanding | 15 | 11 | 26 |
| Safety & Privacy | 8 | 1 | 9 |
| Action Planning | 6 | 5 | 11 |
| Document Parsing | 1 | 0 | 1 |

---

## FPL Reference (2026)

| Threshold | Assistance Tier |
|---|---|
| ≤ 400% FPL | Charity Care (free or heavily reduced) |
| 401–600% FPL | Discount Payment Plan |
| > 600% FPL | Standard billing (payment plans available) |

**Formula:** $15,960/yr for a 1-person household + $5,680 per additional person

---

## Reproduction

Regenerate PDFs for all v2 bills:

```bash
cd synthetic-data/
python3 generate_v2_pdfs.py
```

Regenerate bills 16–25 JSON (evaluator + agent):

```bash
python3 generate_new_bills.py
```

Requires: `csv`, `json`, `os`, `reportlab` (PDFs only).

---

## Which Bills to Pass to the Agent

| Dataset | Use this folder |
|---|---|
| V2 document cases (DV2-001 – DV2-028) | `synthetic_bills_v2_agent/` |

Use `synthetic_validation_dataset.csv` as the master answer key (**70 patients**).

---

## V1 Cases Superseded by V2

All 10 original v1 document cases were migrated to v2 format. The `synthetic_bills/`
folder has been removed — use `synthetic_bills_v2/` for all document cases.

| V1 Case | Replaced by |
|---------|-------------|
| DV-001 | DV2-001 (self-pay ER) |
| DV-002 | DV2-002 (self-pay inpatient) |
| DV-003 | DV2-026 (commercial outpatient – contractual adjustment) |
| DV-004 | DV2-027 (commercial inpatient – OON anesthesia) |
| DV-005 | DV2-005 (Medicare inpatient) |
| DV-006 | DV2-006 (Medicare observation + Medigap) |
| DV-007 | DV2-007 (Medicare Advantage denied) |
| DV-008 | DV2-008 (MA copay discrepancy) |
| DV-009 | DV2-009 (Medi-Cal ER) |
| DV-010 | DV2-028 (Medi-Cal outpatient – share of cost) |
