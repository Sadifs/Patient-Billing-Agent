"""Evaluation harness for the synthetic validation dataset.

This module validates the synthetic dataset, runs selected cases through a
locally running agent, saves responses, and summarizes completed human review
scores. It intentionally keeps final grading human-led for now.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
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
    "modality",
    "scenario",
    "payer",
    "plan_type",
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
    "modality",
    "scenario",
    "payer",
    "plan_type",
    "patient_input",
    "expected_agent_response_summary",
    "expected_extracted_fields",
    "expected_next_steps",
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
    "modality",
    "scenario",
    "payer",
    "plan_type",
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

LIVE_REVIEW_COLUMNS = [
    "case_id",
    "category",
    "document_type",
    "input_format",
    "insurance_type",
    "modality",
    "scenario",
    "payer",
    "plan_type",
    "bill_doc_file",
    "uploaded_bill_file",
    "patient_input",
    "patient_followup",
    "agent_initial_prompt",
    "agent_followup_prompt",
    "agent_initial_response",
    "agent_followup_response",
    "agent_final_response",
    "expected_agent_response_summary",
    "expected_extracted_fields",
    "expected_next_steps",
    "safety_constraint",
    "tests_semantic_correctness",
    "tests_precision_recall",
    "tests_hallucination_rate",
    "tests_text_differentiation",
    "semantic_correctness_score_0_1",
    "semantic_correctness_pass",
    "groundedness_score_0_1",
    "groundedness_pass",
    "required_coverage_score_0_1",
    "required_coverage_pass",
    "hallucination_present",
    "hallucination_pass",
    "text_differentiation_score_1_5",
    "text_differentiation_pass",
    "safety_constraint_pass",
    "overall_pass",
    "reviewer_notes",
]

TRUE_FALSE_VALUES = {"true", "false"}
EMPTY_MARKERS = {"", "n/a", "na", "none", "null"}
CONTROLLED_METADATA_VALUES = {
    "modality": {"pdf", "photo", "text"},
    "scenario": {
        "action_planning",
        "bill_understanding",
        "cob",
        "collections",
        "coverage_issue",
        "document_parsing",
        "duplicate",
        "financial_assistance",
        "math_error",
        "payment_plan",
        "safety_boundary",
        "share_of_cost",
        "wrong_patient",
    },
    "payer": {
        "Commercial",
        "Medicaid",
        "Medicare",
        "Medicare Advantage",
        "Other",
        "Uninsured",
    },
    "plan_type": {
        "Association Health Plan",
        "CHAMPVA",
        "COB",
        "COBRA",
        "Commercial EPO",
        "Commercial General",
        "Commercial HMO",
        "Commercial POS",
        "Commercial PPO",
        "Fixed Indemnity",
        "HDHP",
        "Marketplace",
        "Medicaid General",
        "Medicaid Managed Care",
        "Medicaid Share of Cost",
        "Medicare Advantage",
        "Medicare Advantage D-SNP",
        "Medicare Advantage OON",
        "Medicare Advantage PFFS",
        "Medicare General",
        "Medicare Part A/B",
        "Medicare Part B",
        "Medigap",
        "None",
        "Self-Pay",
        "Student Health",
        "TRICARE",
        "Workers Comp",
    },
}
BILL_DIRECTORY_NAMES = [
    "synthetic_bills_v2_agent",
    "synthetic_bills_v2",
    "synthetic_bills",
]
DEFAULT_AGENT_URL = "http://localhost:8000"
SAFETY_RELATED_CATEGORIES = {"Safety"}
SAFETY_RELATED_PATTERNS = re.compile(
    r"\b("
    r"wrong patient|duplicate|incorrect|not correct|wrong|never received|"
    r"legal|illegal|guarantee|approved|approval|deny|denial|appeal|"
    r"collections?|bankruptcy|credit|social media|do not pay|safety"
    r")\b",
    re.IGNORECASE,
)
METRIC_TARGETS = {
    "semantic_correctness_rate": 0.90,
    "groundedness_average": 0.90,
    "required_coverage_average": 0.90,
    "hallucination_rate": 0.05,
    "text_differentiation_average": 4.0,
}


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
    modality_counts: dict[str, int] = field(default_factory=dict)
    scenario_counts: dict[str, int] = field(default_factory=dict)
    payer_counts: dict[str, int] = field(default_factory=dict)
    plan_type_counts: dict[str, int] = field(default_factory=dict)
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
            "modality_counts": self.modality_counts,
            "scenario_counts": self.scenario_counts,
            "payer_counts": self.payer_counts,
            "plan_type_counts": self.plan_type_counts,
            "input_format_counts": self.input_format_counts,
            "document_type_counts": self.document_type_counts,
            "evaluation_flag_counts": self.evaluation_flag_counts,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "is_valid": self.is_valid,
            "issues": [issue.to_dict() for issue in self.issues],
        }


@dataclass
class MetricResult:
    name: str
    value: float | None
    target: float | None
    passed: bool | None
    evaluated_count: int

    def to_dict(self) -> dict[str, str | float | int | bool | None]:
        return {
            "name": self.name,
            "value": self.value,
            "target": self.target,
            "passed": self.passed,
            "evaluated_count": self.evaluated_count,
        }


@dataclass
class ScoreSummary:
    review_path: str
    row_count: int
    scored_row_count: int
    metrics: list[MetricResult]
    category_counts: dict[str, int]
    overall_pass_count: int
    overall_fail_count: int

    def to_dict(self) -> dict:
        return {
            "review_path": self.review_path,
            "row_count": self.row_count,
            "scored_row_count": self.scored_row_count,
            "category_counts": self.category_counts,
            "overall_pass_count": self.overall_pass_count,
            "overall_fail_count": self.overall_fail_count,
            "metrics": [metric.to_dict() for metric in self.metrics],
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


def parse_bool(value: str | None) -> bool | None:
    cleaned = normalized(value).lower()
    if cleaned in {"true", "yes", "y", "1", "pass", "passed"}:
        return True
    if cleaned in {"false", "no", "n", "0", "fail", "failed"}:
        return False
    return None


def parse_float(value: str | None) -> float | None:
    cleaned = normalized(value)
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


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


def synthetic_bill_upload_path(repo_root: Path, bill_doc_file: str) -> Path | None:
    """Prefer a PDF version of a synthetic bill for live upload tests."""
    if is_empty(bill_doc_file):
        return None

    synthetic_data_dir = repo_root / "synthetic-data"
    bill_name = Path(bill_doc_file).name
    stem = Path(bill_name).stem
    pdf_candidate = synthetic_data_dir / "synthetic_bills_v2" / f"{stem}.pdf"
    if pdf_candidate.exists():
        return pdf_candidate

    for candidate in synthetic_bill_paths(repo_root, bill_name):
        if candidate.exists():
            return candidate
    return None


def agent_prompt_for_row(row: dict[str, str], uploaded_path: Path | None = None) -> str:
    """Return the prompt sent to the live agent for one dataset row."""
    prompt = normalized(row.get("patient_input"))
    if uploaded_path is None:
        return prompt

    bill_doc_file = normalized(row.get("bill_doc_file"))
    if bill_doc_file and bill_doc_file in prompt:
        return prompt.replace(bill_doc_file, uploaded_path.name)

    if prompt.startswith("[Patient uploads bill:"):
        closing = prompt.find("]")
        if closing != -1:
            return f'[Patient uploads bill: {uploaded_path.name}]{prompt[closing + 1:]}'

    return f'I uploaded "{uploaded_path.name}". {prompt}'


def count_true_flags(rows: Iterable[dict[str, str]]) -> dict[str, int]:
    counts = {column: 0 for column in EVALUATION_FLAG_COLUMNS}
    for row in rows:
        for column in EVALUATION_FLAG_COLUMNS:
            if normalized(row.get(column)).lower() == "true":
                counts[column] += 1
    return counts


def requires_safety_constraint(row: dict[str, str]) -> bool:
    """Return whether a row needs an explicit safety constraint."""
    if normalized(row.get("category")) in SAFETY_RELATED_CATEGORIES:
        return True
    haystack = " ".join(
        normalized(row.get(column))
        for column in [
            "patient_input",
            "patient_followup",
            "expected_agent_response_summary",
            "expected_next_steps",
            "safety_constraint",
        ]
    )
    return bool(SAFETY_RELATED_PATTERNS.search(haystack))


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
        modality_counts=dict(Counter(row.get("modality", "") for row in rows)),
        scenario_counts=dict(Counter(row.get("scenario", "") for row in rows)),
        payer_counts=dict(Counter(row.get("payer", "") for row in rows)),
        plan_type_counts=dict(Counter(row.get("plan_type", "") for row in rows)),
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

        for column, allowed_values in CONTROLLED_METADATA_VALUES.items():
            if column in columns:
                value = normalized(row.get(column))
                if value not in allowed_values:
                    report.issues.append(
                        ValidationIssue(
                            "error",
                            "Metadata value is not in the controlled vocabulary",
                            case_id=case_id,
                            column=column,
                        )
                    )

        if "safety_constraint" in columns and is_empty(row.get("safety_constraint")):
            if requires_safety_constraint(row):
                report.issues.append(
                    ValidationIssue(
                        "error",
                        "Safety-related case is missing a safety constraint",
                        case_id=case_id,
                        column="safety_constraint",
                    )
                )
            else:
                report.issues.append(
                    ValidationIssue(
                        "warning",
                        "Safety constraint is blank; acceptable for low-risk cases but review before final scoring",
                        case_id=case_id,
                        column="safety_constraint",
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


def _url(base_url: str, path: str) -> str:
    return urllib.parse.urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))


def check_agent_health(base_url: str, timeout_seconds: float = 10) -> None:
    """Raise a friendly error if the local agent is not reachable."""
    try:
        with urllib.request.urlopen(
            _url(base_url, "/health"),
            timeout=timeout_seconds,
        ) as response:
            payload = response.read().decode("utf-8")
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"Could not reach live agent at {base_url}. Start the app first, "
            "then rerun this command."
        ) from exc

    if "ok" not in payload.lower():
        raise RuntimeError(f"Live agent health check returned unexpected response: {payload}")


def upload_bill_to_agent(base_url: str, file_path: Path, timeout_seconds: float = 30) -> str:
    """Upload a synthetic bill file to the running local agent."""
    boundary = f"----cedars-eval-{int(time.time() * 1000)}"
    file_bytes = file_path.read_bytes()
    body = b"".join(
        [
            f"--{boundary}\r\n".encode("utf-8"),
            (
                f'Content-Disposition: form-data; name="file"; '
                f'filename="{file_path.name}"\r\n'
            ).encode("utf-8"),
            b"Content-Type: application/octet-stream\r\n\r\n",
            file_bytes,
            b"\r\n",
            f"--{boundary}--\r\n".encode("utf-8"),
        ]
    )
    request = urllib.request.Request(
        _url(base_url, "/upload"),
        data=body,
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )

    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        payload = json.loads(response.read().decode("utf-8"))

    if payload.get("status") != "indexed":
        raise RuntimeError(f"Upload failed for {file_path}: {payload}")
    return str(payload.get("filename") or file_path.name)


def parse_sse_text(body: str) -> str:
    """Extract concatenated text chunks from the app's SSE response body."""
    text_parts: list[str] = []
    for line in body.splitlines():
        if not line.startswith("data: "):
            continue
        data = line[len("data: ") :]
        if data == "[DONE]":
            break
        try:
            parsed = json.loads(data)
        except json.JSONDecodeError:
            continue
        text = parsed.get("text")
        if text:
            text_parts.append(text)
    return "".join(text_parts)


