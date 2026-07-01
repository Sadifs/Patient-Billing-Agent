from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from evaluation.evaluation_harness import (
    BILL_DIRECTORY_NAMES,
    EVALUATION_FLAG_COLUMNS,
    MANUAL_REVIEW_COLUMNS,
    REQUIRED_COLUMNS,
    load_dataset,
    synthetic_bill_exists,
    validate_dataset,
    write_manual_review_template,
)


class EvaluationHarnessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[2]
        self.dataset_path = self.repo_root / "synthetic-data" / "synthetic_validation_dataset.csv"

    def test_dataset_has_expected_schema(self) -> None:
        rows, columns = load_dataset(self.dataset_path)

        self.assertGreater(len(rows), 0)
        self.assertEqual(columns, REQUIRED_COLUMNS)

    def test_dataset_validation_passes_without_errors(self) -> None:
        rows, _columns = load_dataset(self.dataset_path)
        report = validate_dataset(self.dataset_path, self.repo_root)

        self.assertEqual(report.error_count, 0)
        self.assertEqual(report.warning_count, 0)
        self.assertEqual(report.row_count, len(rows))
        for column in EVALUATION_FLAG_COLUMNS:
            self.assertIn(column, report.evaluation_flag_counts)

    def test_referenced_v2_bill_files_are_discovered(self) -> None:
        rows, _columns = load_dataset(self.dataset_path)
        bill_files = {
            row["bill_doc_file"]
            for row in rows
            if row.get("bill_doc_file", "").strip().lower() not in {"", "n/a"}
        }

        self.assertIn("synthetic_bills_v2_agent", BILL_DIRECTORY_NAMES)
        self.assertGreater(len(bill_files), 0)
        for bill_file in bill_files:
            self.assertTrue(synthetic_bill_exists(self.repo_root, bill_file), bill_file)

    def test_manual_review_template_has_one_row_per_case(self) -> None:
        source_rows, _columns = load_dataset(self.dataset_path)
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "manual_review_template.csv"
            row_count = write_manual_review_template(self.dataset_path, output_path)

            self.assertEqual(row_count, len(source_rows))
            with output_path.open(newline="", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                rows = list(reader)

            self.assertEqual(reader.fieldnames, MANUAL_REVIEW_COLUMNS)
            self.assertEqual(len(rows), len(source_rows))
            self.assertEqual(rows[0]["agent_response"], "")
            self.assertIn("patient_input", rows[0])


if __name__ == "__main__":
    unittest.main()
