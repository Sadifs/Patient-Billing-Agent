"""Draft evaluation harness for the synthetic validation dataset.

This module intentionally focuses on dataset validation and manual-review
template generation. It does not call the live agent yet because the synthetic
dataset is still being finalized.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


REQUIRED_COLUMNS = [
    "case_id",
    "category",
    "document_type",
    "input_format",
    "insurance_type",
    "household_size",
    "annual_income_usd",
    "amount_owed_usd",
    "fpl_percentage",
    "expected_eligibility_tier",
    "patient_input",
    "agent_clarifying_question",
    "patient_followup",
    "expected_agent_response_summary",
    "expected_extracted_fields",
    "expected_next_steps",
    "safety_constraint",
    "tests_semantic_correctness",
    "tests_precision_recall",
    "tests_hallucination_rate",
    "tests_text_differentiation",
    "source_docs",
    "bill_doc_file",
]

REQUIRED_VALUE_COLUMNS = [
    "case_id",
    "category",
    "document_type",
    "input_format",
    "insurance_type",
    "patient_input",
    "expected_agent_response_summary",
    "expected_extracted_fields",
    "expected_next_steps",
    "safety_constraint",
    "source_docs",
    "bill_doc_file",
]

EVALUATION_FLAG_COLUMNS = [
    "tests_semantic_correctness",
    "tests_precision_recall",
    "tests_hallucination_rate",
    "tests_text_differentiation",
]

MANUAL_REVIEW_COLUMNS = [
    "case_id",
    "category",
    "document_type",
    "input_format",
    "insurance_type",
    "patient_input",
    "expected_agent_response_summary",
    "expected_extracted_fields",
    "expected_next_steps",
    "safety_constraint",
    "tests_semantic_correctness",
    "tests_precision_recall",
    "tests_hallucination_rate",
    "tests_text_differentiation",
    "agent_response",
    "passes_semantic_correctness",
    "passes_precision_recall",
    "passes_hallucination_check",
    "passes_text_differentiation",
    "passes_safety_constraint",
    "reviewer_notes",
]

TRUE_FALSE_VALUES = {"true", "false"}
EMPTY_MARKERS = {"", "n/a", "na", "none", "null"}
BILL_DIRECTORY_NAMES = [
    "synthetic_bills_v2_agent",
    "synthetic_bills_v2",
    "synthetic_bills",
]


@dataclass
class ValidationIssue:
    severity: str
    message: str
    case_id: str | None = None
    column: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "severity": self.severity,
            "message": self.message,
            "case_id": self.case_id,
            "column": self.column,
        }


@dataclass
class ValidationReport:
    dataset_path: str
    row_count: int
    columns: list[str]
    missing_columns: list[str] = field(default_factory=list)
    extra_columns: list[str] = field(default_factory=list)
    category_counts: dict[str, int] = field(default_factory=dict)
    insurance_type_counts: dict[str, int] = field(default_factory=dict)
    input_format_counts: dict[str, int] = field(default_factory=dict)
    document_type_counts: dict[str, int] = field(default_factory=dict)
    evaluation_flag_counts: dict[str, int] = field(default_factory=dict)
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "warning")

    @property
    def is_valid(self) -> bool:
        return self.error_count == 0

    def to_dict(self) -> dict:
        return {
            "dataset_path": self.dataset_path,
            "row_count": self.row_count,
            "column_count": len(self.columns),
            "missing_columns": self.missing_columns,
            "extra_columns": self.extra_columns,
            "category_counts": self.category_counts,
            "insurance_type_counts": self.insurance_type_counts,
            "input_format_counts": self.input_format_counts,
            "document_type_counts": self.document_type_counts,
            "evaluation_flag_counts": self.evaluation_flag_counts,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "is_valid": self.is_valid,
            "issues": [issue.to_dict() for issue in self.issues],
        }


def repo_root_from(path: Path) -> Path:
    """Find the repository root by walking upward from a path."""
    current = path.resolve()
    if current.is_file():
        current = current.parent
    for candidate in [current, *current.parents]:
        if (candidate / "synthetic-data").is_dir() and (candidate / "agent-harness").is_dir():
            return candidate
    return Path.cwd()


def default_dataset_path(repo_root: Path) -> Path:
    return repo_root / "synthetic-data" / "synthetic_validation_dataset.csv"


def load_dataset(dataset_path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with dataset_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        rows = [dict(row) for row in reader]
        columns = list(reader.fieldnames or [])
    return rows, columns


def normalized(value: str | None) -> str:
    return (value or "").strip()


def is_empty(value: str | None) -> bool:
    return normalized(value).lower() in EMPTY_MARKERS


def split_pipe_list(value: str | None) -> list[str]:
    return [item.strip() for item in normalized(value).split("|") if item.strip()]


def synthetic_bill_paths(repo_root: Path, bill_doc_file: str) -> list[Path]:
    """Return all supported locations for a referenced synthetic bill file."""
    synthetic_data_dir = repo_root / "synthetic-data"
    return [
        synthetic_data_dir / directory_name / bill_doc_file
        for directory_name in BILL_DIRECTORY_NAMES
    ]


def synthetic_bill_exists(repo_root: Path, bill_doc_file: str) -> bool:
    """Check current v2 bill folders first, with legacy fallback."""
    return any(path.exists() for path in synthetic_bill_paths(repo_root, bill_doc_file))


def count_true_flags(rows: Iterable[dict[str, str]]) -> dict[str, int]:
    counts = {column: 0 for column in EVALUATION_FLAG_COLUMNS}
    for row in rows:
        for column in EVALUATION_FLAG_COLUMNS:
            if normalized(row.get(column)).lower() == "true":
                counts[column] += 1
    return counts


def validate_dataset(dataset_path: Path, repo_root: Path | None = None) -> ValidationReport:
    rows, columns = load_dataset(dataset_path)
    repo_root = repo_root or repo_root_from(dataset_path)
    knowledge_dir = repo_root / "knowledge-docs"

    report = ValidationReport(
        dataset_path=str(dataset_path),
        row_count=len(rows),
        columns=columns,
        missing_columns=[column for column in REQUIRED_COLUMNS if column not in columns],
        extra_columns=[column for column in columns if column not in REQUIRED_COLUMNS],
        category_counts=dict(Counter(row.get("category", "") for row in rows)),
        insurance_type_counts=dict(Counter(row.get("insurance_type", "") for row in rows)),
        input_format_counts=dict(Counter(row.get("input_format", "") for row in rows)),
        document_type_counts=dict(Counter(row.get("document_type", "") for row in rows)),
        evaluation_flag_counts=count_true_flags(rows),
    )

    for column in report.missing_columns:
        report.issues.append(
            ValidationIssue("error", "Required column is missing", column=column)
        )

    seen_case_ids: set[str] = set()
    for row_number, row in enumerate(rows, start=2):
        case_id = normalized(row.get("case_id")) or f"row {row_number}"

        if case_id in seen_case_ids:
            report.issues.append(
                ValidationIssue("error", "Duplicate case_id", case_id=case_id, column="case_id")
            )
        seen_case_ids.add(case_id)

        for column in REQUIRED_VALUE_COLUMNS:
            if column in columns and normalized(row.get(column)) == "":
                report.issues.append(
                    ValidationIssue(
                        "error",
                        "Required value is blank",
                        case_id=case_id,
                        column=column,
                    )
                )

        flag_values = []
        for column in EVALUATION_FLAG_COLUMNS:
            if column not in columns:
                continue
            value = normalized(row.get(column)).lower()
            flag_values.append(value)
            if value not in TRUE_FALSE_VALUES:
                report.issues.append(
                    ValidationIssue(
                        "error",
                        "Evaluation flag must be True or False",
                        case_id=case_id,
                        column=column,
                    )
                )
        if flag_values and all(value == "false" for value in flag_values):
            report.issues.append(
                ValidationIssue(
                    "warning",
                    "Case does not opt into any evaluation flag",
                    case_id=case_id,
                )
            )

        if "source_docs" in columns:
            for source_doc in split_pipe_list(row.get("source_docs")):
                if not (knowledge_dir / source_doc).exists():
                    report.issues.append(
                        ValidationIssue(
                            "warning",
                            "Referenced source document was not found in knowledge-docs",
                            case_id=case_id,
                            column="source_docs",
                        )
                    )

        bill_doc = normalized(row.get("bill_doc_file"))
        if bill_doc and not is_empty(bill_doc) and not synthetic_bill_exists(repo_root, bill_doc):
            report.issues.append(
                ValidationIssue(
                    "warning",
                    "Referenced synthetic bill file was not found in supported synthetic bill folders",
                    case_id=case_id,
                    column="bill_doc_file",
                )
            )

    return report


def write_manual_review_template(dataset_path: Path, output_path: Path) -> int:
    rows, _columns = load_dataset(dataset_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANUAL_REVIEW_COLUMNS)
        writer.writeheader()
        for row in rows:
            output_row = {column: row.get(column, "") for column in MANUAL_REVIEW_COLUMNS}
            for column in [
                "agent_response",
                "passes_semantic_correctness",
                "passes_precision_recall",
                "passes_hallucination_check",
                "passes_text_differentiation",
                "passes_safety_constraint",
                "reviewer_notes",
            ]:
                output_row[column] = ""
            writer.writerow(output_row)

    return len(rows)


def print_human_report(report: ValidationReport) -> None:
    print(f"Dataset: {report.dataset_path}")
    print(f"Rows: {report.row_count}")
    print(f"Columns: {len(report.columns)}")
    print(f"Errors: {report.error_count}")
    print(f"Warnings: {report.warning_count}")
    print()
    print("Category counts:")
    for key, value in sorted(report.category_counts.items()):
        print(f"  {key}: {value}")
    print()
    print("Evaluation flag counts:")
    for key, value in sorted(report.evaluation_flag_counts.items()):
        print(f"  {key}: {value}")

    if report.issues:
        print()
        print("Issues:")
        for issue in report.issues:
            location = f" case={issue.case_id}" if issue.case_id else ""
            column = f" column={issue.column}" if issue.column else ""
            print(f"  [{issue.severity}] {issue.message}{location}{column}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Draft evaluation harness for the Cedars synthetic validation dataset."
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=None,
        help="Path to synthetic_validation_dataset.csv. Defaults to synthetic-data/synthetic_validation_dataset.csv.",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repository root. Defaults to auto-detection.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print validation report as JSON.",
    )

    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("validate", help="Validate dataset schema and references.")

    template_parser = subparsers.add_parser(
        "template",
        help="Create a manual evaluation template CSV.",
    )
    template_parser.add_argument(
        "--output",
        type=Path,
        default=Path("evaluation/manual_review_template.csv"),
        help="Where to write the manual review CSV.",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    repo_root = args.repo_root.resolve() if args.repo_root else repo_root_from(Path.cwd())
    dataset_path = args.dataset.resolve() if args.dataset else default_dataset_path(repo_root)

    command = args.command or "validate"
    if command == "validate":
        report = validate_dataset(dataset_path, repo_root)
        if args.json:
            print(json.dumps(report.to_dict(), indent=2))
        else:
            print_human_report(report)
        return 0 if report.is_valid else 1

    if command == "template":
        row_count = write_manual_review_template(dataset_path, args.output)
        print(f"Wrote {row_count} manual review rows to {args.output}")
        return 0

    parser.error(f"Unknown command: {command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
