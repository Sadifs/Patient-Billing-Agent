# Draft Evaluation Harness

This folder contains evaluation infrastructure for the Cedars-Sinai Patient
Billing Agent synthetic validation dataset.

The harness is intentionally lightweight. It validates the dataset, can run
selected cases through a locally running agent, saves responses, and creates
manual review/scoring CSVs. It does not yet produce final automated accuracy
scores.

## What It Does

- Loads `synthetic-data/synthetic_validation_dataset.csv`
- Confirms the expected 23-column schema is present
- Counts cases by category, insurance type, document type, input format, and
  evaluation flag
- Checks that required fields are populated
- Checks that evaluation flags are `True` or `False`
- Warns when referenced source documents or synthetic bill files are missing
- Resolves synthetic bill references from the current v2 folders first:
  `synthetic_bills_v2_agent`, then `synthetic_bills_v2`, then the legacy
  `synthetic_bills` folder
- Creates a manual evaluation CSV template for future agent response review
- Runs selected cases through the local agent via `/chat`
- Optionally uploads referenced synthetic bill PDFs before document cases
- Saves initial/follow-up/final agent responses
- Creates a review CSV aligned to team metrics:
  semantic correctness, precision, recall, hallucination, text differentiation,
  and safety

## What It Does Not Do Yet

- It does not grade semantic correctness automatically.
- It does not calculate final accuracy, hallucination, or extraction scores.
- Dataset validation and template creation do not require an API key or `.env`
  file.
- Live-agent runs require the local agent to already be running.

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

To run a small live-agent evaluation sample:

```bash
# In another terminal, start the app first:
# cd agent-harness
# docker compose up --build

python3 -m evaluation.evaluation_harness run-live \
  --limit 5 \
  --output evaluation/live_agent_review_sample.csv
```

To run specific cases:

```bash
python3 -m evaluation.evaluation_harness run-live \
  --case-id FA-001 \
  --case-id DV2-021 \
  --output evaluation/live_agent_review_selected.csv
```

The live review CSV intentionally leaves reviewer scoring fields blank. Reviewers
should mark:

- `semantic_correctness_score_0_1` and `semantic_correctness_pass`
- `precision_score_0_1` and `precision_pass`
- `recall_score_0_1` and `recall_pass`
- `hallucination_present` and `hallucination_pass`
- `text_differentiation_score_1_5` and `text_differentiation_pass`
- `safety_constraint_pass`
- `overall_pass`

## Recommended Next Steps

Recommended next improvements:

1. Add summary metric aggregation from completed review CSVs.
2. Add rubric-based LLM-assisted scoring as an optional helper, not as the only
   source of truth.
3. Compare results across branches before merging new agent tools.
4. Add retry/resume support for long live-agent runs.
