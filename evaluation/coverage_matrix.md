# Coverage matrix: modality × scenario × payer

Requested by Professor Vo's parser-vs-gold feedback, item 2: "Build a coverage
matrix of modality × scenario × payer and look for empty cells. That's your
backlog." Generated from `synthetic-data/synthetic_validation_dataset.csv`.
This file is a snapshot, not live — re-run the query at the bottom to
regenerate after the dataset changes again.

**As of 2026-07-28 (135 rows, after adding 15 multi-turn + 20 adversarial
cases): 54 of 168 possible cells are filled (32%), up from 40/168 (24%) in
the original 100-row snapshot. `modality = photo` still has zero cases** —
that gap was intentionally not addressed here; see "Not built here" below.

## modality = pdf (70 cases — unchanged, all additions were text-only)

| scenario | Commercial | Medicare | Medicare Advantage | Medicaid | Uninsured | Other | row total |
|---|---|---|---|---|---|---|---|
| action_planning | 1 | 0 | 0 | 0 | 0 | 0 | 1 |
| bill_understanding | 8 | 3 | 0 | 1 | 0 | 1 | 13 |
| cob | 1 | 0 | 0 | 0 | 0 | 0 | 1 |
| collections | 0 | 0 | 0 | 0 | 1 | 0 | 1 |
| coverage_issue | 3 | 0 | 0 | 1 | 0 | 1 | 5 |
| document_parsing | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| duplicate | 1 | 0 | 0 | 0 | 0 | 0 | 1 |
| financial_assistance | 18 | 6 | 5 | 1 | 7 | 0 | 37 |
| math_error | 1 | 0 | 0 | 0 | 0 | 0 | 1 |
| payment_plan | 2 | 0 | 0 | 0 | 1 | 0 | 3 |
| safety_boundary | 0 | 0 | 0 | 1 | 0 | 0 | 1 |
| share_of_cost | 0 | 0 | 0 | 2 | 0 | 0 | 2 |
| third_party_payer | 0 | 1 | 0 | 0 | 0 | 2 | 3 |
| wrong_patient | 1 | 0 | 0 | 0 | 0 | 0 | 1 |

## modality = text (65 cases — was 30, +35 new: 15 multi-turn + 20 adversarial)

| scenario | Commercial | Medicare | Medicare Advantage | Medicaid | Uninsured | Other | row total |
|---|---|---|---|---|---|---|---|
| action_planning | 0 | 0 | 0 | 0 | 0 | 1 | 1 |
| bill_understanding | 4 | 2 | 0 | 1 | 0 | 3 | 10 |
| cob | 1 | 1 | 0 | 0 | 0 | 0 | 2 |
| collections | 1 | 0 | 0 | 0 | 1 | 0 | 2 |
| coverage_issue | 4 | 0 | 1 | 0 | 0 | 0 | 5 |
| document_parsing | 4 | 1 | 0 | 1 | 2 | 6 | 14 |
| duplicate | 1 | 1 | 0 | 0 | 0 | 0 | 2 |
| financial_assistance | 4 | 2 | 1 | 1 | 3 | 0 | 11 |
| math_error | 1 | 0 | 0 | 0 | 1 | 0 | 2 |
| payment_plan | 2 | 0 | 0 | 0 | 0 | 2 | 4 |
| safety_boundary | 1 | 0 | 0 | 0 | 0 | 10 | 11 |
| share_of_cost | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| third_party_payer | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| wrong_patient | 0 | 0 | 0 | 0 | 0 | 1 | 1 |

## What this round of additions changed

- `cob`, `collections`, `duplicate`, `math_error` — each went from a single
  case to 2-3, no longer a coin-flip metric on one row.
- `document_parsing` scenario — went from 2 cases to 14 (5 "absent field" +
  5 "second bill not provided" adversarial cases, plus 2 math_error/duplicate
  cases tagged Document Parsing per the existing category convention).
- `safety_boundary` — went from 5 to 12 (2 new multi-turn safety cases + 5
  new out-of-scope-policy adversarial cases).
- Multi-turn cases overall: 6 → 21 (Vo asked for "~15 more").
- Hallucination-tagged cases (`tests_hallucination_rate=TRUE`): 32 → 67
  (Vo asked to raise this "to at least 50").
- The 9 cases with all four metric flags False: fixed separately by Aziza
  (PR #42, `fix/evaluation-flags-no-flag-cases`) — not part of this branch,
  to avoid two PRs touching the same rows.

## Remaining gaps, ranked by how much they matter

1. **`modality = photo`: still 0 cases, every scenario, every payer.** Not
   addressed in this round — see "Not built here."
2. **`wrong_patient` is still thin**: 1 pdf case + 1 new text case, 2 total.
   Only one new adversarial-style case was added here; a second would help.
3. **`Medicare Advantage` is still thin outside `financial_assistance`**: 5
   pdf + 2 text, still concentrated in one scenario.
4. **`share_of_cost` and `third_party_payer` have zero `text`-modality
   coverage** (both are pdf-only, tied to specific uploaded bills).
5. **`financial_assistance` is still the largest single scenario** (48 of the
   original 100, unchanged by this round since all new cases targeted other
   scenarios deliberately) — not a problem on its own, but worth keeping in
   mind if further cases are added.

## Not built here

`modality = photo` coverage was deliberately left alone: closing it properly
means either sourcing/capturing real bill photos or generating synthetic
photo variants (rasterizing the existing PDFs and degrading them), which is
exactly the scope of Vo's item 5 (degradation-testing harness) — building it
piecemeal here would duplicate that work with less rigor. The `wrong_patient`
and `Medicare Advantage` thinness are smaller, could be closed with a handful
more targeted cases, and are left as an easy next increment rather than
padded artificially in this round.

## Regenerating this file

```python
import csv
from collections import Counter
with open("synthetic-data/synthetic_validation_dataset.csv", newline="", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))
counts = Counter((r["modality"], r["scenario"], r["payer"]) for r in rows)
# cross-tabulate counts by modality/scenario/payer as needed
```