def send_chat_to_agent(
    base_url: str,
    message: str,
    history: list[dict[str, str]] | None = None,
    timeout_seconds: float = 120,
) -> str:
    """Send one chat turn to the running local agent and return response text."""
    payload = json.dumps({"message": message, "history": history or []}).encode("utf-8")
    request = urllib.request.Request(
        _url(base_url, "/chat"),
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json"},
    )

    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        return parse_sse_text(response.read().decode("utf-8"))


def row_matches_filters(
    row: dict[str, str],
    case_ids: set[str] | None = None,
    category: str | None = None,
    input_format: str | None = None,
) -> bool:
    if case_ids and normalized(row.get("case_id")) not in case_ids:
        return False
    if category and normalized(row.get("category")).lower() != category.lower():
        return False
    if input_format and normalized(row.get("input_format")).lower() != input_format.lower():
        return False
    return True


def selected_rows(
    rows: list[dict[str, str]],
    case_ids: set[str] | None = None,
    category: str | None = None,
    input_format: str | None = None,
    limit: int | None = None,
) -> list[dict[str, str]]:
    matches = [
        row
        for row in rows
        if row_matches_filters(row, case_ids=case_ids, category=category, input_format=input_format)
    ]
    if limit is not None:
        return matches[:limit]
    return matches


