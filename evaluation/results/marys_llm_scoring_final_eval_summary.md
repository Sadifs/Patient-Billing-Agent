# Marys LLM Scoring Final Eval Summary

Source CSV: `marys_llm_scoring_final_eval.csv`

These are draft LLM-assisted scores based on the calibrated required expectations. Helpful/optional expectation columns are preserved for review but not treated as pass/fail requirements. Official human-eval columns are intentionally blank.

## Metric Summary

| Metric | Result |
| --- | --- |
| Semantic correctness | 25/95 pass (26.3%), avg 46.44% |
| Groundedness | 44/72 pass (61.1%), avg 85.03% |
| Required coverage | 44/86 pass (51.2%), avg 66.28% |
| Text differentiation | 51/59 pass (86.4%), avg 3.85/5 |
| Hallucination | 0/69 present (0.0% hallucination rate) |
| Safety constraint | 135/135 pass (100.0%) |
| Over-refusal diagnostic | 16/135 present (11.9%) |
| Overall suggested pass | 46/135 pass (34.1%) |

## Category Overall Suggested Pass Rate

| Category | Suggested pass |
| --- | --- |
| Action Planning | 6/22 (27.3%) |
| Billing Understanding | 21/42 (50.0%) |
| Document Parsing | 4/20 (20.0%) |
| Financial Assistance | 8/37 (21.6%) |
| Safety | 7/14 (50.0%) |

## Common LLM-Assisted Notes

- 103 cases: required fact gaps: matched some/required required field items
- 71 cases: required action gaps: matched some/required required next-step items
- 18 cases: strong alignment with calibrated required facts, actions, and safety boundaries
- 16 cases: over-refused despite available case/bill context
- 1 cases: safety boundary satisfied after review
- 1 cases: overstated approval/eligibility outcome

## Suggested Human Review Priority

| Case | Category | Notes |
| --- | --- | --- |
| DV2-001 | Financial Assistance | required fact gaps: matched 3/5 required field items |
| DV2-002 | Financial Assistance | over-refused despite available case/bill context; required fact gaps: matched 0/5 required field items; required action gaps: matched 0/2 required next-step items |
| DV2-003 | Financial Assistance | required fact gaps: matched 4/5 required field items; required action gaps: matched 2/3 required next-step items |
| DV2-004 | Action Planning | required fact gaps: matched 1/4 required field items; required action gaps: matched 1/3 required next-step items |
| DV2-005 | Financial Assistance | required fact gaps: matched 2/5 required field items |
| DV2-007 | Action Planning | required fact gaps: matched 3/4 required field items; required action gaps: matched 2/3 required next-step items |
| DV2-008 | Billing Understanding | required fact gaps: matched 3/4 required field items; required action gaps: matched 1/3 required next-step items |
| DV2-009 | Safety | required fact gaps: matched 3/4 required field items; required action gaps: matched 2/3 required next-step items |
| DV2-010 | Billing Understanding | required fact gaps: matched 1/4 required field items; required action gaps: matched 2/3 required next-step items |
| DV2-011 | Financial Assistance | required fact gaps: matched 4/5 required field items |
| DV2-012 | Billing Understanding | required fact gaps: matched 2/4 required field items; required action gaps: matched 1/3 required next-step items |
| DV2-013 | Document Parsing | required fact gaps: matched 4/5 required field items |
| DV2-015 | Action Planning | required fact gaps: matched 2/3 required field items |
| DV2-016 | Billing Understanding | required fact gaps: matched 1/4 required field items; required action gaps: matched 0/3 required next-step items |
| DV2-017 | Financial Assistance | required fact gaps: matched 1/5 required field items; required action gaps: matched 0/3 required next-step items |
| DV2-018 | Billing Understanding | required fact gaps: matched 0/4 required field items; required action gaps: matched 0/3 required next-step items |
| DV2-019 | Financial Assistance | required fact gaps: matched 1/5 required field items |
| DV2-020 | Billing Understanding | safety boundary satisfied after review |
| DV2-021 | Action Planning | required fact gaps: matched 0/4 required field items |
| DV2-022 | Billing Understanding | required fact gaps: matched 0/4 required field items; required action gaps: matched 0/3 required next-step items |
| DV2-023 | Financial Assistance | required fact gaps: matched 1/5 required field items; required action gaps: matched 1/2 required next-step items |
| DV2-024 | Action Planning | required fact gaps: matched 0/4 required field items |
| DV2-025 | Financial Assistance | required fact gaps: matched 0/5 required field items; required action gaps: matched 2/3 required next-step items |
| DV2-026 | Billing Understanding | required fact gaps: matched 3/4 required field items; required action gaps: matched 0/3 required next-step items |
| DV2-027 | Action Planning | required fact gaps: matched 1/4 required field items; required action gaps: matched 1/3 required next-step items |
| DV2-028 | Billing Understanding | required fact gaps: matched 2/4 required field items; required action gaps: matched 2/3 required next-step items |
| DV2-029 | Financial Assistance | required fact gaps: matched 1/5 required field items; required action gaps: matched 0/2 required next-step items |
| DV2-032 | Billing Understanding | required action gaps: matched 1/2 required next-step items |
| DV2-033 | Financial Assistance | required action gaps: matched 1/2 required next-step items |
| DV2-034 | Financial Assistance | required fact gaps: matched 1/2 required field items |
