# Evaluation Harness

This folder contains evaluation infrastructure for the Cedars-Sinai Patient
Billing Agent synthetic validation dataset.

The harness is intentionally lightweight and formal-evaluation ready. It
validates the dataset, can run selected cases through a locally running agent,
saves responses, creates manual review/scoring CSVs, and summarizes completed
human review scores against the team metrics.

## What It Does

- Loads `synthetic-data/synthetic_validation_dataset.csv`
- Confirms the expected 23-column schema is present
- Counts cases by category, insurance type, document type, input format, and
  evaluation flag
- Checks that required fields are populated
- Checks that evaluation flags are `True` or `False`
- Treats blank `safety_constraint` values as warnings for low-risk cases, but
  errors for safety-related cases
- Warns when referenced source documents or synthetic bill files are missing
- Resolves synthetic bill references from the current v2 folders first:
  `synthetic_bills_v2_agent`, then `synthetic_bills_v2`, then the legacy
  `synthetic_bills` folder
- Creates a manual evaluation CSV template for future agent response review
- Runs selected cases through the local agent via `/chat`
- Optionally uploads referenced synthetic bill PDFs before document cases
- Saves initial/follow-up/final agent responses
- Creates a review CSV aligned to team metrics:
  semantic correctness, groundedness, required coverage, hallucination, text
  differentiation, and safety
- Summarizes completed review CSVs into metric results and compares them to the
  team targets

## What It Does Not Do Yet

- It does not grade semantic correctness automatically.
- It does not replace human review; reviewers still score each agent response.
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
  --case-id DV2-021 \
  --case-id DV2-063 \
  --output evaluation/live_agent_review_selected.csv
```

The live review CSV intentionally leaves reviewer scoring fields blank. Reviewers
should mark:

- `semantic_correctness_score_0_1` and `semantic_correctness_pass`
- `groundedness_score_0_1` and `groundedness_pass`
- `required_coverage_score_0_1` and `required_coverage_pass`
- `hallucination_present` and `hallucination_pass`
- `text_differentiation_score_1_5` and `text_differentiation_pass`
- `safety_constraint_pass`
- `overall_pass`

Older generated review CSVs may still use `precision_*` and `recall_*`
columns. The summary command supports both the old and renamed column names.

To summarize a completed review CSV:

```bash
python3 -m evaluation.evaluation_harness summarize \
  evaluation/live_agent_review_selected.csv
```

To print the summary as JSON:

```bash
python3 -m evaluation.evaluation_harness summarize \
  evaluation/live_agent_review_selected.csv \
  --json
```

## Team Metric Targets

The summary command compares completed reviewer scores against these targets:

- Semantic correctness rate: at least `90%`
- Groundedness average: at least `90%`
- Required coverage average: at least `90%`
- Hallucination rate: below `5%`
- Text differentiation average: at least `4/5`
- Safety constraint pass rate: `100%`

## Recommended Formal Evaluation Flow

1. Validate the dataset.
2. Start the local agent.
3. Run selected cases through `run-live`.
4. Have reviewers score the generated CSV.
5. Run `summarize` on the completed review CSV.
6. Use `reviewer_notes` to build the midterm error-analysis slide.

## Recommended Next Steps

Recommended next improvements:

1. Add rubric-based LLM-assisted scoring as an optional helper, not as the only
   source of truth.
2. Compare results across branches before merging new agent tools.
3. Add retry/resume support for long live-agent runs.
