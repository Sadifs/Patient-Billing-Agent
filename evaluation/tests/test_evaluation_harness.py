from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from evaluation.evaluation_harness import (
    BILL_DIRECTORY_NAMES,
    EVALUATION_FLAG_COLUMNS,
    LIVE_REVIEW_COLUMNS,
    MANUAL_REVIEW_COLUMNS,
    REQUIRED_COLUMNS,
    agent_prompt_for_row,
    load_dataset,
    live_review_output_row,
    parse_sse_text,
    selected_rows,
    synthetic_bill_exists,
    synthetic_bill_upload_path,
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

    def test_synthetic_bill_upload_path_prefers_pdf(self) -> None:
        upload_path = synthetic_bill_upload_path(
            self.repo_root,
            "bill_v2_collections_selfpay_21.json",
        )

        self.assertIsNotNone(upload_path)
        self.assertEqual(upload_path.suffix, ".pdf")

    def test_agent_prompt_rewrites_bill_reference_to_uploaded_pdf(self) -> None:
        row = {
            "patient_input": "[Patient uploads bill: bill_v2_test.json] — Can you explain this?",
            "bill_doc_file": "bill_v2_test.json",
        }

        prompt = agent_prompt_for_row(row, self.repo_root / "synthetic-data" / "synthetic_bills_v2" / "bill_v2_test.pdf")

        self.assertIn("bill_v2_test.pdf", prompt)
        self.assertNotIn("bill_v2_test.json", prompt)

    def test_selected_rows_filters_cases(self) -> None:
        rows, _columns = load_dataset(self.dataset_path)

        selected = selected_rows(rows, case_ids={"FA-001"}, limit=10)

        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["case_id"], "FA-001")

    def test_parse_sse_text_combines_text_chunks(self) -> None:
        body = (
            'data: {"text": "Hello"}\n\n'
            'data: {"text": " world"}\n\n'
            "data: [DONE]\n\n"
        )

        self.assertEqual(parse_sse_text(body), "Hello world")

    def test_live_review_output_row_has_metric_columns(self) -> None:
        rows, _columns = load_dataset(self.dataset_path)
        output_row = live_review_output_row(
            rows[0],
            uploaded_bill_file="",
            agent_initial_prompt="Prompt",
            agent_followup_prompt="",
            agent_initial_response="Initial",
            agent_followup_response="",
        )

        self.assertEqual(list(output_row.keys()), LIVE_REVIEW_COLUMNS)
        self.assertEqual(output_row["agent_initial_prompt"], "Prompt")
        self.assertEqual(output_row["agent_final_response"], "Initial")
        self.assertIn("semantic_correctness_score_0_1", output_row)
        self.assertIn("text_differentiation_score_1_5", output_row)


if __name__ == "__main__":
    unittest.main()
