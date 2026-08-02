# Realistic PDF Evaluation Expectation Calibration Notes

Calibrated CSV: `final_agent_evaluation_realistic_pdf_calibrated_review.csv`
Source CSV: `final_agent_evaluation_realistic_pdf_live_outputs.csv`

This file preserves the agent responses from the realistic PDF workflow batch run and recalibrates the answer key so final scoring focuses on required patient-safety, factual-correctness, and action-planning details.

## What Changed

- Preserved the original expected columns in `original_expected_*` columns.
- Replaced active `expected_extracted_fields` and `expected_next_steps` with required-only versions.
- Added `helpful_optional_expected_extracted_fields` and `helpful_optional_expected_next_steps` for nice-to-have details that should not drive pass/fail scoring.
- Rewrote `expected_agent_response_summary` into the agent-style sectioned format: summary, key bill facts/insurance, warnings, next steps, helpful optional details, and scoring note.
- Replaced outdated/exact `310-423-8000` expectations with generic Cedars-Sinai Patient Financial Services contact guidance.

## Counts

- Rows with rewritten section-style summaries: 135 of 135
- Rows with required/helper field or next-step changes: 56 of 135
- Required expected field items after calibration: 380
- Helpful/optional expected field items after calibration: 79
- Required next-step items after calibration: 285
- Helpful/optional next-step items after calibration: 56
- Rows with removed/reworded outdated expectations: 13

## Rows With Required Field/Step Changes By Category

| Category | Rows |
| --- | --- |
| Action Planning | 10 |
| Billing Understanding | 21 |
| Document Parsing | 1 |
| Financial Assistance | 19 |
| Safety | 5 |

## Example Calibrations

