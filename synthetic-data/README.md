# Synthetic Validation Dataset — Overview

**Project:** LMU MSBA × Cedars-Sinai AI Patient Billing Agent  
**Last updated:** July 2026

---

## Start Here for Review

If you're reviewing this dataset (Cedars team, faculty, or a new contributor), you only need two things:

- **`synthetic_validation_dataset.csv`** — the master answer key, 135 labeled test cases
- **`synthetic_validation_dataset_realistic_pdf_workflow.csv`** — optional evaluation copy where PDF cases use a realistic first turn (`Can you explain this bill?`) and move the original case-specific prompt to the follow-up turn
- **`synthetic_bills_v2/`** — the 70 full synthetic bills (JSON + PDF) those cases reference, including the expected-answer metadata

Everything else in this folder (`scripts/`, `build-artifacts/`, `edge-cases/`, `synthetic_bills_v2_agent/`) is either build tooling that produced the two items above, or a metadata-stripped copy used internally to feed the agent without exposing its own answer key. See **Contents** below for what each one is.

---

## What This Dataset Is

The synthetic validation dataset is the ground truth used to evaluate the AI
billing agent. It contains **135 labeled test cases** spanning two case
**types** (not to be confused with the dataset's chronological v1/v2/v3/v4
growth — see **Version History** below):

| Case type | Cases | Focus |
|---------|-------|-------|
| **Text-only** (`FA-`, `BILL-`, `SAF-`, `ACT-`, `DOC-` prefixes) | 65 | Text-input scenarios, billing literacy, FAP routing, safety, multi-turn, adversarial |
| **Document-linked** (`DV2-` prefix) | 70 | Bills (JSON + PDF) with diversified patient financial profiles |

Ten early text-only cases (DV-001 – DV-010) were retired once document-linked
bills covered the same ground. Other text-only cases that duplicated
document-linked coverage were consolidated during the dataset's v3 expansion
(100 cases, 70 bills). A later v4 round added 35 more text-only cases (15
multi-turn, 20 adversarial) to close specific coverage gaps — see **Version
History** below and `evaluation/coverage_matrix.md` for what those gaps were.

When the agent responds to a case, its output is compared against the labeled
expected response to measure accuracy.

All cases use fictional patient profiles — no real PHI.

---

## Version History

The filenames and folder names in this dataset still say "v2" throughout
(`synthetic_bills_v2/`, `bill_v2_*.json`, etc.), which is a **different use of
"v1/v2" than the case-type table above** — this section is about the
dataset's chronological growth, confirmed against actual commit history:

