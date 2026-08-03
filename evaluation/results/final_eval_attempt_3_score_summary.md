# Final Eval Attempt 3 Score Summary

Source CSV: `final_eval_attempt_2.csv`

Scored CSV: `final_eval_attempt_3.csv`

Metric flag audit: `final_eval_metric_flag_audit.csv`

Attempt 3 copies Attempt 2, applies the recommended AS-AW metric-flag updates, and refreshes the LLM-assisted/automated scoring fields for the updated metric applicability. These are Codex/rubric-assisted draft scores, not official human scoring.

After the flag audit, semantic correctness, groundedness, required coverage, and hallucination are tested on all 135 cases; text differentiation is tested on 124 cases where case-specificity is relevant. Official human-eval score columns remain blank.

## Metric Summary

| Metric | Result |
| --- | --- |
| Semantic correctness | 21/135 pass, avg 51.2% |
| Groundedness | 120/135 pass, avg 92.7% |
| Required coverage | 17/135 pass, avg 56.4% |
| Text differentiation | 94/124 pass, avg 3.99/5 |
| Hallucination | 2/135 present; 133/135 pass |
| Safety constraint | 134/135 pass |
| Overall suggested pass | 9/135 pass |

## Important Caveat

Attempt 3 changes the metric denominators because the AS-AW flags were updated to better match the final rubric. Because more metrics are now active on more cases, pass rates are not directly comparable to Attempt 2 without accounting for the larger denominator and stricter applicability.

## Automated Status Breakdown

- `needs_human_review`: 126
- `pass`: 9

## Recommended Human Review Focus

- Review cases where newly enabled semantic correctness or required coverage metrics fail.
- Review hallucination flags now that hallucination is tested broadly.
- Treat this as LLM-assisted evidence only; official human-eval columns remain separate.
