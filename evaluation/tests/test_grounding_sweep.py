"""Tests for grounding_sweep.py.

Unlike the other evaluation test modules, this one imports the real
bill_parser (to get real _provenance), so it needs the agent-harness
virtualenv, not the lighter environment the rest of evaluation/ runs
in:

    PYTHONPATH=agent-harness/src agent-harness/.venv/bin/python3 \\
        -m unittest evaluation.tests.test_grounding_sweep
"""

from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from evaluation.grounding_sweep import (
    conversation_text_for_row,
    load_bill_and_provenance_warnings,
    run_sweep,
)


class ConversationTextForRowTest(unittest.TestCase):
    def test_joins_input_and_followup(self) -> None:
        text = conversation_text_for_row(
            {"patient_input": "Hello", "patient_followup": "Follow-up"}
        )

        self.assertEqual(text, "Hello Follow-up")

    def test_skips_na_and_blank_fields(self) -> None:
        text = conversation_text_for_row(
            {"patient_input": "Hello", "patient_followup": "N/A"}
        )

        self.assertEqual(text, "Hello")


class LoadBillAndProvenanceWarningsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[2]

    def test_returns_empty_for_missing_bill_doc_file(self) -> None:
        bill_json, warnings = load_bill_and_provenance_warnings(self.repo_root, "N/A")

        self.assertEqual(bill_json, {})
        self.assertEqual(warnings, [])

    def test_parses_real_bill_and_surfaces_reconciliation_warning(self) -> None:
        bill_json, warnings = load_bill_and_provenance_warnings(
            self.repo_root, "bill_v2_intentionally_incorrect_math_13.json"
        )

        self.assertIn("total_billed", bill_json)
        self.assertIn("fails_total_reconciliation", warnings)

    def test_parses_real_bill_with_no_warnings(self) -> None:
        _bill_json, warnings = load_bill_and_provenance_warnings(
            self.repo_root, "bill_v2_selfpay_er_01.json"
        )

        self.assertEqual(warnings, [])


class RunSweepTest(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[2]

    def _write_review_csv(self, path: Path, rows: list[dict[str, str]]) -> None:
        fieldnames = [
            "case_id",
            "bill_doc_file",
            "patient_input",
            "patient_followup",
            "agent_final_response",
        ]
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow({field: row.get(field, "") for field in fieldnames})

    def test_skips_rows_without_a_recorded_response(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "review.csv"
            self._write_review_csv(
                csv_path,
                [{"case_id": "CASE-1", "bill_doc_file": "N/A", "agent_final_response": ""}],
            )

            summary = run_sweep(csv_path, repo_root=self.repo_root)

        self.assertEqual(summary.total_cases, 1)
        self.assertEqual(summary.checked_cases, 0)

    def test_flags_a_fabricated_amount_against_a_real_bill(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "review.csv"
            self._write_review_csv(
                csv_path,
                [
                    {
                        "case_id": "CASE-1",
                        "bill_doc_file": "bill_v2_selfpay_er_01.json",
                        "agent_final_response": "Your outstanding balance is $999,999.99.",
                    }
                ],
            )

            summary = run_sweep(csv_path, repo_root=self.repo_root)

        self.assertEqual(summary.checked_cases, 1)
        self.assertEqual(summary.grounded_count, 0)
        self.assertIn("999,999.99", summary.results[0].ungrounded_amounts)

    def test_surfaces_provenance_warnings_alongside_a_real_ungrounded_case(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "review.csv"
            self._write_review_csv(
                csv_path,
                [
                    {
                        "case_id": "CASE-1",
                        "bill_doc_file": "bill_v2_intentionally_incorrect_math_13.json",
                        "agent_final_response": "Your outstanding balance is $999,999.99.",
                    }
                ],
            )

            summary = run_sweep(csv_path, repo_root=self.repo_root)

        result = summary.results[0]
        self.assertFalse(result.grounded)
        self.assertIn("fails_total_reconciliation", result.provenance_warnings)


if __name__ == "__main__":
    unittest.main()
