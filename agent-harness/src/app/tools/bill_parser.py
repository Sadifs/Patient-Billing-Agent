"""Parse uploaded patient bill PDFs into structured JSON.

Extracts line items, billing codes (CPT, HCPCS, ICD-10), service dates,
and dollar amounts using pdfplumber for text and table extraction.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import pdfplumber

from agent_harness import tool

# ── Patterns ────────────────────────────────────────────────────────────

DATE_PATTERNS = [
    re.compile(r"\b(\d{1,2}/\d{1,2}/\d{2,4})\b"),
    re.compile(r"\b(\d{1,2}-\d{1,2}-\d{2,4})\b"),
    re.compile(r"\b(\d{4}-\d{2}-\d{2})\b"),
]

AMOUNT_PATTERN = re.compile(
    r"(?:\(\s*)?\$?\s*([\d,]+\.\d{2})(?:\s*\))?"
)

# CPT (5 digits, optional modifier), HCPCS (letter + 4 digits), ICD-10-CM
CPT_PATTERN = re.compile(r"\b(\d{5}(?:-[A-Z0-9]{2})?)\b")
HCPCS_PATTERN = re.compile(r"\b([A-Z]\d{4})\b")
ICD10_PATTERN = re.compile(r"\b([A-Z]\d{2}(?:\.\d{1,4})?)\b")

LINE_ITEM_KEYWORDS = re.compile(
    r"\b(charge|service|procedure|supply|medication|lab|radiology|room|fee)\b",
    re.IGNORECASE,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent

DEFAULT_KNOWLEDGE_DIRS = [
    Path(os.environ.get("UPLOAD_DIR", "/tmp/uploads")).expanduser(),
    Path("/app/uploads"),
    _REPO_ROOT / "knowledge-docs",
    Path("/app/knowledge-docs"),
]


def _resolve_pdf_path(file_path: str) -> Path:
    """Resolve a PDF path from an absolute path, relative path, or filename."""
    candidate = Path(file_path).expanduser()
    if candidate.is_file():
        return candidate

    for base in DEFAULT_KNOWLEDGE_DIRS:
        resolved = base / file_path
        if resolved.is_file():
            return resolved

    raise FileNotFoundError(f"PDF not found: {file_path}")


def _normalize_date(raw: str) -> str:
    """Return dates in MM/DD/YYYY when possible."""
    raw = raw.strip()
    for sep in ("/", "-"):
        if sep in raw:
            parts = raw.split(sep)
            if len(parts) == 3:
                a, b, c = parts
                if len(c) == 2:
                    c = f"20{c}" if int(c) < 50 else f"19{c}"
                if len(a) == 4:
                    return f"{b.zfill(2)}/{c.zfill(2)}/{a}"
                return f"{a.zfill(2)}/{b.zfill(2)}/{c}"
    return raw


def _parse_amount(raw: str) -> float | None:
    """Parse a dollar string into a float; parentheses indicate negative."""
    cleaned = raw.replace("$", "").replace(",", "").strip()
    if not cleaned:
        return None
    negative = raw.strip().startswith("(") and raw.strip().endswith(")")
    try:
        value = float(cleaned)
    except ValueError:
        return None
    return -value if negative else value


def _extract_billing_codes(text: str) -> list[dict[str, str]]:
    """Collect unique billing codes with their type."""
    codes: dict[str, str] = {}

    for match in CPT_PATTERN.finditer(text):
        code = match.group(1)
        if code.isdigit() or "-" in code:
            codes.setdefault(code, "CPT")

    for match in HCPCS_PATTERN.finditer(text):
        code = match.group(1)
        codes.setdefault(code, "HCPCS")

    for match in ICD10_PATTERN.finditer(text):
        code = match.group(1)
        if not re.fullmatch(r"[A-Z]\d{4}", code):
            codes.setdefault(code, "ICD-10")

    return [{"code": code, "type": code_type} for code, code_type in sorted(codes.items())]


def _extract_dates(text: str) -> list[str]:
    dates: list[str] = []
    seen: set[str] = set()
    for pattern in DATE_PATTERNS:
        for match in pattern.finditer(text):
            normalized = _normalize_date(match.group(1))
            if normalized not in seen:
                seen.add(normalized)
                dates.append(normalized)
    return dates


def _extract_amounts(text: str) -> list[dict[str, Any]]:
    amounts: list[dict[str, Any]] = []
    seen: set[float] = set()
    for match in AMOUNT_PATTERN.finditer(text):
        value = _parse_amount(match.group(0))
        if value is None or value in seen:
            continue
        seen.add(value)
        start = max(0, match.start() - 40)
        end = min(len(text), match.end() + 40)
        amounts.append({
            "amount": value,
            "raw": match.group(0).strip(),
            "context": text[start:end].replace("\n", " ").strip(),
        })
    return amounts


def _codes_in_text(text: str) -> list[str]:
    return [entry["code"] for entry in _extract_billing_codes(text)]


def _line_item_from_text(line: str) -> dict[str, Any] | None:
    """Heuristically parse a single text line into a line item."""
    stripped = line.strip()
    if len(stripped) < 5:
        return None

    amount_matches = list(AMOUNT_PATTERN.finditer(stripped))
    if not amount_matches:
        return None

    last_amount = amount_matches[-1]
    amount = _parse_amount(last_amount.group(0))
    if amount is None:
        return None

    date = None
    for pattern in DATE_PATTERNS:
        date_match = pattern.search(stripped)
        if date_match:
            date = _normalize_date(date_match.group(1))
            break

    description = stripped
    for pattern in DATE_PATTERNS:
        description = pattern.sub("", description)
    description = AMOUNT_PATTERN.sub("", description)
    for code in _codes_in_text(stripped):
        description = description.replace(code, "")
    description = re.sub(r"\s{2,}", " ", description).strip(" -|:\t")

    codes = _codes_in_text(stripped)
    if not description and not codes:
        return None
    if not description and not LINE_ITEM_KEYWORDS.search(stripped) and not codes:
        return None

    return {
        "date": date,
        "description": description or None,
        "billing_codes": codes,
        "amount": amount,
        "raw_line": stripped,
    }


def _parse_line_items_from_text(text: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line in text.splitlines():
        item = _line_item_from_text(line)
        if item and item["raw_line"] not in seen:
            seen.add(item["raw_line"])
            items.append(item)
    return items


def _header_index(headers: list[str | None], *candidates: str) -> int | None:
    lowered = [(h or "").strip().lower() for h in headers]
    for candidate in candidates:
        for idx, header in enumerate(lowered):
            if candidate in header:
                return idx
    return None


def _cell_value(row: list[Any], index: int | None) -> str | None:
    if index is None or index >= len(row):
        return None
    value = row[index]
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_line_items_from_tables(tables: list[list[list[Any]]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seen: set[str] = set()

    for table in tables:
        if not table or len(table) < 2:
            continue

        headers = [str(cell).strip() if cell is not None else "" for cell in table[0]]
        date_idx = _header_index(headers, "date", "service date", "dos")
        desc_idx = _header_index(headers, "description", "service", "procedure", "item")
        code_idx = _header_index(headers, "code", "cpt", "hcpcs", "procedure code")
        amount_idx = _header_index(headers, "charge", "amount", "billed", "total", "balance")

        if desc_idx is None and code_idx is None and amount_idx is None:
            continue

        for row in table[1:]:
            if not row or all(cell is None or str(cell).strip() == "" for cell in row):
                continue

            row_text = " | ".join(str(cell).strip() for cell in row if cell is not None)
            date_value = _cell_value(row, date_idx)
            if date_value:
                date_value = _normalize_date(date_value)

            description = _cell_value(row, desc_idx)
            code_value = _cell_value(row, code_idx)
            amount_value = _cell_value(row, amount_idx)

            amount = _parse_amount(amount_value) if amount_value else None
            if amount is None:
                amount_matches = list(AMOUNT_PATTERN.finditer(row_text))
                if amount_matches:
                    amount = _parse_amount(amount_matches[-1].group(0))

            codes = _codes_in_text(row_text)
            if code_value and code_value not in codes:
                codes.insert(0, code_value)

            if amount is None and not description and not codes:
                continue

            item = {
                "date": date_value,
                "description": description,
                "billing_codes": codes,
                "amount": amount,
                "raw_line": row_text,
            }
            if item["raw_line"] not in seen:
                seen.add(item["raw_line"])
                items.append(item)

    return items


def _extract_pdf_content(path: Path) -> tuple[str, list[list[list[Any]]], int]:
    text_parts: list[str] = []
    tables: list[list[list[Any]]] = []
    page_count = 0

    with pdfplumber.open(path) as pdf:
        page_count = len(pdf.pages)
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            if page_text:
                text_parts.append(page_text)

            page_tables = page.extract_tables() or []
            for table in page_tables:
                if table:
                    tables.append(table)

    return "\n\n".join(text_parts), tables, page_count


def parse_bill_pdf(file_path: str) -> dict[str, Any]:
    """Parse a bill PDF and return structured extraction results."""
    path = _resolve_pdf_path(file_path)
    if path.suffix.lower() != ".pdf":
        raise ValueError(f"Expected a PDF file, got: {path.suffix}")

    text, tables, page_count = _extract_pdf_content(path)
    table_items = _parse_line_items_from_tables(tables)
    text_items = _parse_line_items_from_text(text)
    line_items = table_items if table_items else text_items

    billing_codes = _extract_billing_codes(text)
    for item in line_items:
        for code in item.get("billing_codes", []):
            if code not in {entry["code"] for entry in billing_codes}:
                billing_codes.append({"code": code, "type": "unknown"})

    return {
        "source_file": str(path),
        "filename": path.name,
        "page_count": page_count,
        "dates": _extract_dates(text),
        "billing_codes": billing_codes,
        "amounts": _extract_amounts(text),
        "line_items": line_items,
        "line_item_count": len(line_items),
        "parse_method": "tables" if table_items else "text",
    }


@tool(
    name="bill_parser",
    description=(
        "Parse an uploaded patient bill PDF and return structured JSON with "
        "line items, billing codes (CPT, HCPCS, ICD-10), service dates, "
        "and dollar amounts. Pass the uploaded filename or full path."
    ),
    parameters={
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": (
                    "Filename or path of the uploaded bill PDF "
                    "(e.g. 'sample_bill_pdf.pdf')"
                ),
            },
        },
        "required": ["file_path"],
    },
)
def bill_parser(args: dict) -> str:
    file_path = args.get("file_path", "").strip()
    if not file_path:
        return json.dumps({"error": "file_path is required"})

    try:
        result = parse_bill_pdf(file_path)
        return json.dumps(result)
    except FileNotFoundError as exc:
        return json.dumps({"error": str(exc)})
    except ValueError as exc:
        return json.dumps({"error": str(exc)})
    except Exception as exc:
        return json.dumps({"error": f"Failed to parse bill PDF: {exc}"})