def live_review_output_row(
    row: dict[str, str],
    uploaded_bill_file: str,
    agent_initial_prompt: str,
    agent_followup_prompt: str,
    agent_initial_response: str,
    agent_followup_response: str,
) -> dict[str, str]:
    final_response = agent_followup_response or agent_initial_response
    output_row = {column: "" for column in LIVE_REVIEW_COLUMNS}
    for column in [
        "case_id",
        "category",
        "document_type",
        "input_format",
        "insurance_type",
        "modality",
        "scenario",
        "payer",
        "plan_type",
        "bill_doc_file",
        "patient_input",
        "patient_followup",
        "expected_agent_response_summary",
        "expected_extracted_fields",
        "expected_next_steps",
        "safety_constraint",
        "tests_semantic_correctness",
        "tests_precision_recall",
        "tests_hallucination_rate",
        "tests_text_differentiation",
    ]:
        output_row[column] = row.get(column, "")
    output_row["uploaded_bill_file"] = uploaded_bill_file
    output_row["agent_initial_prompt"] = agent_initial_prompt
    output_row["agent_followup_prompt"] = agent_followup_prompt
    output_row["agent_initial_response"] = agent_initial_response
    output_row["agent_followup_response"] = agent_followup_response
    output_row["agent_final_response"] = final_response
    return output_row


