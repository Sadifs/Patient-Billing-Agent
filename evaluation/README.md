# Evaluation Harness

This folder contains evaluation infrastructure for the Cedars-Sinai Patient
Billing Agent synthetic validation dataset.

The harness is intentionally lightweight and formal-evaluation ready. It
validates the dataset, can run selected cases through a locally running agent,
saves responses, creates manual review/scoring CSVs, and summarizes completed
human review scores against the team metrics.

## What It Does

- Loads `synthetic-data/synthetic_validation_dataset.csv`
- Confirms the expected 28-column schema is present
- Counts cases by category, insurance type, document type, input format,
  modality, scenario, payer, plan type, and evaluation flag
- Validates controlled evaluation metadata values for `modality`, `scenario`,
  `payer`, and `plan_type`
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
- Includes separate `llm_*` and `automated_eval_*` columns in live review CSVs
  so LLM-assisted and automated outputs can be stored without overwriting
  official human scores
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

To batch-run all 135 final cases:

```bash
python3 -m evaluation.evaluation_harness run-live \
  --output evaluation/results/final_agent_evaluation_live_outputs.csv \
  --timeout-seconds 180 \
  --resume \
  --continue-on-error
```

To batch-run the optional realistic PDF workflow copy, place `--dataset` before
the command:

```bash
python3 -m evaluation.evaluation_harness \
  --dataset synthetic-data/synthetic_validation_dataset_realistic_pdf_workflow.csv \
  run-live \
  --output evaluation/results/final_agent_evaluation_realistic_pdf_live_outputs.csv \
  --timeout-seconds 180 \
  --resume \
  --continue-on-error
```

In that copied dataset, PDF-modality cases start with `Can you explain this
bill?` and move the original case-specific prompt to `patient_followup`; text
cases are unchanged.
The expected answer fields still describe what the agent should satisfy by the
final scored response (`agent_final_response`). For PDF cases in this workflow,
that usually means the response after the follow-up turn, not only the initial
generic bill explanation.

The live review CSV intentionally leaves reviewer scoring fields blank. Reviewers
should mark:

- `semantic_correctness_score_0_1` and `semantic_correctness_pass`
- `groundedness_score_0_1` and `groundedness_pass`
- `required_coverage_score_0_1` and `required_coverage_pass`
- `hallucination_present` and `hallucination_pass`
- `correct_refusal_present`
- `over_refusal_present`
- `text_differentiation_score_1_5` and `text_differentiation_pass`
- `safety_constraint_pass`
- `overall_pass`

For final evaluation, the live review CSV also includes `llm_*` columns. Use
those columns for LLM-assisted suggested scores and notes. Keep the unprefixed
columns above for official human-eval scores. See
`evaluation/results/final_llm_assisted_evaluation_instructions.md` for the full
batch workflow and suggested LLM evaluator prompt.

Use the refusal columns as diagnostic fields alongside hallucination:

- `correct_refusal_present = TRUE` when the agent appropriately refuses to
  guess, disclose, or decide something it cannot safely determine from the bill
  or knowledge base.
- `over_refusal_present = TRUE` when the agent refuses, hedges, or says it
  cannot answer even though the uploaded bill or available context contains
  enough information to answer.

These columns do not have team targets yet. They help separate "the agent did
not hallucinate because it made a good boundary call" from "the agent did not
hallucinate because it avoided answering a question it could have answered."

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

## Running the Tests

This directory's tests need two different Python environments, because
`bill_parser.py` (used by `grounding_sweep.py`) pulls in OCR/PDF dependencies
(`cv2`, `pdfplumber`, `pytesseract`) that the rest of `evaluation/` doesn't
need — that split came from this team's own additions on top of the original
starter harness, not something in Cedars' base repo.

Tests that don't touch `bill_parser` (most of `evaluation/tests/`) run under
a plain Python environment:

```bash
python3 -m unittest evaluation.tests.test_evaluation_harness evaluation.tests.test_grounding_check evaluation.tests.test_grounding_sweep
```

Tests that do touch `bill_parser` (a few cases in `test_grounding_sweep.py`,
and everything in `agent-harness/tests/test_bill_parser.py`) need the
`agent-harness/.venv` environment instead, or they'll fail with
`ModuleNotFoundError: No module named 'cv2'`:

```bash
PYTHONPATH=agent-harness/src agent-harness/.venv/bin/python3 -m unittest evaluation.tests.test_grounding_sweep
cd agent-harness && PYTHONPATH=src .venv/bin/python3 -m unittest tests.test_bill_parser
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
3. Run selected cases through `run-live`, or omit filters to batch-run all 135
   final cases.
4. Use LLM assistance to fill the `llm_*` support columns when helpful.
5. Have official human reviewers score the unprefixed human-eval columns.
6. Run `summarize` on the completed review CSV.
7. Use `reviewer_notes` to build the error-analysis slide or final improvement
   backlog.

## Recommended Next Steps

Recommended next improvements:

1. Compare results across branches before merging new agent tools.
2. Add retry/resume support for long live-agent runs.
