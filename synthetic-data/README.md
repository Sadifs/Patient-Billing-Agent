# Synthetic Validation Dataset — Overview

**Project:** LMU MSBA × Cedars-Sinai AI Patient Billing Agent  
**Last updated:** June 2026

---

## What This Dataset Is

The synthetic validation dataset is the ground truth used to evaluate the AI
billing agent. It contains **70 labeled test cases** across two dataset versions:

| Version | Cases | Focus |
|---------|-------|-------|
| **V1** | 45 | Text-input scenarios, billing literacy, FAP routing, safety |
| **V2** | 25 | Document-linked bills with diversified patient financial profiles |

Seven v1 document cases (DV-001, DV-002, DV-005–DV-009) were superseded by v2
bills and are excluded from v1 to keep the combined total at **70 patients**.

When the agent responds to a case, its output is compared against the labeled
expected response to measure accuracy.

All cases use fictional patient profiles — no real PHI.

---

## Contents

| File / Folder | Description |
|---|---|
| `synthetic_validation_dataset.csv` | **Master — 60 labeled test cases (v1 + v2 combined). Use this.** |
| `generate_final.py` | Regenerates v1 CSV |
| `generate_v2_bills.py` | Regenerates v2 bill JSON (evaluator + agent copies) |
| `generate_v2_csv.py` | Regenerates v2 validation CSV |
| `merge_validation_datasets.py` | Combines v1 + v2 into combined CSV |
| `generate_all.py` | Runs all generators in order |
| `edge-cases/` | Planning CSVs for v1 and v2 edge scenarios |
| `synthetic_bills/` | V1 — 10 JSON + 10 PDF bills |
| `synthetic_bills_v2/` | V2 — 15 evaluator bills (full metadata) |
| `synthetic_bills_v2_agent/` | V2 — 15 LLM-safe bills (metadata stripped) |

---

## V1 vs V2

### V1 (`synthetic_bills/` + 45-case CSV)

- Text-input and document-parsing scenarios
- 10 Cedars-style bills (JSON + PDF)
- Covers billing understanding, FAP, safety, action planning

### V2 (`synthetic_bills_v2/` + 25-case CSV)

- Cedars-style patient statement schema v2.0 (guarantor, summary of services, patient services contact)
- **25 bills** with expanded insurance taxonomy (HDHP, dual eligible, TRICARE, Workers Comp, COB, collections, FAP-approved, surprise billing, payment plans, etc.)
- Diversified patient profiles in CSV (household size, income, FPL tier)
- Bill JSON has **no FAP ground truth** — evaluation metadata lives in CSV only
- `synthetic_bills_v2_agent/` strips `_schema_version`, `_note`, `_intentional_error_note` before LLM use

---

## Dataset Summary

| Field | V1 | V2 | Combined |
|---|---|---|---|
| Total cases | 45 | 25 | **70** |
| Fields per case | 23 | 23 | 23 |
| Synthetic bills | 10 (JSON+PDF) | 25 (JSON+PDF) | 35 unique bill sets |
| FPL range | 0% – 689% | 85% – 533% | 0% – 689% |

---

## Category Breakdown (Combined)

| Category | V1 | V2 | Total |
|---|---|---|---|
| Financial Assistance | 12 | 9 | 21 |
| Billing Understanding | 15 | 9 | 24 |
| Safety & Privacy | 8 | 1 | 9 |
| Action Planning | 6 | 5 | 11 |
| Document Parsing | 4 | 1 | 5 |

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

Regenerate everything:

```bash
cd synthetic-data/
python3 generate_all.py
```

Or run individually:

```bash
python3 generate_final.py              # v1 CSV
python3 generate_v2_bills.py           # v2 bills (evaluator + agent)
python3 generate_v2_csv.py             # v2 CSV
python3 merge_validation_datasets.py   # combined CSV
```

Requires: `csv`, `json`, `os`, `shutil` (stdlib only).

---

## Which Bills to Pass to the Agent

| Dataset | Use this folder |
|---|---|
| V1 document cases (DV-001 – DV-010) | `synthetic_bills/` |
| V2 document cases (DV2-001 – DV2-025) | `synthetic_bills_v2_agent/` |

Use `synthetic_validation_dataset.csv` as the master answer key (**70 patients**).

### V1 cases superseded by V2 (excluded from v1 CSV)

| Removed | Replaced by |
|---------|-------------|
| DV-001 | DV2-001 (self-pay ER) |
| DV-002 | DV2-002 (self-pay inpatient) |
| DV-005 | DV2-005 (Medicare inpatient) |
| DV-006 | DV2-006 (Medicare observation) |
| DV-007 | DV2-007 (Medicare Advantage denied) |
| DV-008 | DV2-008 (MA copay discrepancy) |
| DV-009 | DV2-009 (Medi-Cal ER) |