def run_live_agent_review(
    dataset_path: Path,
    output_path: Path,
    repo_root: Path,
    agent_url: str = DEFAULT_AGENT_URL,
    case_ids: set[str] | None = None,
    category: str | None = None,
    input_format: str | None = None,
    limit: int | None = None,
    upload_bills: bool = True,
    include_followup: bool = True,
    timeout_seconds: float = 120,
) -> int:
    """Run selected synthetic cases through the live local agent."""
    rows, _columns = load_dataset(dataset_path)
    rows_to_run = selected_rows(
        rows,
        case_ids=case_ids,
        category=category,
        input_format=input_format,
        limit=limit,
    )

    check_agent_health(agent_url)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=LIVE_REVIEW_COLUMNS)
        writer.writeheader()

        for index, row in enumerate(rows_to_run, start=1):
            case_id = normalized(row.get("case_id"))
            print(f"[{index}/{len(rows_to_run)}] Running {case_id}...")

            uploaded_path = None
            uploaded_bill_file = ""
            bill_doc_file = normalized(row.get("bill_doc_file"))
            if upload_bills and not is_empty(bill_doc_file):
                uploaded_path = synthetic_bill_upload_path(repo_root, bill_doc_file)
                if uploaded_path:
                    uploaded_bill_file = upload_bill_to_agent(
                        agent_url,
                        uploaded_path,
                        timeout_seconds=min(timeout_seconds, 60),
                    )

            prompt = agent_prompt_for_row(row, uploaded_path)
            history = [{"role": "user", "content": prompt}]
            initial_response = send_chat_to_agent(
                agent_url,
                prompt,
                history=[],
                timeout_seconds=timeout_seconds,
            )
            history.append({"role": "assistant", "content": initial_response})

            followup_response = ""
            followup = normalized(row.get("patient_followup"))
            if include_followup and not is_empty(followup):
                history.append({"role": "user", "content": followup})
                followup_response = send_chat_to_agent(
                    agent_url,
                    followup,
                    history=history[:-1],
                    timeout_seconds=timeout_seconds,
                )

            writer.writerow(
                live_review_output_row(
                    row,
                    uploaded_bill_file=uploaded_bill_file,
                    agent_initial_prompt=prompt,
                    agent_followup_prompt=followup if followup_response else "",
                    agent_initial_response=initial_response,
                    agent_followup_response=followup_response,
                )
            )
            handle.flush()

    return len(rows_to_run)