| Date | Milestone | Cases | Bills | What happened |
|---|---|---|---|---|
| 2026-06-08 | v1 | 52 | 0 | Original text-only dataset (Sprint 1 foundation) |
| 2026-06-24 | v2 (built separately) | — | 15 | A separate `synthetic-data-v2/` folder was built in parallel with its own bills |
| 2026-06-30 | v1 + v2 **merged** | 60 | 15 | The two folders were combined into one `synthetic-data/`; 7 v1 cases retired as superseded by the new bills |
| 2026-07-01 | **expanded** | 72 | 30 | 15 more document-linked bills added to the merged dataset |
| 2026-07-07 | v3 | 100 | 70 | 40 more bills + 24 more text-only cases added (commit literally titled "Expand ... to v3") |
| 2026-07-28 | v4 (current) — **expanded** | **135** | **70** | 15 multi-turn + 20 adversarial text-only cases added, closing specific gaps found via a modality × scenario × payer coverage matrix (Prof. Vo's parser-vs-gold feedback, item 2) — see `evaluation/coverage_matrix.md` |

So: there was exactly **one real merge** (06-30, two folders becoming one),
followed by **two rounds of pure expansion** (07-01, 07-07) of that single
unified dataset — nothing has been "combined" since 06-30. `synthetic_bills_v2/`
and `synthetic_validation_dataset.csv` are both live today; there is no
separate "v1 folder" or "v2 folder" left to browse.

The "v2" naming in files/folders stuck from the 06-24/06-30 milestone above and
was never updated through the later expansions. If this dataset expands again,
consider dropping the version number entirely (there's nothing left to
disambiguate it from) rather than bumping to "v4."

---

## Contents

| File / Folder | Description |
|---|---|
| `synthetic_validation_dataset.csv` | **Master — 135 labeled test cases (current, fully expanded). Use this.** |
| `synthetic_validation_dataset_realistic_pdf_workflow.csv` | **Evaluation copy — same 135 cases, but PDF-modality cases start with `Can you explain this bill?` and move the original patient prompt into `patient_followup`; text-modality cases are unchanged.** |
| `synthetic_bills_v2/` | 70 evaluator bills (JSON + PDF, full metadata) — the actual bill files the master CSV references |
| `synthetic_bills_v2_agent/` | 70 LLM-safe bills (JSON, metadata stripped) — same bills, answer-key fields removed, safe to feed the agent |
| `edge-cases/` | Planning CSVs for v1 and v2 edge scenarios (reference, not used in evaluation) |
| `build-artifacts/synthetic_validation_dataset_v1_new24.csv` | Build artifact — 24 V1 text cases, already merged into master. Do not use directly. |
| `build-artifacts/synthetic_validation_dataset_v2_31_70.csv` | Build artifact — V2 cases DV2-031–070, already merged into master. Do not use directly. |
| `scripts/generate_v2_bills.py` | Regenerates v2 bill JSON for bills 01–15 (evaluator + agent copies) |
| `scripts/generate_v2_csv.py` | Regenerates v2 validation CSV for bills 01–15 |
| `scripts/generate_new_bills.py` | Generates v2 bills 16–25 (reproducible) |
| `scripts/generate_bills_31_70.py` | Generates v2 bills 31–70 (evaluator + agent copies) |
| `scripts/generate_v1_text_24.py` | Generates 24 new v1 text-only validation cases |
| `scripts/merge_expand_dataset.py` | Rebuilds master CSV after expansion |
| `scripts/generate_v2_pdfs.py` | Generates PDFs for all v2 bills from JSON |

All scripts in `scripts/` are meant to be run from the `synthetic-data/` directory (see **Reproduction** below), not from inside `scripts/` itself.

---

## Case Types: Text-Only vs Document-Linked

This section describes the two case **types** that make up today's single
135-case dataset — not the chronological v1/v2/v3/v4 growth covered in
**Version History** above.

### Optional realistic PDF workflow CSV

`synthetic_validation_dataset_realistic_pdf_workflow.csv` is a copy of the
master dataset for testing a more realistic uploaded-bill conversation flow.
It does **not** replace `synthetic_validation_dataset.csv`.

For rows where `modality = pdf`:

- `patient_input` is changed to `Can you explain this bill?`
- the original case-specific `patient_input` is moved into `patient_followup`
- any original follow-up is preserved after the moved prompt

For rows where `modality = text`:

- `patient_input` and `patient_followup` are unchanged, because there is no
  uploaded bill file and the text itself is the patient-provided context

Use this copy when you want to evaluate the user-like workflow: upload PDF
first, ask for a general explanation, then ask the case-specific follow-up.
The expected response columns are intentionally unchanged from the master
dataset. For this workflow copy, treat `expected_agent_response_summary`,
`expected_extracted_fields`, `expected_next_steps`, and `safety_constraint` as
expectations for the **final conversation response** after the follow-up turn,
not only the first generic `Can you explain this bill?` response.

### Text-only cases (65 cases, no bill files)

- Text-input and document-parsing scenarios
- No bill files — all cases are text-based patient questions
- Covers billing understanding, FAP routing, safety, action planning
- Includes 24 new cases (FA-013 – SAF-011) added July 2026

### Document-linked cases (70 cases, `synthetic_bills_v2/`)

- Cedars-style patient statement schema v2.0 (guarantor, summary of services, patient services contact)
- **70 bills** with expanded insurance taxonomy (HDHP, dual eligible, TRICARE, Workers Comp, COB, collections, FAP-approved, surprise billing, payment plans, Medi-Cal share of cost, POS, PFFS-MA, D-SNP, CHAMPVA, IRMAA, oncology, NICU, air ambulance, etc.)
- Diversified patient profiles in CSV (household size, income, FPL tier)
- Bill JSON has **no FAP ground truth** — evaluation metadata lives in CSV only
- `synthetic_bills_v2_agent/` strips `_schema_version`, `_note`, `_intentional_error_note` before LLM use

---

## V2 Bill Inventory (DV2-001 – DV2-070)

Each V2 bill is a Cedars-Sinai–style patient statement (JSON + PDF) covering a distinct insurance scenario. The evaluator folder (`synthetic_bills_v2/`) contains full metadata; the agent folder (`synthetic_bills_v2_agent/`) has evaluation fields stripped.

| Case ID | File (prefix: `bill_v2_`) | Insurance | Scenario | Key Teaching Point |
|---|---|---|---|---|
| DV2-001 | `selfpay_er_01` | None (self-pay) | ER visit – abdominal pain | Full chargemaster bill; AGB & FAP screening needed |
| DV2-002 | `selfpay_inpatient_02` | None (self-pay) | Inpatient appendectomy | Full chargemaster; FAP eligibility at ~94% FPL |
| DV2-003 | `commercial_ppo_outpatient_03` | Anthem PPO | Outpatient MRI + office visit | Copay/coinsurance after deductible |
| DV2-004 | `commercial_hdhp_oon_anesthesia_04` | UHC HDHP | Knee replacement – OON anesthesiologist | No Surprises Act; balance billing for OON provider |
| DV2-005 | `medicare_traditional_inpatient_05` | Medicare A+B | Hip replacement inpatient | DRG payment; Part A deductible = $1,632 (2026) |
| DV2-006 | `medicare_medigap_observation_06` | Medicare + Medigap Plan G | 72-hr observation stay | Observation ≠ inpatient; outpatient drugs not covered by Medigap |
| DV2-007 | `medicare_advantage_denied_07` | Humana Gold HMO (MA) | Spinal fusion – claim denied | Prior auth denial; $107K pending; 180-day appeal right |
| DV2-008 | `medicare_advantage_copay_discrepancy_08` | Kaiser Senior Advantage (MA) | Intravitreal injection (Lucentis) | Billed copay ($600) differs from expected copay ($200) |
| DV2-009 | `medicaid_er_09` | Medi-Cal FFS | ER visit – standard Medi-Cal | Safety scenario; patient balance unusual for Medi-Cal |
| DV2-010 | `medicaid_share_of_cost_10` | Medi-Cal Share of Cost | Colonoscopy with biopsy | Share of Cost as monthly deductible mechanism |
| DV2-011 | `dual_eligible_snf_11` | Medicare + Medi-Cal (dual) | SNF days 21–25 | Dual eligible = $0 balance; Medicare primary, Medi-Cal fills gap |
| DV2-012 | `commercial_wellness_reclassified_12` | Blue Shield HMO | Annual wellness visit reclassified | Preventive→diagnostic reclassification; unexpected patient balance |
| DV2-013 | `intentionally_incorrect_math_13` | Cigna EPO | Lab panel – intentional math error | Outstanding ($260) ≠ patient balance ($960); agent should flag discrepancy |
| DV2-014 | `tricare_outpatient_14` | TRICARE Prime | Prenatal visit + obstetric ultrasound | Active duty dependent; $0 patient balance |
| DV2-015 | `workers_comp_er_15` | State Compensation Fund | ER – workplace hand laceration | Workers' comp pays 100%; $0 patient balance |
| DV2-016 | `complex_cardiac_inpatient_16` | Blue Shield PPO | Cardiac inpatient – PCI + stents | High-complexity multi-line bill; FAP at ~337% FPL |
| DV2-017 | `maternity_inpatient_17` | Anthem HMO | Vaginal delivery + newborn | Guarantor = spouse; maternity coverage; epidural |
| DV2-018 | `secondary_insurance_cob_18` | Cigna PPO + Kaiser (secondary COB) | Laparoscopic colon resection | Coordination of Benefits; secondary insurance credit |
| DV2-019 | `medicare_partb_outpatient_19` | Medicare Part B | Colonoscopy + polypectomy | 80/20 Part B split; FAP eligible at ~105% FPL |
| DV2-020 | `medicaid_outpatient_20` | L.A. Care (Medi-Cal MC) | Outpatient physical therapy | Small copay; FAP eligible at ~90% FPL |
| DV2-021 | `collections_selfpay_21` | None (collections) | ER appendectomy – sent to collections | Patient FAP-eligible (~257% FPL) but never applied; retroactive FAP |
| DV2-022 | `eob_commercial_22` | UHC PPO | Cardiac inpatient – EOB reading | Tests agent's ability to explain EOB components |
| DV2-023 | `fap_approved_zero_balance_23` | None → FAP applied | ER respiratory – FAP already approved | Zero balance because FAP applied; agent must recognize this |
| DV2-024 | `surprise_balance_billing_24` | Aetna PPO | Hip replacement – OON assistant surgeon | No Surprises Act dispute; OON surprise billing; ~555% FPL |
| DV2-025 | `selfpay_payment_plan_25` | None (payment plan active) | Lumbar spinal fusion | Active payment plan; prior payments credited; FAP eligible (~264% FPL) |
| DV2-026 | `commercial_outpatient_contractual_26` | Cigna PPO | Outpatient imaging – contractual adj | Large contractual adjustment; deductible scenario |
| DV2-027 | `commercial_inpatient_oon_anesthesia_27` | Aetna PPO | Knee replacement – OON anesthesia | Balance billing for OON anesthesiologist; No Surprises Act |
| DV2-028 | `medicaid_share_of_cost_colonoscopy_28` | Molina (Medi-Cal MC) | Colonoscopy – share of cost | Medi-Cal managed care + contractual adj + SOC; FAP eligible (~116% FPL) |
| DV2-029 | `pediatric_er_appendectomy_29` | Anthem PPO | Pediatric ER appendectomy | Minor patient; FAP eligibility based on parent (guarantor) income |
| DV2-030 | `prior_auth_denial_30` | Kaiser HMO | MRI studies – prior auth denied | Denial pending appeal; patient near FAP threshold (~388% FPL) |
| DV2-031 | `commercial_pos_outpatient_31` | Health Net POS | Outpatient POS tier cost-sharing | In-network vs out-of-network POS rules |
| DV2-032 | `medicare_advantage_pffs_32` | PFFS MA | Cardiology outpatient | PFFS 20% coinsurance pattern |
| DV2-033 | `medicare_advantage_snp_33` | D-SNP + Medi-Cal | Endocrinology visit | Dual special needs plan coordination |
| DV2-034 | `medicaid_pending_er_34` | None (Medi-Cal pending) | ER + CT | Do not pay while Medi-Cal pending |
| DV2-035 | `medicare_irmaa_partb_35` | Medicare Part B | Outpatient surgery | IRMAA affects premium not claim payment |
| DV2-036 | `champva_outpatient_36` | CHAMPVA | Rheumatology | VA family coverage vs Cedars FAP |
| DV2-037 | `commercial_epo_inpatient_37` | Oscar EPO | Appendectomy inpatient | EPO in-network cost-sharing |
| DV2-038 | `marketplace_silver_plan_38` | Covered CA Silver | Urgent care | Marketplace ACA cost-sharing + FAP |
| DV2-039 | `cobra_continuation_39` | COBRA PPO | MRI after job loss | FAP uses current income ($0) |
| DV2-040 | `hdhp_family_deductible_40` | UHC HDHP family | Pediatric ER | Family deductible not met |
| DV2-041 | `oncology_infusion_41` | Anthem PPO | Chemotherapy infusion | High-cost specialty drug coinsurance |
| DV2-042 | `mental_health_inpatient_42` | Cigna PPO | Psychiatric inpatient | Behavioral health + empathy + FAP |
| DV2-043 | `dialysis_outpatient_43` | Medicare ESRD + Medigap N | Hemodialysis | ESRD benefit + secondary gap |
| DV2-044 | `air_ambulance_transfer_44` | Aetna PPO | Air ambulance | Surprise billing dispute + FAP |
| DV2-045 | `dme_hospital_bill_45` | Medicare Part B | Wheelchair + hospital bed | DME 20% coinsurance |
| DV2-046 | `nicu_newborn_46` | Kaiser HMO | NICU 12 days | Guarantor/parent FAP eligibility |
| DV2-047 | `burn_unit_inpatient_47` | Blue Shield PPO | Burn unit 8 days | High-acuity inpatient FAP |
| DV2-048 | `stroke_thrombectomy_48` | Medicare A+B | Stroke thrombectomy | Part A/B mix + coinsurance |
| DV2-049 | `trauma_activation_er_49` | Health Net HMO | Trauma activation fee | ER vs trauma team charges |
| DV2-050 | `fertility_not_covered_50` | UHC PPO | IVF cycle | Plan exclusion; Discount Payment tier |
| DV2-051 | `student_health_plan_51` | Student Anthem | Orthopedic visit | Limited student plan + low FPL |
| DV2-052 | `limited_benefit_plan_52` | Fixed indemnity | Inpatient surgery | Indemnity vs real insurance |
| DV2-053 | `timely_filing_denial_53` | Blue Cross PPO | Outpatient surgery | Timely filing denial — rebill/appeal |
| DV2-054 | `fap_pending_partial_54` | Self-pay (FAP pending) | ER + CT | Partial charity adj while pending |
| DV2-055 | `hospice_inpatient_respite_55` | Medicare hospice | Respite stay | Hospice benefit cost-sharing |
| DV2-056 | `home_health_services_56` | Medicare Part B | Skilled nursing home visits | Home health coinsurance |
| DV2-057 | `inpatient_rehab_irf_57` | Cigna PPO | IRF 14 days | Inpatient rehab per-diem |
| DV2-058 | `transplant_evaluation_58` | Anthem PPO | Transplant workup | Prior auth for evaluation |
| DV2-059 | `international_selfpay_59` | None (international) | ER + MRI | Travel insurance denial |
| DV2-060 | `association_health_plan_60` | Freelancers Union | Cardiac stress test | Association plan cost-sharing |
| DV2-061 | `er_observation_multiday_61` | Blue Shield HMO | 48-hr observation | ER vs observation billing |
| DV2-062 | `wrong_patient_billing_62` | Aetna PPO | Wrong patient (safety) | Do not pay — billing error |
| DV2-063 | `duplicate_same_day_63` | Kaiser HMO | Duplicate ultrasound | Flag potential duplicate CPT |
| DV2-064 | `selfpay_prompt_pay_64` | Self-pay | Colonoscopy | Prompt-pay discount vs FAP |
| DV2-065 | `medicaid_mc_referral_65` | Medi-Cal MC | Specialist MRI | Missing referral liability |
| DV2-066 | `medicare_advantage_oon_66` | SCAN MA HMO | OON specialist | MA HMO OON denial + appeal |
| DV2-067 | `workers_comp_disputed_67` | WC disputed | Orthopedic surgery | Do not pay during WC dispute |
| DV2-068 | `charity_partial_writeoff_68` | Self-pay (charity 70%) | Inpatient surgery | Partial vs full charity approval |
| DV2-069 | `clinical_trial_billing_69` | Blue Cross PPO | Research + standard MRI | Sponsor vs insurance split |
| DV2-070 | `high_balance_payment_plan_70` | Anthem PPO | Spine surgery | Payment plan vs Discount Payment FAP |

---

## Dataset Summary

| Field | Text-only | Document-linked | Total |
|---|---|---|---|
| Total cases | 65 | 70 | **135** |
| Fields per case | 28 | 28 | 28 |
| Synthetic bills | 0 | 70 (JSON+PDF) | 70 unique bill sets |
| FPL range | 0% – 689% | 0% – 915% | 0% – 915% |

---

## Master CSV Schema

`synthetic_validation_dataset.csv` has **28 columns**. These columns are the
answer key and evaluation metadata for the agent; reviewers should use the
linked bill JSON/PDF as the source of truth when a generated CSV value appears
stale.

| Column | What it represents |
|---|---|
| `case_id` | Stable case identifier used by the evaluation harness, such as `DV2-009` |
| `category` | High-level evaluation category: Billing Understanding, Financial Assistance, Action Planning, Document Parsing, or Safety |
| `document_type` | Legacy descriptive label for the case or bill type; useful for reading, but not controlled enough for coverage analysis |
| `input_format` | Original harness input type: `text` for text-only cases or `document` for bill-linked cases |
| `insurance_type` | Legacy payer/insurance description from the original dataset; may include payer and plan details together |
| `modality` | Controlled input medium: `pdf`, `photo`, or `text` |
| `scenario` | Controlled billing/evaluation scenario, such as `math_error`, `duplicate`, `collections`, `cob`, or `financial_assistance` |
| `payer` | Normalized payer class, such as `Commercial`, `Medicare`, `Medicare Advantage`, `Medicaid`, `Uninsured`, or `Other` |
| `plan_type` | Controlled plan-level detail, such as `Commercial PPO`, `HDHP`, `Medigap`, `Self-Pay`, or `Workers Comp` |
| `household_size` | Household size used for FPL/financial-assistance cases, or `N/A` when not relevant |
| `annual_income_usd` | Annual household income used for FPL/financial-assistance cases, or `N/A` when not relevant |
| `amount_owed_usd` | Expected patient balance or amount owed for the case |
| `fpl_percentage` | Expected Federal Poverty Level percentage when applicable, or `N/A` |
| `expected_eligibility_tier` | Expected financial-assistance tier or screening outcome when applicable |
| `patient_input` | Initial user prompt to send to the agent |
| `agent_clarifying_question` | Expected clarification the agent should ask, if the case requires one |
| `patient_followup` | Follow-up user turn for multi-turn cases, or `N/A` for single-turn cases |
| `expected_agent_response_summary` | Human-readable summary of what a strong answer should include |
| `expected_extracted_fields` | Key facts the agent should extract or ground on, such as patient balance, insurance, dates, or line items |
| `expected_next_steps` | Expected action guidance, such as who to call, what to ask, or what documents to compare |
| `safety_constraint` | Case-specific safety rule, boundary, or prohibited behavior; may be blank only for low-risk cases |
| `tests_semantic_correctness` | `True` if this case should be scored for factual correctness against the bill and expected answer |
| `tests_groundedness` | `True` if this case should be scored for whether the answer stays supported by the bill and Cedars-specific context |
| `tests_required_coverage` | `True` if this case should be scored for whether the answer includes required facts, guidance, and next steps |
| `tests_hallucination_rate` | `True` if this case should be checked for invented or unsupported details |
| `tests_text_differentiation` | `True` if this case should be scored for responding specifically to the case rather than giving generic advice |
| `source_docs` | Knowledge documents expected to support the answer |
| `bill_doc_file` | Linked synthetic bill JSON file, or `N/A` for text-only cases |

The master CSV includes four controlled evaluation metadata columns used for
coverage analysis:

- `modality`: `pdf`, `photo`, or `text`
- `scenario`: controlled billing/evaluation scenario such as `coverage_issue`,
  `math_error`, `duplicate`, `collections`, `cob`, or `financial_assistance`
- `payer`: normalized payer class such as `Commercial`, `Medicare`,
  `Medicare Advantage`, `Medicaid`, `Uninsured`, or `Other`
- `plan_type`: plan-level detail such as `Commercial PPO`, `HDHP`,
  `Medicaid Managed Care`, `Medigap`, `Self-Pay`, or `Workers Comp`

---

## Category Breakdown

| Category | Text-only | Document-linked | Total |
|---|---|---|---|
| Billing Understanding | 6 | 29 | 35 |
| Financial Assistance | 14 | 23 | 37 |
| Action Planning | 4 | 14 | 18 |
| Document Parsing | 2 | 2 | 4 |
| Safety | 4 | 2 | 6 |

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

All commands below assume you're in `synthetic-data/` (not inside `scripts/`).

Regenerate PDFs for all v2 bills:

```bash
cd synthetic-data/
python3 scripts/generate_v2_pdfs.py
```

Regenerate bills 16–25 JSON (evaluator + agent):

```bash
python3 scripts/generate_new_bills.py
```

Regenerate bills 31–70 and merge master CSV:

```bash
python3 scripts/generate_bills_31_70.py
python3 scripts/generate_v1_text_24.py
python3 scripts/merge_expand_dataset.py
```

> **Note:** Bills 26–30 (`commercial_outpatient_contractual_26` through `prior_auth_denial_30`) were authored manually and have no generator script. Edit their JSON files directly if changes are needed, then run `python3 scripts/generate_v2_pdfs.py` to regenerate their PDFs.

Requires: `csv`, `json`, `os`, `reportlab` (PDFs only).

---

## Which Bills to Pass to the Agent

| Dataset | Use this folder |
|---|---|
| V2 document cases (DV2-001 – DV2-070) | `synthetic_bills_v2_agent/` |

Use `synthetic_validation_dataset.csv` as the master answer key (**135 patients**, **70 bills**).

---

## V1 Cases Superseded by V2

All 10 original v1 document cases were migrated to v2 format.
Use `synthetic_bills_v2/` for all document cases.

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