| Case | Required fields | Helpful/optional fields | Required next steps | Helpful/optional next steps | Removed/reworded |
| --- | --- | --- | --- | --- | --- |
| DV2-001 | insurance=Self-pay; balance_due=$19000; household_size=4; annual_income=$28000; fpl_percent=85% | cedars_tier=Charity Care candidate; preferred_language=Spanish | 1. Call Cedars-Sinai Patient Financial Services and ask for a Spanish-speaking representative. / 2. Request FAP application — 85% FPL qualifies for Charity Care. | 1. Ask billing to hold account during FAP review. / 2. Gather income documentation for all household earners. | reworded step "Call 310-423-8000 and ask for a Spanish-speaking representative." as "Call Cedars-Sinai Patient Financial Services and ask for a Spanish-speaking representative." |
| DV2-002 | insurance=Self-pay; balance_due=$51200; household_size=1; annual_income=$15000; fpl_percent=94% | cedars_tier=Charity Care candidate; service=appendectomy inpatient | 1. Call Cedars-Sinai Patient Financial Services immediately — $51,200 balance is urgent. / 2. Apply for Cedars FAP — 94% FPL qualifies for Charity Care. | 1. Ask billing to hold account during review. / 2. Gather income proof (pay stubs or tax return). | reworded step "Call 310-423-8000 immediately — $51,200 balance is urgent." as "Call Cedars-Sinai Patient Financial Services immediately — $51,200 balance is urgent." |
| DV2-003 | gross_charges=$12200; insurance_paid=$9600; adjustments=$2000; patient_responsibility=$600; household_size=2 | fpl_percent=324%; cedars_tier=Charity Care candidate if needed | 1. Verify EOB confirms $600 patient responsibility. / 2. If balance is unaffordable, apply for Cedars FAP — 324% FPL qualifies for Charity Care. / 3. Call Cedars-Sinai Patient Financial Services with billing questions. | 1. Pay $600 once EOB is confirmed if no assistance needed. | reworded step "Call 310-423-8000 with billing questions." as "Call Cedars-Sinai Patient Financial Services with billing questions." |
| DV2-004 | insurance=Commercial HDHP; balance_due=$10100; fpl_percent=533%; cedars_tier=Discount Payment candidate | no_surprises_act=review anesthesia network status | 1. Apply for Cedars Discount Payment program — 533% FPL qualifies (401–600%). / 2. Review whether anesthesia was out-of-network; dispute under No Surprises Act if applicable. / 3. Call Cedars-Sinai Patient Financial Services to request FAP application. | 1. Do NOT assume you make too much — Cedars covers up to 600% FPL. | reworded step "Call 310-423-8000 to request FAP application." as "Call Cedars-Sinai Patient Financial Services to request FAP application." |
| DV2-005 | insurance=Medicare Part A+B; balance_due=$1632; fpl_percent=113%; cedars_tier=Charity Care candidate; supplemental=None | msp_eligible=possible | 1. Apply for Cedars FAP — Medicare patients qualify based on income. / 2. Call Cedars-Sinai Patient Financial Services to request FAP application. | 1. Ask about Medicare Savings Programs at 1-800-MEDICARE. / 2. Provide Social Security income documentation. | reworded step "Call 310-423-8000 to request FAP application." as "Call Cedars-Sinai Patient Financial Services to request FAP application." |
| DV2-006 | status=observation not inpatient; insurance=Medicare Part B + Medigap Plan G; total_amount_due=$820; unpaid_reason=pharmacy billed under Part D (not covered by Plan G) | Part_A_applies=False; FAP_eligible=True (157% FPL Charity Care) | 1. Request the MOON (Medicare Outpatient Observation Notice) in writing from Cedars. / 2. Call 866-803-1777 to confirm the $820 pharmacy charge and request an itemized statement. / 3. Apply for Cedars FAP — at 157% FPL the patient qualifies for Charity Care, which may cover the remaining balance. | 1. Ask billing whether the outpatient drugs can be processed through Medicare Part D instead. |  |
| DV2-007 | insurance=Medicare Advantage (Humana); insurance_paid=$0; balance_due=$107200; fpl_percent=301% | cedars_tier=Charity Care candidate; appeal_right=internal then IRO | 1. Do NOT pay $107,200 while appeal is in progress. / 2. Request denial letter from Humana with specific reason. / 3. File expedited internal appeal with Humana. | 1. Simultaneously apply for Cedars FAP — 301% FPL qualifies for Charity Care as fallback. |  |
| DV2-008 | insurance=Medicare Advantage (Kaiser); balance_due=$1200; fpl_percent=400%; boundary_case=True | copay_discrepancy=procedure vs office visit | 1. Review Kaiser MA Summary of Benefits for procedure cost-sharing. / 2. Request EOB to verify $1,200 is correct. / 3. Apply for Cedars FAP — 400% is the Charity Care boundary, not a disqualifier. | 1. Ask about Discount Payment tier if Charity Care is denied. |  |
| DV2-009 | insurance=Medi-Cal; balance_due=$820; expected_patient_cost=low or zero; action=verify before paying | possible_cause=billing error OR non-covered item | 1. Do NOT pay $820 yet. / 2. Contact Cedars-Sinai Patient Financial Services to verify charges were billed to Medi-Cal. / 3. Call Medi-Cal at 1-800-541-5555 to confirm coverage. | 1. Request written explanation of the balance. | reworded step "Call Cedars billing at 310-423-8000 to verify charges were billed to Medi-Cal." as "Contact Cedars-Sinai Patient Financial Services to verify charges were billed to Medi-Cal." |
| DV2-010 | insurance=Medi-Cal Share of Cost; balance_due=$760; share_of_cost=$760; fpl_percent=113% | documentation_type=alternative acceptable; medi_cal_pending=possible | 1. Check Medi-Cal application status — approval may cover bill retroactively. / 2. Call Medi-Cal at 1-800-541-5555 to confirm share of cost calculation. / 3. If applying for FAP, ask about alternative documentation for cash workers. | 1. Do not pay until Medi-Cal status is confirmed. |  |
| DV2-011 | insurance=Medicare+Medi-Cal dual eligible; balance_due=$0; fpl_percent=103%; cedars_tier=Charity Care candidate if balance arises; service=SNF |  | 1. Call Cedars-Sinai Patient Financial Services if a future balance appears. / 2. Apply for Cedars FAP proactively if concerned about future bills — 103% FPL qualifies. / 3. Contact Medi-Cal member services to confirm ongoing dual eligibility. | 1. Keep EOBs and this $0 statement for your records. | reworded step "Call 310-423-8000 if a future balance appears." as "Call Cedars-Sinai Patient Financial Services if a future balance appears." |
| DV2-012 | insurance=Commercial HMO; balance_due=$340; service=wellness reclassified diagnostic; fpl_percent=345% | cedars_tier=Charity Care candidate; action=verify coding and appeal | 1. Request visit coding from provider — ask if Z00.00 preventive code was used. / 2. Ask insurer in writing why visit was reclassified. / 3. File appeal if reclassification was triggered by minor mention. | 1. Apply for Cedars FAP if balance stands — 345% FPL qualifies for Charity Care. |  |