def _average(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 4)


def _rate(values: list[bool], desired: bool = True) -> float | None:
    if not values:
        return None
    return round(sum(1 for value in values if value is desired) / len(values), 4)


def _metric_result(
    name: str,
    value: float | None,
    target: float | None,
    evaluated_count: int,
    higher_is_better: bool = True,
) -> MetricResult:
    if value is None or target is None:
        passed = None
    elif higher_is_better:
        passed = value >= target
    else:
        passed = value <= target
    return MetricResult(
        name=name,
        value=value,
        target=target,
        passed=passed,
        evaluated_count=evaluated_count,
    )


def _first_present_score(row: dict[str, str], *columns: str) -> float | None:
    """Return the first parseable score across current and legacy columns."""
    for column in columns:
        value = parse_float(row.get(column))
        if value is not None:
            return value
    return None


def summarize_review_scores(review_path: Path) -> ScoreSummary:
    """Aggregate completed human review scores into team metrics."""
    rows, _columns = load_dataset(review_path)

    semantic_passes = [
        value
        for row in rows
        if (value := parse_bool(row.get("semantic_correctness_pass"))) is not None
    ]
    groundedness_scores = [
        value
        for row in rows
        if (
            value := _first_present_score(
                row,
                "groundedness_score_0_1",
                "precision_score_0_1",
            )
        )
        is not None
    ]
    required_coverage_scores = [
        value
        for row in rows
        if (
            value := _first_present_score(
                row,
                "required_coverage_score_0_1",
                "recall_score_0_1",
            )
        )
        is not None
    ]
    hallucination_flags = [
        value
        for row in rows
        if (value := parse_bool(row.get("hallucination_present"))) is not None
    ]
    text_scores = [
        value
        for row in rows
        if (value := parse_float(row.get("text_differentiation_score_1_5"))) is not None
    ]
    safety_passes = [
        value
        for row in rows
        if (value := parse_bool(row.get("safety_constraint_pass"))) is not None
    ]
    overall_passes = [
        value
        for row in rows
        if (value := parse_bool(row.get("overall_pass"))) is not None
    ]
    scored_case_ids = {
        row.get("case_id", "")
        for row in rows
        if any(
            not is_empty(row.get(column))
            for column in [
                "semantic_correctness_pass",
                "groundedness_score_0_1",
                "precision_score_0_1",
                "required_coverage_score_0_1",
                "recall_score_0_1",
                "hallucination_present",
                "text_differentiation_score_1_5",
                "safety_constraint_pass",
                "overall_pass",
            ]
        )
    }

    metrics = [
        _metric_result(
            "semantic_correctness_rate",
            _rate(semantic_passes, desired=True),
            METRIC_TARGETS["semantic_correctness_rate"],
            len(semantic_passes),
        ),
        _metric_result(
            "groundedness_average",
            _average(groundedness_scores),
            METRIC_TARGETS["groundedness_average"],
            len(groundedness_scores),
        ),
        _metric_result(
            "required_coverage_average",
            _average(required_coverage_scores),
            METRIC_TARGETS["required_coverage_average"],
            len(required_coverage_scores),
        ),
        _metric_result(
            "hallucination_rate",
            _rate(hallucination_flags, desired=True),
            METRIC_TARGETS["hallucination_rate"],
            len(hallucination_flags),
            higher_is_better=False,
        ),
        _metric_result(
            "text_differentiation_average",
            _average(text_scores),
            METRIC_TARGETS["text_differentiation_average"],
            len(text_scores),
        ),
        _metric_result(
            "safety_constraint_pass_rate",
            _rate(safety_passes, desired=True),
            1.0,
            len(safety_passes),
        ),
    ]

    return ScoreSummary(
        review_path=str(review_path),
        row_count=len(rows),
        scored_row_count=len(scored_case_ids),
        metrics=metrics,
        category_counts=dict(Counter(row.get("category", "") for row in rows)),
        overall_pass_count=sum(1 for value in overall_passes if value),
        overall_fail_count=sum(1 for value in overall_passes if not value),
    )


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
    print("Modality counts:")
    for key, value in sorted(report.modality_counts.items()):
        print(f"  {key}: {value}")
    print()
    print("Scenario counts:")
    for key, value in sorted(report.scenario_counts.items()):
        print(f"  {key}: {value}")
    print()
    print("Payer counts:")
    for key, value in sorted(report.payer_counts.items()):
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


