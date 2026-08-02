# Final Evaluation Comparison Summary

This summary compares two LLM-assisted final evaluation attempts:

- `final_eval_attempt_1.csv`: earlier realistic-PDF evaluation run used as the comparison baseline.
- `final_eval_attempt_2.csv`: updated evaluation run after the final-eval agent routing and coverage fixes on branch `mary/fix-final-eval-agent-gaps`.

## Important Caveat

This is not a perfectly apples-to-apples comparison. The newer scoring pass uses the updated evaluation instructions: score the full transcript (`agent_initial_response` + `agent_followup_response`) instead of only the final response. The scoring helper is also rubric-assisted and should be treated as draft LLM-assisted evidence, not official human scoring.

## Overall Read

The updated agent looks better in response quality, but worse by strict pass count.

The agent improved on grounding, specificity, and average semantic/coverage scores. However, many rows still miss at least one required field or required next step, and the final pass threshold is strict (`>= 0.90`). Because of that, the pass counts for semantic correctness, required coverage, and overall suggested pass are lower.

## Metric Comparison

| Metric | Attempt 1 | Attempt 2 | Direction |
| --- | ---: | ---: | --- |
| Semantic correctness pass | 25/95 | 16/95 | Worse pass count |
| Semantic correctness average | 46.4% | 52.4% | Better average |
| Groundedness pass | 44/72 | 70/72 | Much better |
| Groundedness average | 85.0% | 93.9% | Better |
| Required coverage pass | 44/86 | 17/86 | Worse pass count |
| Required coverage average | 66.3% | 73.6% | Better average |
| Text differentiation pass | 51/59 | 55/59 | Better |
| Text differentiation average | 3.85/5 | 4.36/5 | Better |
| Hallucination rate | 0/69 present | 2/69 present | Slightly worse, still under 5% target |
| Safety pass | 135/135 | 134/135 | Slightly worse |
| Overall suggested pass | 46/135 | 27/135 | Worse pass count |

## Interpretation

- **Grounding improved:** The agent is much less likely to make unsupported or overly broad claims.
- **Case specificity improved:** The agent responses are more tailored to the bill and patient situation.
- **Average semantic and coverage scores improved:** Even when the agent does not pass, it is often closer to the expected answer than before.
- **Strict pass counts dropped:** The `>= 0.90` pass threshold means missing one important required fact or action can turn an otherwise decent response into a failing row.
- **Required coverage remains the main gap:** The most common issue is still missing required fields or next steps, not unsafe behavior.
- **Manual review is needed:** The two hallucination flags and one safety failure should be manually reviewed to confirm whether they are real agent issues or scoring artifacts.

## Bottom Line

The updated agent appears better from a product-quality perspective: more grounded, more specific, and stronger on average. But the formal pass-rate metrics still show that the agent needs more work on consistently including all required facts and next steps.

Suggested next step: manually review the priority cases listed in `final_eval_attempt_2_score_summary.md`, especially the hallucination/safety flags and the high-volume required-coverage failures. Use `final_eval_attempt_2.csv` as the current scored evaluation output.
