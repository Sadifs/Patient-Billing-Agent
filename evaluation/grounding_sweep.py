"""Batch-run the grounding check across every already-recorded case in a
completed review CSV.

This is the no-infrastructure-needed slice of Professor Vo's "run this
over all cases" ask: it reuses each case's own already-recorded agent
response and already-uploaded bill file, so it needs no live agent
calls and no CI pipeline — just what's already on disk. Wiring this to
run automatically on every future PR still needs an actual CI pipeline
this repo doesn't have; that remains a separate infrastructure
decision, not something this script can substitute for.

For each case, this parses the case's own uploaded bill with the real
bill_parser (so grounding is checked against what the agent actually
had access to, including its _provenance block — not the bill's
source-of-truth generation JSON, which the agent never saw) and
reconstructs the conversation from patient_input/patient_followup. A
case with no uploaded bill (a conversational-only case) is still
checked, against the conversation alone.

When a case comes back ungrounded, this also reports whether the
underlying parse had a _provenance warning on the totals fields
(fails_total_reconciliation / low_ocr_confidence) — connecting
provenance tracking and the grounding check instead of leaving them as
two unrelated additions.

Requires the agent-harness virtualenv (parse_bill_file needs
pdfplumber/pytesseract/opencv), unlike grounding_check.py on its own:

    PYTHONPATH=agent-harness/src agent-harness/.venv/bin/python3 \\
        -m evaluation.grounding_sweep evaluation/results/midterm_agent_evaluation_scoring.csv
"""

from __future__ import annotations

import csv
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
_AGENT_HARNESS_SRC = _REPO_ROOT / "agent-harness" / "src"
if str(_AGENT_HARNESS_SRC) not in sys.path:
    sys.path.insert(0, str(_AGENT_HARNESS_SRC))

from app.tools.bill_parser import parse_bill_file  # noqa: E402

from evaluation.evaluation_harness import synthetic_bill_upload_path  # noqa: E402
from evaluation.grounding_check import check_grounding  # noqa: E402


@dataclass
class CaseGroundingResult:
    case_id: str
    grounded: bool
    ungrounded_amounts: list[str]
    ungrounded_codes: list[str]
    provenance_warnings: list[str]
    parse_error: str | None = None


@dataclass
class SweepSummary:
    total_cases: int
    checked_cases: int
    grounded_count: int
    results: list[CaseGroundingResult] = field(default_factory=list)

    @property
    def ungrounded_results(self) -> list[CaseGroundingResult]:
        return [result for result in self.results if not result.grounded]


def conversation_text_for_row(row: dict[str, str]) -> str:
    """Join the patient's own turns — a legitimate grounding source
    even though they aren't part of the bill (see grounding_check)."""
    parts = []
    for key in ("patient_input", "patient_followup"):
        value = (row.get(key) or "").strip()
        if value and value.upper() != "N/A":
            parts.append(value)
    return " ".join(parts)


def load_bill_and_provenance_warnings(
    repo_root: Path, bill_doc_file: str
) -> tuple[dict[str, Any], list[str]]:
    """Parse the case's own uploaded bill with the real bill_parser, so
    grounding is checked against what the agent actually saw. Returns
    ({}, []) for conversational-only cases with no bill on file."""
    if not bill_doc_file or bill_doc_file.strip().lower() == "n/a":
        return {}, []

    path = synthetic_bill_upload_path(repo_root, bill_doc_file)
    if path is None:
        return {}, []

    parsed = parse_bill_file(str(path))
    provenance = parsed.get("_provenance", {})
    warnings = sorted(
        {
            warning
            for field_entry in provenance.values()
            for warning in field_entry.get("warnings", [])
        }
    )
    return parsed, warnings


def run_sweep(review_csv_path: Path, repo_root: Path | None = None) -> SweepSummary:
    repo_root = repo_root or _REPO_ROOT
    with review_csv_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    results: list[CaseGroundingResult] = []
    for row in rows:
        case_id = (row.get("case_id") or "").strip()
        response = (row.get("agent_final_response") or row.get("agent_initial_response") or "").strip()
        if not response:
            continue

        bill_doc_file = row.get("bill_doc_file", "")
        parse_error: str | None = None
        try:
            bill_json, provenance_warnings = load_bill_and_provenance_warnings(
                repo_root, bill_doc_file
            )
        except Exception as exc:  # bill_parser raises on unreadable/missing files
            bill_json, provenance_warnings, parse_error = {}, [], str(exc)

        grounding = check_grounding(response, bill_json, conversation_text_for_row(row))
        results.append(
            CaseGroundingResult(
                case_id=case_id,
                grounded=grounding["grounded"],
                ungrounded_amounts=grounding["ungrounded_amounts"],
                ungrounded_codes=grounding["ungrounded_codes"],
                provenance_warnings=provenance_warnings,
                parse_error=parse_error,
            )
        )

    return SweepSummary(
        total_cases=len(rows),
        checked_cases=len(results),
        grounded_count=sum(1 for result in results if result.grounded),
        results=results,
    )


def format_report(summary: SweepSummary) -> str:
    lines = [
        f"Checked {summary.checked_cases}/{summary.total_cases} cases with a recorded response.",
        f"Grounded: {summary.grounded_count}/{summary.checked_cases}",
    ]
    if summary.ungrounded_results:
        lines.append("")
        lines.append("Ungrounded cases:")
        for result in summary.ungrounded_results:
            detail = []
            if result.ungrounded_amounts:
                detail.append(f"amounts={result.ungrounded_amounts}")
            if result.ungrounded_codes:
                detail.append(f"codes={result.ungrounded_codes}")
            if result.parse_error:
                detail.append(f"parse_error={result.parse_error}")
            note = ""
            if result.provenance_warnings:
                note = f" [bill parse warnings: {', '.join(result.provenance_warnings)}]"
            lines.append(f"  {result.case_id}: {'; '.join(detail)}{note}")
    return "\n".join(lines)


def main() -> None:
    import argparse

    arg_parser = argparse.ArgumentParser(description=__doc__)
    arg_parser.add_argument("review_csv", type=Path)
    args = arg_parser.parse_args()

    summary = run_sweep(args.review_csv)
    print(format_report(summary))


if __name__ == "__main__":
    main()