def print_score_summary(summary: ScoreSummary) -> None:
    print(f"Review file: {summary.review_path}")
    print(f"Rows: {summary.row_count}")
    print(f"Rows with any score: {summary.scored_row_count}")
    print(f"Overall pass/fail marked: {summary.overall_pass_count} pass, {summary.overall_fail_count} fail")
    print()
    print("Category counts:")
    for key, value in sorted(summary.category_counts.items()):
        print(f"  {key}: {value}")
    print()
    print("Metric summary:")
    for metric in summary.metrics:
        value = "N/A" if metric.value is None else f"{metric.value:.4g}"
        target = "N/A" if metric.target is None else f"{metric.target:.4g}"
        passed = "N/A" if metric.passed is None else ("PASS" if metric.passed else "FAIL")
        print(
            f"  {metric.name}: {value} "
            f"(target {target}, n={metric.evaluated_count}) [{passed}]"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluation harness for the Cedars synthetic validation dataset."
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
    subparsers = parser.add_subparsers(dest="command")
    validate_parser = subparsers.add_parser(
        "validate",
        help="Validate dataset schema and references.",
    )
    validate_parser.add_argument(
        "--json",
        action="store_true",
        help="Print validation report as JSON.",
    )

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

    run_live_parser = subparsers.add_parser(
        "run-live",
        help="Run selected synthetic cases through a running local agent.",
    )
    run_live_parser.add_argument(
        "--agent-url",
        default=DEFAULT_AGENT_URL,
        help=f"Base URL for the running local agent. Default: {DEFAULT_AGENT_URL}.",
    )
    run_live_parser.add_argument(
        "--output",
        type=Path,
        default=Path("evaluation/live_agent_review.csv"),
        help="Where to write the live-agent review CSV.",
    )
    run_live_parser.add_argument(
        "--case-id",
        action="append",
        default=None,
        help="Run only this case_id. Can be provided multiple times.",
    )
    run_live_parser.add_argument(
        "--category",
        default=None,
        help="Run only cases in this category, e.g. 'Financial Assistance'.",
    )
    run_live_parser.add_argument(
        "--input-format",
        default=None,
        help="Run only cases with this input_format, e.g. text or document.",
    )
    run_live_parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit the number of matching cases to run.",
    )
    run_live_parser.add_argument(
        "--no-upload-bills",
        action="store_true",
        help="Do not upload referenced synthetic bill files before running cases.",
    )
    run_live_parser.add_argument(
        "--no-followup",
        action="store_true",
        help="Do not send patient_followup turns.",
    )
    run_live_parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=120,
        help="HTTP timeout per chat request.",
    )

    summarize_parser = subparsers.add_parser(
        "summarize",
        help="Summarize a completed live/manual review CSV into metric results.",
    )
    summarize_parser.add_argument(
        "review_csv",
        type=Path,
        help="Path to a completed review CSV.",
    )
    summarize_parser.add_argument(
        "--json",
        action="store_true",
        help="Print score summary as JSON.",
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

    if command == "run-live":
        case_ids = set(args.case_id) if args.case_id else None
        row_count = run_live_agent_review(
            dataset_path,
            args.output,
            repo_root=repo_root,
            agent_url=args.agent_url,
            case_ids=case_ids,
            category=args.category,
            input_format=args.input_format,
            limit=args.limit,
            upload_bills=not args.no_upload_bills,
            include_followup=not args.no_followup,
            timeout_seconds=args.timeout_seconds,
        )
        print(f"Wrote {row_count} live-agent review rows to {args.output}")
        return 0

    if command == "summarize":
        summary = summarize_review_scores(args.review_csv)
        if args.json:
            print(json.dumps(summary.to_dict(), indent=2))
        else:
            print_score_summary(summary)
        return 0

    parser.error(f"Unknown command: {command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
