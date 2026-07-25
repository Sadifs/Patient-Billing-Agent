# Midterm Evaluation Results

This folder contains the team's midterm evaluation results for the Cedars-Sinai
Patient Billing Agent.

## Files

- `midterm_agent_evaluation_scoring.csv`: completed review CSV for the 28
  selected midterm cases.
- `midterm_error_analysis.md`: summarized error patterns and recommended
  improvement areas based on reviewer notes.

## Evaluation Method

The team used **Human Review + LLM Assistance**:

- Human reviewers ran selected synthetic cases through the live local agent.
- Reviewers used the synthetic bill PDF/JSON as the source of truth.
- LLM assistance was used to help interpret responses, check consistency, and
  summarize reviewer notes.
- Final scores were reviewer-owned and were not fully automated.

## Metric Names

For the midterm presentation, the team renamed two metrics so they better match
what was actually reviewed:

- `groundedness_score_0_1`: formerly precision. Measures whether the answer is
  supported by bill data, Cedars-specific guidance, or clearly stated limits.
- `required_coverage_score_0_1`: formerly recall. Measures whether the answer
  includes the required case-specific facts, next steps, and safety guidance.

Other scored fields:

- `semantic_correctness_score_0_1`
- `hallucination_present`
- `text_differentiation_score_1_5`
- `safety_constraint_pass`
- `overall_pass`

## How To Summarize Results

From the repository root:

```bash
python3 -m evaluation.evaluation_harness summarize \
  evaluation/results/midterm_agent_evaluation_scoring.csv
```

## How To Use These Results

Use this CSV as an evidence base for future agent improvements:

1. Find cases with low scores or `overall_pass = FALSE`.
2. Read `reviewer_notes` to identify the failure pattern.
3. Decide whether the fix belongs in prompts, parser logic, safety hooks, UI
   context handling, or evaluation data.
4. Add or update a regression test for the failing behavior.
5. Rerun the affected case through the live-agent evaluation harness.

This file should be treated as a versioned evaluation artifact, not as training
data containing real patient information. The cases are synthetic.
