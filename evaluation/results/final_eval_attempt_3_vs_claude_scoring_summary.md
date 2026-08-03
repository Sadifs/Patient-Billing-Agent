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
- `possible_dataset_balance_conflict`: 1

## Key Findings

- The independent Claude scoring is materially stricter on groundedness and safety. Several of those disagreements should be manually reviewed rather than dismissed as scoring noise.
- The hard upload-refusal issue was real in text-only cases. The direct bill header/amount handlers were still returning “I do not see an uploaded bill connected...” instead of deferring to the LLM when the user had already supplied enough text context.
- This branch now fixes that refusal path by letting the LLM answer text-only bill questions instead of forcing an upload. A 14-case smoke test covering the previously flagged refusal cases produced zero instances of the old refusal text; see `final_eval_refusal_fix_smoke.csv`.
- DV2-064 appears to be a dataset/answer-key conflict: the bill JSON and `amount_owed_usd` show $9,664, while the prompt/expected fields mention $7,464.
- Some Claude hallucination/safety flags may be real defects; compare the cases tagged `claude_hallucination_only` and `claude_safety_fail_only` in the CSV before accepting final scores.
- `final_eval_dataset_issue_audit.csv` lists cases where expected/prompt dollar values may conflict with the source bill JSON. Some rows are component balances rather than true total-balance errors, so these should be reviewed before changing expected fields.

## Files

- Row-level comparison: `final_eval_attempt_3_vs_claude_scoring_comparison.csv`
- Attempt 3 scores: `final_eval_attempt_3.csv`
- Claude scores: `final_eval_attempt_2_claude_scored.csv`
- Smoke test after upload-refusal fix: `final_eval_refusal_fix_smoke.csv`
- Source-of-truth audit: `final_eval_dataset_issue_audit.csv`
- Manual priority list: `final_eval_claude_priority_review_cases.md`
