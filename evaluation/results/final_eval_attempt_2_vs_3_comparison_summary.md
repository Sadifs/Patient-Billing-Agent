# Final Eval Attempt 2 vs Attempt 3 Comparison

Attempt 3 is a copy of Attempt 2 with corrected AS-AW metric flags and refreshed LLM-assisted scoring.

| Metric | Attempt 2 | Attempt 3 | Note |
| --- | ---: | ---: | --- |
| Semantic correctness | 16/95 pass, avg 52.4% | 21/135 pass, avg 51.2% | metric flags corrected |
| Groundedness | 70/72 pass, avg 93.9% | 120/135 pass, avg 92.7% | metric flags corrected |
| Required coverage | 17/86 pass, avg 73.6% | 17/135 pass, avg 56.4% | metric flags corrected |
| Text differentiation | 55/59 pass, avg 4.36/5 | 94/124 pass, avg 3.99/5 | metric flags corrected |
| Hallucination | 2/69 present | 2/135 present | denominator/flags updated |
| Safety | 134/135 pass | 134/135 pass | updated after flag correction |
| Overall suggested pass | 27/135 pass | 9/135 pass | updated after flag correction |

## Read This Carefully

If Attempt 3 has lower pass rates, that does not necessarily mean the agent got worse. The agent responses are the same as Attempt 2; the evaluation became broader because more metrics are now applied to cases where they are relevant under the final rubric.

