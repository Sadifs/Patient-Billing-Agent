# Midterm Evaluation Results

This folder contains the team's midterm evaluation results for the Cedars-Sinai
Patient Billing Agent.

## Files

- `midterm_agent_evaluation_scoring.csv`: completed review CSV for the 28
  selected midterm cases.
- `midterm_error_analysis.md`: summarized error patterns and recommended
  improvement areas based on reviewer notes.
- `final_agent_evaluation_scoring_template.csv`: blank final-review template for
  all 135 synthetic cases. It includes the answer-key fields, upload filenames
  for the 70 document/PDF cases, and empty response/scoring columns for final
  evaluation.

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
- `correct_refusal_present`
- `over_refusal_present`
- `text_differentiation_score_1_5`
- `safety_constraint_pass`
- `overall_pass`

Refusal fields are diagnostic and should be read alongside hallucination:

- `correct_refusal_present = TRUE` means the agent appropriately declined to
  guess, disclose, or decide something it could not safely determine.
- `over_refusal_present = TRUE` means the agent refused or over-hedged even
  though the bill/context contained enough information to answer.

The goal is to avoid making a vague agent look good just because it did not
hallucinate. A strong response should avoid hallucination while still answering
grounded questions when the information is available.

## How To Summarize Results

From the repository root:

```bash
python3 -m evaluation.evaluation_harness summarize \
  evaluation/results/midterm_agent_evaluation_scoring.csv
```

## How To Use These Results

Use this CSV as an evidence base for future agent improvements:

1. Open `midterm_agent_evaluation_scoring.csv`.
2. Filter for rows where `overall_pass = FALSE`.
3. Also review rows with any of these risk signals:
   - `semantic_correctness_score_0_1 < 0.90`
   - `groundedness_score_0_1 < 0.90`
   - `required_coverage_score_0_1 < 0.90`
   - `hallucination_present = TRUE`
   - `over_refusal_present = TRUE`
   - `text_differentiation_score_1_5 < 4`
   - `safety_constraint_pass = FALSE`
4. Read `reviewer_notes`, `expected_agent_response_summary`,
   `expected_extracted_fields`, and `expected_next_steps` for those cases.
5. Compare the agent response against the linked bill PDF/JSON when numbers,
   payer fields, dates, balances, or line items are involved.
6. Label the failure type:
   - **Prompt/skill issue:** the bill data was available, but the response was
     generic, poorly ordered, or missed required next steps.
   - **Parser issue:** the agent used wrong or missing fields because bill
     extraction failed.
   - **Safety issue:** the agent made a final legal, billing-validity, payment,
     or insurance-coverage determination it should have bounded.
   - **UI/context issue:** follow-up questions lost the uploaded bill context or
     confused multiple uploaded bills.
   - **Evaluation-data issue:** the expected answer or CSV field disagrees with
     the source bill JSON/PDF.
7. Make the smallest targeted fix in the relevant area.
8. Add or update a regression test for that behavior.
9. Rerun the affected case through the live-agent evaluation harness.
10. If the fix changes expected behavior, update the synthetic case or reviewer
    notes so future reviewers understand the new standard.

In short: use the scored CSV to find the failure, use the bill PDF/JSON and
expected fields to confirm the source of truth, then turn the reviewer note into
a targeted code, prompt, parser, safety, UI, or evaluation-data fix.

This file should be treated as a versioned evaluation artifact, not as training
data containing real patient information. The cases are synthetic.
