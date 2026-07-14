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

PATIENT_NAME_PATTERN = re.compile(
    r"Patient:\s*(.+?)\s+(?:DOB|Address|Account\s*#?):",
    re.IGNORECASE,
)
PATIENT_NAME_FALLBACK_PATTERN = re.compile(
    r"^(.+?)\s+A l Pay Online:",
    re.MULTILINE,
)
GUARANTOR_NAME_PATTERN = re.compile(r"Guarantor Name:\s*(.+)", re.IGNORECASE)
GUARANTOR_NUMBER_PATTERN = re.compile(
    r"Guarantor\s*(?:#|Number):\s*(\S+)",
    re.IGNORECASE,
)
ACCOUNT_NUMBER_PATTERN = re.compile(r"Account\s*#:\s*(\S+)", re.IGNORECASE)
SERVICE_DATE_PATTERN = re.compile(r"Service Date:\s*(\S+)", re.IGNORECASE)
PAY_ONLINE_PATTERN = re.compile(r"Pay Online:\s*(\S+)", re.IGNORECASE)
PAY_BY_PHONE_PATTERN = re.compile(r"Pay by Phone:\s*([\d-]+)", re.IGNORECASE)
CALL_PHONE_PATTERN = re.compile(
    r"\b(?:call|assistance, call)\s+([\d-]+)",
    re.IGNORECASE,
)
PATIENT_SERVICES_EMAIL_PATTERN = re.compile(
    r"\b([A-Z0-9._%+-]+@cshs\.org)\b",
    re.IGNORECASE,
)
PATIENT_SERVICES_HOURS_PATTERN = re.compile(
    r"(Monday[–-]Friday,[^,\n]*?\bPT\b)",
    re.IGNORECASE,
)
PATIENT_SERVICES_MAIL_PATTERN = re.compile(
    r"(Cedars-Sinai Medical Center, P\.O\. Box \d+, Los Angeles, CA \d{5})",
    re.IGNORECASE,
)
PO_BOX_MERGE_PATTERN = re.compile(
    r"(?:P[\.\)\s]*O[\.\)\s]*\.?\s*Box|Box\s+48750|Los Angeles, CA 90048|\)\s*48750)",
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
                if len(a) == 4:
                    return f"{b.zfill(2)}/{c.zfill(2)}/{a}"
                if len(c) == 4:
                    return f"{a.zfill(2)}/{b.zfill(2)}/{c}"
                if len(c) == 2:
                    c = f"20{c}" if int(c) < 50 else f"19{c}"
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


def _first_line(value: str | None) -> str | None:
    if not value:
        return None
    line = value.strip().split("\n", 1)[0].strip()
    return line or None


def _strip_corrupted_parenthetical(value: str) -> str:
    """Remove parentheticals corrupted by PDF text-merge with mailing addresses."""

    def is_corrupted(inner: str) -> bool:
        if re.search(r"Box|48750|Los Angeles|P[\.\)]\s*O", inner, re.IGNORECASE):
            return True
        if len(re.findall(r"\b[A-Za-z]\.", inner)) >= 2:
            return True
        if len(re.findall(r"[^\w\s\-–(),./&+]", inner)) > 2:
            return True
        return False

    cleaned = value
    changed = True
    while changed:
        changed = False
        match = re.search(r"\([^)]*\)", cleaned)
        if not match:
            break
        inner = match.group(0)[1:-1]
        if is_corrupted(inner):
            cleaned = (cleaned[: match.start()] + cleaned[match.end() :]).strip()
            changed = True
    cleaned = re.sub(r"\([^)]*$", "", cleaned).strip()
    return cleaned


def _clean_insurance_value(value: str | None) -> str | None:
    """Clean payer text extracted from PDF lines."""
    cleaned = _first_line(value)
    if not cleaned:
        return None

    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -:\t")
    cleaned = re.split(r"\s+Secondary Insurance:", cleaned, maxsplit=1)[0].strip()
    cleaned = re.split(
        r"\s+(?:Guarantor|Patient:|Account #:)",
        cleaned,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0].strip(" -:\t")
    merge = PO_BOX_MERGE_PATTERN.search(cleaned)
    if merge:
        cleaned = cleaned[: merge.start()]
    cleaned = re.sub(
        r"sponso\s*Pre\.?O\.?d\.?",
        "sponsored",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = _strip_corrupted_parenthetical(cleaned)
    return cleaned.strip(" .,") or None


def _extract_insurance_info(text: str) -> dict[str, str | None]:
    """Extract primary and secondary insurance labels from bill text."""
    primary_match = re.search(r"Primary Insurance:\s*([^\n\r]+)", text, re.IGNORECASE)
    secondary_match = re.search(r"Secondary Insurance:\s*([^\n\r]+)", text, re.IGNORECASE)
    return {
        "primary": _clean_insurance_value(primary_match.group(1) if primary_match else None),
        "secondary": _clean_insurance_value(secondary_match.group(1) if secondary_match else None),
    }


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
    for line in text.splitlines():
        item = _line_item_from_text(line)
        if item:
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


def _amounts_from_cell(value: str | None) -> list[float]:
    """Return all dollar amounts found in a table cell."""
    if not value:
        return []
    amounts: list[float] = []
    for match in AMOUNT_PATTERN.finditer(value):
        amount = _parse_amount(match.group(0))
        if amount is not None:
            amounts.append(amount)
    return amounts


def _parse_line_items_from_tables(tables: list[list[list[Any]]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []

    for table in tables:
        if not table or len(table) < 2:
            continue

        headers = [str(cell).strip() if cell is not None else "" for cell in table[0]]
        date_idx = _header_index(headers, "date", "service date", "dos")
        desc_idx = _header_index(headers, "description", "service", "procedure", "item")
        code_idx = _header_index(headers, "code", "cpt", "hcpcs", "procedure code")
        billed_idx = _header_index(headers, "billed", "charge", "amount")
        insurance_idx = _header_index(
            headers,
            "ins pmts",
            "insurance payments",
            "insurance paid",
            "ins. paid",
            "ins paid",
            "pmts",
        )
        adjustment_idx = _header_index(headers, "adjustment", "adjustments", "adj")
        patient_balance_idx = _header_index(
            headers,
            "patient bal",
            "patient balance",
            "responsibility",
            "pt. resp",
            "pt resp",
        )
        amount_idx = billed_idx or _header_index(headers, "total", "balance")

        if desc_idx is None and code_idx is None:
            continue

        for row in table[1:]:
            if not row or all(cell is None or str(cell).strip() == "" for cell in row):
                continue

            row_text = " | ".join(str(cell).strip() for cell in row if cell is not None)
            date_value = _cell_value(row, date_idx)
            if date_value:
                date_value = _normalize_date(date_value)

            description = _cell_value(row, desc_idx)
            if description and description.strip().lower() in {"total", "totals"}:
                continue

            code_value = _cell_value(row, code_idx)
            amount_value = _cell_value(row, amount_idx)
            billed_value = _cell_value(row, billed_idx)
            insurance_value = _cell_value(row, insurance_idx)
            adjustment_value = _cell_value(row, adjustment_idx)
            patient_balance_value = _cell_value(row, patient_balance_idx)

            billed_amount = _parse_amount(billed_value) if billed_value else None
            insurance_payments = _parse_amount(insurance_value) if insurance_value else None
            adjustments = _parse_amount(adjustment_value) if adjustment_value else None
            patient_balance = _parse_amount(patient_balance_value) if patient_balance_value else None

            if adjustment_idx == patient_balance_idx:
                combined_amounts = _amounts_from_cell(adjustment_value)
                if len(combined_amounts) >= 2:
                    adjustments = combined_amounts[0]
                    patient_balance = combined_amounts[1]

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
                "billed_amount": billed_amount,
                "insurance_payments": insurance_payments,
                "adjustments": adjustments,
                "patient_balance": patient_balance,
                "raw_line": row_text,
            }
            items.append(item)

    return items


def _line_item_duplicate_signals(line_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return potential duplicate line-item signals for repeated bill rows."""
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for index, item in enumerate(line_items, start=1):
        codes = item.get("billing_codes") or []
        primary_code = codes[0] if codes else None
        description = str(item.get("description") or "").strip().lower()
        if not primary_code and not description:
            continue

        key = (
            item.get("date"),
            primary_code,
            description,
            item.get("billed_amount") if item.get("billed_amount") is not None else item.get("amount"),
            item.get("patient_balance"),
        )
        grouped.setdefault(key, []).append({"index": index, "item": item})

    signals: list[dict[str, Any]] = []
    for entries in grouped.values():
        if len(entries) < 2:
            continue
        first = entries[0]["item"]
        signals.append(
            {
                "description": first.get("description"),
                "code": (first.get("billing_codes") or [None])[0],
                "date": first.get("date"),
                "occurrences": len(entries),
                "line_item_numbers": [entry["index"] for entry in entries],
                "billed_amount_each": first.get("billed_amount")
                if first.get("billed_amount") is not None
                else first.get("amount"),
                "patient_balance_each": first.get("patient_balance"),
                "guidance": (
                    "Potential duplicate line item. Do not say it is definitely "
                    "incorrect; tell the patient to ask Cedars-Sinai billing to "
                    "verify why the same service/code appears more than once."
                ),
            }
        )
    return signals


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


def _bill_flags(text: str, line_items: list[dict[str, Any]]) -> dict[str, Any]:
    """Return high-level billing signals useful for patient guidance."""
    combined = " ".join(
        [text]
        + [
            str(item.get("description") or item.get("raw_line") or "")
            for item in line_items
        ]
    ).lower()

    has_collections_fee = any(
        "collection" in str(item.get("description") or item.get("raw_line") or "").lower()
        or "agency assessment" in str(item.get("description") or item.get("raw_line") or "").lower()
        for item in line_items
    )
    self_pay_signal = bool(
        re.search(r"\b(self-pay|self pay|no insurance|uninsured)\b", combined)
    )
    primary_no_insurance = bool(
        re.search(
            r"\bprimary\s+insurance\s*:?\s*(none on file|self-pay|self pay|no insurance|uninsured)\b",
            combined,
        )
    )
    primary_has_payer = bool(
        re.search(
            r"\bprimary\s+insurance\s*:?\s*(?!none on file|self-pay|self pay|no insurance|uninsured)[a-z0-9]",
            combined,
        )
    )
    none_on_file_without_primary_payer = "none on file" in combined and not primary_has_payer
    no_insurance_on_file = (
        self_pay_signal
        or primary_no_insurance
        or none_on_file_without_primary_payer
    )
    duplicate_signals = _line_item_duplicate_signals(line_items)

    return {
        "no_insurance_or_self_pay_signal": no_insurance_on_file,
        "collections_signal": "collections" in combined or has_collections_fee,
        "collections_fee_signal": has_collections_fee,
        "potential_duplicate_line_item_signal": bool(duplicate_signals),
        "potential_duplicate_line_items": duplicate_signals,
        "recommended_guidance_if_true": (
            "If no_insurance_or_self_pay_signal or collections_signal is true, "
            "explain that financial assistance may still be available, ask for "
            "household size and annual income if missing, recommend calling "
            "Cedars-Sinai Patient Financial Services at [866-803-1777](tel:8668031777) "
            "(Monday–Friday, 8:00 AM–4:30 PM PT) or emailing patient.billing@cshs.org, ask "
            "billing/collections to pause collection activity during FAP review, "
            "and ask whether any collections fee can be reviewed or waived. "
            "If potential_duplicate_line_item_signal is true, explain that the "
            "same service/code appears more than once and suggest asking "
            "Cedars-Sinai billing to verify before paying."
        ),
    }


def _suggested_next_steps(flags: dict[str, Any]) -> list[str]:
    """Return patient-facing next steps triggered by parser flags."""
    if not (
        flags.get("no_insurance_or_self_pay_signal")
        or flags.get("collections_signal")
    ):
        return []

    steps = [
        "Call [866-803-1777](tel:8668031777) (Monday–Friday, 8:00 AM–4:30 PM PT) or email patient.billing@cshs.org to apply for financial assistance with Cedars-Sinai Patient Financial Services.",
        "Ask billing or collections to pause collection activity while your financial-assistance application is reviewed.",
        "Cedars-Sinai may offer payment assistance based partly on your Federal Poverty Level (FPL). If you share your household size and approximate annual household income, I can estimate your FPL percentage and suggest next steps.",
    ]
    if flags.get("collections_fee_signal"):
        steps.append(
            "Ask whether the collections fee can be reviewed, waived, or adjusted if financial assistance is approved."
        )
    return steps


def _extract_patient_name(text: str) -> str | None:
    match = PATIENT_NAME_PATTERN.search(text)
    if match:
        return match.group(1).strip()

    match = PATIENT_NAME_FALLBACK_PATTERN.search(text)
    if match:
        name = match.group(1).strip()
        if not name.startswith("Cedars") and "Los Angeles" not in name:
            return name

    match = GUARANTOR_NAME_PATTERN.search(text)
    if match:
        return match.group(1).strip()
    return None


def _extract_contact_info(text: str) -> dict[str, str | None]:
    contact: dict[str, str | None] = {
        "department": None,
        "phone": None,
        "hours": None,
        "online": None,
        "email": None,
        "mail": None,
    }

    if re.search(r"Patient Financial Services|Patient Services", text, re.IGNORECASE):
        contact["department"] = "Patient Financial Services"

    match = PAY_ONLINE_PATTERN.search(text)
    if match:
        contact["online"] = match.group(1).strip()

    match = PAY_BY_PHONE_PATTERN.search(text)
    if match:
        contact["phone"] = match.group(1).strip()
    else:
        match = CALL_PHONE_PATTERN.search(text)
        if match:
            contact["phone"] = match.group(1).strip()

    match = PATIENT_SERVICES_EMAIL_PATTERN.search(text)
    if match:
        contact["email"] = match.group(1).strip()

    match = PATIENT_SERVICES_HOURS_PATTERN.search(text)
    if match:
        contact["hours"] = match.group(1).strip().rstrip(",")

    match = PATIENT_SERVICES_MAIL_PATTERN.search(text)
    if match:
        contact["mail"] = match.group(1).strip()
    elif "P.O. Box 48750, Los Angeles, CA 90048" in text:
        contact["mail"] = "P.O. Box 48750, Los Angeles, CA 90048"

    return contact


def _extract_guarantor_info(text: str) -> dict[str, str | None]:
    """Extract guarantor details from bill header text."""
    guarantor_name = None
    match = GUARANTOR_NAME_PATTERN.search(text)
    if match:
        guarantor_name = match.group(1).strip()

    guarantor_number = None
    match = GUARANTOR_NUMBER_PATTERN.search(text)
    if match:
        guarantor_number = match.group(1).strip()

    return {
        "guarantor_name": guarantor_name,
        "guarantor_account_number": guarantor_number,
    }


def _extract_bill_header_fields(text: str) -> dict[str, Any]:
    """Extract patient, insurance, and contact fields from bill header text."""
    service_date = None
    match = SERVICE_DATE_PATTERN.search(text)
    if match:
        service_date = _normalize_date(match.group(1))

    account_number = None
    match = ACCOUNT_NUMBER_PATTERN.search(text)
    if match:
        account_number = match.group(1).strip()

    return {
        "patient": {
            "patient_name": _extract_patient_name(text),
            "patient_account_number": account_number,
            "service_date": service_date,
        },
        "guarantor": _extract_guarantor_info(text),
        "insurance": _extract_insurance_info(text),
        "contact_info": _extract_contact_info(text),
    }


def _line_item_total(line_items: list[dict[str, Any]]) -> float | None:
    amounts = [
        item.get("amount")
        for item in line_items
        if isinstance(item.get("amount"), (int, float))
    ]
    if not amounts:
        return None
    return round(sum(amounts), 2)


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
    billing_flags = _bill_flags(text, line_items)
    header_fields = _extract_bill_header_fields(text)

    return {
        "source_file": str(path),
        "filename": path.name,
        "page_count": page_count,
        **header_fields,
        "dates": _extract_dates(text),
        "billing_codes": billing_codes,
        "amounts": _extract_amounts(text),
        "line_items": line_items,
        "line_item_count": len(line_items),
        "line_item_amount_total": _line_item_total(line_items),
        "billing_flags": billing_flags,
        "suggested_next_steps": _suggested_next_steps(billing_flags),
        "parse_method": "tables" if table_items else "text",
    }


@tool(
    name="bill_parser",
    description=(
        "Parse an uploaded patient bill PDF and return structured JSON with "
        "patient name, service date, insurance, contact info, line items, "
        "billing codes (CPT, HCPCS, ICD-10), service dates, and dollar amounts. "
        "Pass the uploaded filename or full path."
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
