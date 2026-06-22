# Draft Evaluation Harness

This folder contains early evaluation infrastructure for the Cedars-Sinai
Patient Billing Agent synthetic validation dataset.

The synthetic data is still being finalized, so this harness is intentionally
lightweight. It validates the dataset shape and creates a manual review
template, but it does not yet produce final automated accuracy scores.

## What It Does

- Loads `synthetic-data/synthetic_validation_dataset.csv`
- Confirms the expected 23-column schema is present
- Counts cases by category, insurance type, document type, input format, and
  evaluation flag
- Checks that required fields are populated
- Checks that evaluation flags are `True` or `False`
- Warns when referenced source documents or synthetic bill files are missing
- Creates a manual evaluation CSV template for future agent response review

## What It Does Not Do Yet

- It does not call the live agent.
- It does not grade semantic correctness automatically.
- It does not calculate final accuracy, hallucination, or extraction scores.
- It does not require an API key or `.env` file.

## Usage

From the repository root:

```bash
python3 -m evaluation.evaluation_harness validate
```

To print the validation report as JSON:

```bash
python3 -m evaluation.evaluation_harness validate --json
```

To create a manual review template:

```bash
python3 -m evaluation.evaluation_harness template --output evaluation/manual_review_template.csv
```

The generated manual review template is meant for reviewers to paste in agent
responses and mark whether each response passed the relevant checks.

## Recommended Next Steps

Once the synthetic dataset is finalized, the harness can be expanded to:

1. Run selected cases through the local agent.
2. Save agent responses beside the expected answers.
3. Add rubric-based scoring for each evaluation flag.
4. Produce summary metrics by category and failure type.
5. Compare results across branches before merging new agent tools.

