# Attempt 3 vs Independent Claude Scoring Comparison

This compares `final_eval_attempt_3.csv` against Sadaf's independent Claude-scored `final_eval_attempt_2_claude_scored.csv`. Both are LLM-assisted drafts, not official human scoring.

## Headline Counts

| Source | Overall pass | Groundedness pass | Safety pass | Hallucination present |
| --- | ---: | ---: | ---: | ---: |
| Attempt 3 | 9/135 | 120/135 | 134/135 | 2/135 |
| Claude | 32/135 | 41/135 | 111/135 | 5/69 |

## Suspected Issue Tags

- `claude_safety_fail_only`: 24
- `upload_refusal`: 14
- `claude_hallucination_only`: 5
- `possible_dataset_balance_conflict`: 0 after dataset cleanup

## Key Findings

- The independent Claude scoring is materially stricter on groundedness and safety. Several of those disagreements should be manually reviewed rather than dismissed as scoring noise.
- The hard upload-refusal issue was real in text-only cases. The direct bill header/amount handlers were still returning “I do not see an uploaded bill connected...” instead of deferring to the LLM when the user had already supplied enough text context.
- This branch now fixes that refusal path by letting the LLM answer text-only bill questions instead of forcing an upload, and ports the remaining PR #45 trigger coverage into #46. A 14-case smoke test covering the previously flagged refusal cases produced zero instances of the old refusal text; see `final_eval_refusal_fix_smoke.csv`.
- The expected-balance source-of-truth conflicts previously flagged in DV2-046, DV2-048, DV2-049, DV2-051, DV2-056, DV2-058, DV2-061, and DV2-064 have been corrected in `synthetic_validation_dataset_realistic_pdf_workflow.csv`. The refreshed audit now finds 0 remaining `balance_due` / `amount_owed_usd` conflicts against bill JSON.
- DV2-056 should still be reviewed separately because the agent may contradict its own balance across turns, even though the dataset balance has been corrected.
- Some Claude hallucination/safety flags may be real defects; compare the cases tagged `claude_hallucination_only` and `claude_safety_fail_only` in the CSV before accepting final scores.
- `final_eval_dataset_issue_audit.csv` is currently empty aside from the header after the dataset cleanup. If new balance conflicts appear, regenerate the audit before treating them as agent failures.

## Files

- Row-level comparison: `final_eval_attempt_3_vs_claude_scoring_comparison.csv`
- Attempt 3 scores: `final_eval_attempt_3.csv`
- Claude scores: `final_eval_attempt_2_claude_scored.csv`
- Smoke test after upload-refusal fix: `final_eval_refusal_fix_smoke.csv`
- Source-of-truth audit: `final_eval_dataset_issue_audit.csv`
- Manual priority list: `final_eval_claude_priority_review_cases.md`
