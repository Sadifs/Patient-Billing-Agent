"""Parse uploaded patient bill PDFs and photos into structured JSON.

Extracts line items, billing codes (CPT, HCPCS, ICD-10), service dates,
and dollar amounts. PDFs use pdfplumber for text and table extraction;
photos (.jpg/.jpeg/.png/.heic/.heif) go through OCR (Tesseract) and feed
into the same downstream text-parsing pipeline.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pdfplumber
import pytesseract
from PIL import Image, UnidentifiedImageError

from agent_harness import tool

logger = logging.getLogger(__name__)

# ── OCR / image-parsing config ─────────────────────────────────────────
# Provisional defaults, picked by judgment rather than statistical
# calibration against a large photo corpus. Adjust here as real-world
# usage surfaces whether they're too strict or too loose — this is the
# one place both values live, so tightening later is a one-line change.

# Tesseract page segmentation mode. 6 = "assume a single uniform block of
# text", which fits a bill's dense paragraph-and-table layout better than
# the default (3, general-purpose page layout analysis).
OCR_PSM_MODE = 6

# Mean word-confidence (0-100, from pytesseract.image_to_data) below which
# we treat the photo as unreadable rather than risk parsing garbage.
OCR_MIN_CONFIDENCE = 45

# A second, softer threshold (0-1 scale, unlike OCR_MIN_CONFIDENCE above)
# for _provenance warnings. A photo can clear OCR_MIN_CONFIDENCE (get
# parsed at all) while still being mediocre enough that its numbers
# deserve a "double check this" flag rather than being stated as fact.
OCR_SOFT_CONFIDENCE_THRESHOLD = 0.70

# Minimum recognized word count. Confidence alone isn't enough — a heavily
# degraded image can yield a handful of garbage single-character "words"
# that Tesseract is individually confident about, pulling the mean
# confidence above threshold despite there being almost no real content.
# A real bill page reliably produces well over 100 words; this catches
# "barely anything was found" separately from "what was found looks iffy."
OCR_MIN_WORD_COUNT = 30

# Target size (pixels, smaller dimension) for the upscale-if-small step.
# Tesseract accuracy degrades sharply on low-resolution input — measured a
# jump from 61 to 82 mean confidence (and several digit misreads corrected
# outright, e.g. a line item read as $872,624 instead of the real $72,624)
# upscaling a 450x600 test photo before OCR. Images already at or above
# this size are left untouched, both to avoid wasted work and because
# upscaling an already-detailed image doesn't add real information.
#
# Raised from 1500 to 3000 (Professor Vo's parser-vs-gold feedback,
# item 4/5 investigation): a 150 DPI page render (1275px smaller
# dimension — a realistic resolution for a full-page phone photo) only
# reached 1500px under the old target, a mere 1.18x upscale. Line-item
# text on that image OCR'd as garbage; the same source upscaled to a
# 3000px target (2.35x) OCR'd every line item's amounts and billing
# codes correctly. Confirmed live on a real bill, not assumed.
OCR_UPSCALE_TARGET_MIN_DIMENSION = 3000
OCR_UPSCALE_MAX_FACTOR = 4

# How far the summed line-item total is allowed to drift from the bill's
# stated total before we flag the read as inconsistent, as a fraction of
# the stated total (e.g. 0.02 = 2%). Real bills have legitimate rounding;
# this is not meant to catch cent-level drift, only "this reading is
# probably wrong."
MATH_CONSISTENCY_TOLERANCE = 0.02

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
HEIC_EXTENSIONS = {".heic", ".heif"}


class LowConfidenceOCRError(Exception):
    """Raised when OCR confidence on a photo is too low to trust."""


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
    # "Pat\w*nt" tolerates common OCR misreads of "Patient" (e.g.
    # "Pationt"), "[:;]" tolerates colon/semicolon confusion, and the
    # optional "Name" plus broader lookahead set covers bill templates
    # that label this field "Patient Name:" rather than just "Patient:".
    r"Pat\w*nt(?:\s+Name)?\s*[:;]\s*(.+?)\s+"
    r"(?:DOB|Address|Account\s*#?|Service\s*Date|(?:Primary|Secondary)\s*\w*surance)[:;]?",
    re.IGNORECASE,
)
PATIENT_NAME_FALLBACK_PATTERN = re.compile(
    r"^(.+?)\s+A l Pay Online:",
    re.MULTILINE,
)
GUARANTOR_NAME_PATTERN = re.compile(
    r"Guar\w*[ \t]+Nam\w*\s*[:;]\s*([^\n]+)", re.IGNORECASE
)
GUARANTOR_NUMBER_PATTERN = re.compile(
    r"Guar\w*[ \t]*(?:#|Numb\w*)\s*[:;]\s*(\S+)",
    re.IGNORECASE,
)
ACCOUNT_NUMBER_PATTERN = re.compile(
    r"Acc\w*[ \t]*(?:#|Numb\w*)?\s*[:;]\s*(\S+)", re.IGNORECASE
)
SERVICE_DATE_PATTERN = re.compile(
    # "Serv\w*" tolerates OCR misreads like "Serve Date" (dropped "ic").
    # The gap before "Date" is deliberately [ \t]* (not \s*) so it can't
    # span a newline — \s* previously let this match all the way from an
    # unrelated "Services" earlier in the text to a "Date:" line further
    # down, e.g. "...Physician Services\nDate: 2026-04-01" (the statement
    # date, not the service date). Capturing a non-greedy value covers
    # spelled-out dates like "November 25, 2013" that have spaces, not
    # just MM/DD/YYYY. Stop before a trailing same-line label like
    # "Service Type:" (commercial outpatient bills put both on one line)
    # — same idea as PATIENT_NAME_PATTERN stopping at DOB/Address — or
    # at end-of-line via MULTILINE $.
    r"Serv\w*[ \t]*Date\s*[:;]\s*(.+?)"
    r"(?=\s+(?:Serv\w*[ \t]*Type|Account\s*#?|Status|Policy|"
    r"(?:Primary|Secondary)\s*\w*surance)\b|\s*$)",
    re.IGNORECASE | re.MULTILINE,
)
PAY_ONLINE_PATTERN = re.compile(r"Pay\w*[ \t]+On\w*\s*[:;]\s*(\S+)", re.IGNORECASE)
PAY_BY_PHONE_PATTERN = re.compile(
    r"Pay\w*[ \t]+by[ \t]+Phon\w*\s*[:;]\s*([\d-]+)", re.IGNORECASE
)
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
    r"(?:\bP[\.\)\s]+O[\.\)\s]*\.?\s*Box|\bP\.O\.?\s*Box|Box\s+48750|Los Angeles, CA 90048|\)\s*48750)",
    re.IGNORECASE,
)
TOTAL_DUE_PATTERN = re.compile(
    # This feeds the math-consistency safety net directly — if this label
    # fails to match on a noisy OCR read, the check silently doesn't run
    # at all rather than failing loudly, so it gets the same OCR-typo and
    # colon/semicolon tolerance as the header-field patterns above.
    r"\b(?:Tot\w*(?:[ \t]+Amo\w*)?[ \t]+Du\w*|Bal\w*[ \t]+Du\w*|Pat\w*[ \t]+(?:Bal\w*|Respon\w*))"
    r"\s*[:;]?\s*\$?\s*([\d,]+\.\d{2})",
    re.IGNORECASE,
)
STATEMENT_DATE_PATTERN = re.compile(
    r"\bStatement[ \t]+Date\s*[:;]\s*([^\n\r|]+)",
    re.IGNORECASE,
)
DUE_DATE_PATTERN = re.compile(
    r"\bDue[ \t]+Date\s*[:;]\s*([^\n\r|]+)",
    re.IGNORECASE,
)
FACILITY_NAME_PATTERN = re.compile(
    r"^\s*(Cedars-Sinai Medical Center)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
TOTALS_LINE_PATTERN = re.compile(r"^\s*Totals\s+(.+)$", re.IGNORECASE | re.MULTILINE)

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent

DEFAULT_KNOWLEDGE_DIRS = [
    Path(os.environ.get("UPLOAD_DIR", "/tmp/uploads")).expanduser(),
    Path("/app/uploads"),
    _REPO_ROOT / "knowledge-docs",
    Path("/app/knowledge-docs"),
]


def _resolve_bill_path(file_path: str) -> Path:
    """Resolve a bill file path from an absolute path, relative path, or filename."""
    candidate = Path(file_path).expanduser()
    if candidate.is_file():
        return candidate

    for base in DEFAULT_KNOWLEDGE_DIRS:
        resolved = base / file_path
        if resolved.is_file():
            return resolved

    raise FileNotFoundError(f"Bill file not found: {file_path}")


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
    negative = cleaned.startswith("(") and cleaned.endswith(")")
    if negative:
        # Strip the parens themselves, not just surrounding whitespace —
        # float("( 9120.00 )") raises ValueError, which previously caused
        # every parenthesized (credit/payment) amount to silently parse as
        # None instead of a negative number. That dropped credit line
        # items from sums entirely rather than subtracting them, which is
        # why a bill with a payment-plan credit line summed to more than
        # its stated total (e.g. $77,520 summed vs $68,400 stated, off by
        # exactly the $9,120 credit that got discarded).
        cleaned = cleaned[1:-1].strip()
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
        # A former third check here — "2+ single-letter-period
        # abbreviations" (meant to catch "P.O." bleed) — was removed.
        # It also matched legitimate content like "L.A." in "Medi-Cal
        # (Managed Care – L.A. Care Health Plan)", silently deleting a
        # real payer detail. The two checks below already cover the
        # actual corruption signature specifically; the removed one
        # generalized to over-stripping on suspicion rather than positive
        # evidence — exactly the failure mode Professor Vo's feedback
        # (parser-vs-gold, item 1B) called out by name.
        if re.search(r"Box|48750|Los Angeles|P[\.\)]\s*O", inner, re.IGNORECASE):
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

    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -:\t|")
    cleaned = re.sub(
        r"\(parent employer-[^)]*\)",
        "(parent employer-sponsored)",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"(\(parent employer-sponsored\))\s*48750.*",
        r"\1",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.split(r"\s+Secondary Insurance:", cleaned, maxsplit=1)[0].strip()
    cleaned = re.split(
        r"\s+(?:Date|Service Date|Service Type|Due Date|Statement Date|"
        r"Policy\s*#|Policy Number|Status)\s*:",
        cleaned,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0].strip()
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


def _extract_insurance_by_line_clustering(path: Path) -> dict[str, str | None] | None:
    """Extract Primary/Secondary Insurance values from a PDF using precise
    word-position clustering, bypassing pdfplumber's flattened text.

    Some bills in this dataset render the insurance parenthetical and an
    unrelated P.O. Box address line at nearly the same y-position — gaps as
    small as ~0.4pt, well under pdfplumber's default ~3pt line-merging
    tolerance. That causes extract_text() to treat them as one line and
    sort their characters by x-position, interleaving two unrelated strings
    character-by-character, e.g. "(Medicare AdvantageP).O. Box 48750, Los
    Angeles, CA 90048" instead of "(Medicare Advantage)".

    A blanket tighter y_tolerance can't fix this globally: legitimate
    same-line label/value pairs elsewhere in this same bill template (e.g.
    "Total Amount Due:" and its dollar amount) have a LARGER y-gap (~1.6pt)
    than this corruption's gap (~0.4pt) — so no single tolerance value
    keeps genuine pairs together while splitting the corrupted ones apart.

    Instead, this targets the one field known to be affected: a label like
    "Primary Insurance:" is drawn as a single continuous text run with
    ~0 internal y-jitter, so grouping ALL characters on the page by their
    exact y-position and taking only the group the label itself belongs to
    cleanly reconstructs just that one logical line — any unrelated text
    an accidental overlap glued in sits at a measurably different y and is
    naturally excluded, no heuristic guessing required.

    Returns None (signaling "fall back to regex-over-text") if the labels
    can't be found this way — e.g. for any bill whose layout differs enough
    that this approach doesn't apply.
    """
    try:
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                lines_by_top: dict[float, list[dict[str, Any]]] = {}
                for char in page.chars:
                    lines_by_top.setdefault(round(char["top"], 1), []).append(char)

                lines = {}
                for top, chars in lines_by_top.items():
                    chars.sort(key=lambda c: c["x0"])
                    lines[top] = "".join(c["text"] for c in chars)

                primary = None
                secondary = None
                for line in lines.values():
                    if primary is None:
                        match = re.match(r"\s*Primary Insurance:\s*(.+)", line, re.IGNORECASE)
                        if match:
                            primary = match.group(1).strip()
                    if secondary is None:
                        match = re.match(r"\s*Secondary Insurance:\s*(.+)", line, re.IGNORECASE)
                        if match:
                            secondary = match.group(1).strip()

                if primary is not None or secondary is not None:
                    return {
                        "primary": _clean_insurance_value(primary),
                        "secondary": _clean_insurance_value(secondary),
                    }
    except Exception:
        logger.exception("Word-position insurance extraction failed; falling back to text regex")
    return None


def _extract_insurance_info(text: str) -> dict[str, str | None]:
    """Extract primary and secondary insurance labels from bill text."""
    secondary_match = re.search(r"Secondary Insurance:\s*([^\n\r]+)", text, re.IGNORECASE)
    primary_match = re.search(r"Primary Insurance:\s*([^\n\r]+)", text, re.IGNORECASE)
    if not primary_match:
        # Some layouts use a bare "Insurance:" label (not "Primary Insurance:").
        # Negative lookbehind avoids matching "Secondary Insurance:".
        primary_match = re.search(
            r"(?<!Secondary )Insurance:\s*([^\n\r]+)",
            text,
            re.IGNORECASE,
        )

    primary_raw = primary_match.group(1) if primary_match else None
    if primary_match and primary_raw is not None:
        # pdfplumber can wrap payer names across lines, e.g.
        # "Insurance: Anthem Date: ... Service Type:\nBlue Cross PPO Policy #: ..."
        remainder = text[primary_match.end() :]
        next_line = re.match(r"\r?\n([^\n\r]+)", remainder)
        if next_line and re.search(
            r"\b(?:Date|Service Date|Service Type)\s*:",
            primary_raw,
            re.IGNORECASE,
        ):
            continuation = re.split(
                r"\s+(?:Policy\s*#:|Policy\s*Number:|Status:|Itemized|Rev Code|"
                r"Account Summary)",
                next_line.group(1),
                maxsplit=1,
                flags=re.IGNORECASE,
            )[0].strip()
            head = re.split(
                r"\s+(?:Date|Service Date|Service Type|Due Date|Statement Date)\s*:",
                primary_raw,
                maxsplit=1,
                flags=re.IGNORECASE,
            )[0].strip()
            if continuation:
                primary_raw = f"{head} {continuation}".strip()

    return {
        "primary": _clean_insurance_value(primary_raw),
        "secondary": _clean_insurance_value(
            secondary_match.group(1) if secondary_match else None
        ),
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


def _extract_bill_totals(text: str) -> dict[str, float | None]:
    """Extract bill-level total fields from summary/totals lines.

    The line-item ``amount`` field usually represents the provider's billed
    charge. For insured bills, that is not the same thing as the patient's
    balance. These explicit total fields give downstream prompts a safer
    source for "what do I owe?" questions.
    """
    totals: dict[str, float | None] = {
        "total_billed": None,
        "total_insurance_payments": None,
        "total_adjustments": None,
        "outstanding_balance": None,
        "patient_balance": None,
        "total_amount_due": None,
    }

    due_match = TOTAL_DUE_PATTERN.search(text)
    if due_match:
        totals["total_amount_due"] = _parse_amount(due_match.group(1))

    totals_lines = [match.group(1).strip() for match in TOTALS_LINE_PATTERN.finditer(text)]
    four_amount_line: list[float] | None = None
    three_amount_line: list[float] | None = None
    for line in totals_lines:
        # Self-pay/no-insurance bills render the "Ins Pmts" column as an
        # em dash ("—") instead of "$0.00" — a real dollar amount is never
        # a literal dash, so this substitution is unambiguous. Without it,
        # a 4-column totals line (billed/ins pmts/adj/patient bal) with a
        # dashed-out insurance column only yields 3 *numeric* amounts,
        # which previously got misread as (billed, outstanding_balance,
        # patient_balance) instead of (billed, adjustments, patient_balance)
        # — silently losing total_insurance_payments and total_adjustments
        # for every self-pay bill.
        line = line.replace("—", "$0.00")
        amounts = _amounts_from_cell(line)
        if len(amounts) >= 4:
            four_amount_line = amounts[:4]
        elif len(amounts) == 3 and three_amount_line is None:
            three_amount_line = amounts

    if four_amount_line:
        (
            totals["total_billed"],
            totals["total_insurance_payments"],
            totals["total_adjustments"],
            totals["patient_balance"],
        ) = four_amount_line
        # Default outstanding_balance = patient_balance since a 4-column
        # line has no separate slot for it — true for every bill in this
        # corpus except one (deliberately built so the two differ, to
        # test discrepancy detection). Prefer a three_amount_line's real,
        # distinct outstanding_balance when one was also found, rather
        # than unconditionally overwriting it with this assumption.
        totals["outstanding_balance"] = totals["patient_balance"]
    if three_amount_line:
        billed, outstanding_balance, patient_balance = three_amount_line
        totals["total_billed"] = totals["total_billed"] or billed
        totals["outstanding_balance"] = outstanding_balance
        totals["patient_balance"] = totals["patient_balance"] or patient_balance

    if totals["total_amount_due"] is None and totals["patient_balance"] is not None:
        totals["total_amount_due"] = totals["patient_balance"]

    return totals


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


def _extract_pdf_content(path: Path) -> tuple[str, list[list[list[Any]]], int, float]:
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

    # PDF text extraction is deterministic — no OCR confidence score
    # applies, so this is a fixed 1.0 rather than a measured value. See
    # _extract_image_content for the OCR path, which returns a real
    # per-photo confidence instead.
    return "\n\n".join(text_parts), tables, page_count, 1.0


def _load_image(path: Path) -> Image.Image:
    """Load a photo into a PIL Image, converting HEIC/HEIF first if needed."""
    if path.suffix.lower() in HEIC_EXTENSIONS:
        import pillow_heif

        heif_file = pillow_heif.open_heif(path, convert_hdr_to_8bit=True)
        return Image.frombytes(
            heif_file.mode, heif_file.size, heif_file.data, "raw"
        )
    return Image.open(path)


def _deskew(gray: np.ndarray) -> np.ndarray:
    """Rotate a grayscale image to correct for camera-angle skew.

    Uses the minimum-area bounding rectangle of the non-background pixels,
    which needs real gradient/edge information to work — this is why
    deskew must run on the grayscale image, before thresholding collapses
    it to pure black/white and destroys those edges.
    """
    inverted = cv2.bitwise_not(gray)
    coords = np.column_stack(np.where(inverted > 0))
    if coords.size == 0:
        return gray

    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle

    if abs(angle) < 0.5:
        return gray

    (h, w) = gray.shape[:2]
    center = (w // 2, h // 2)
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    return cv2.warpAffine(
        gray, matrix, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE
    )


def _upscale_if_small(gray: np.ndarray) -> tuple[np.ndarray, float]:
    """Upscale low-resolution photos before OCR gets a look at them.

    A photo that's been downsized (screenshot crop, compressed export,
    etc.) gives Tesseract too few pixels per character to read reliably.
    Upscaling doesn't add real detail, but cubic interpolation smooths
    character edges enough to measurably help — see the constant's
    docstring for the concrete before/after numbers this was based on.

    Returns the (possibly resized) image and the factor applied, so the
    caller can scale other size-dependent parameters (e.g. the adaptive
    threshold's block size) to match — using a fixed block size on an
    upscaled image was tried first and made already-decent-resolution
    photos measurably worse, since the same pixel window now covers a
    much smaller fraction of each (now-larger) character.
    """
    h, w = gray.shape[:2]
    smaller_dim = min(h, w)
    if smaller_dim >= OCR_UPSCALE_TARGET_MIN_DIMENSION:
        return gray, 1.0

    factor = min(OCR_UPSCALE_TARGET_MIN_DIMENSION / smaller_dim, OCR_UPSCALE_MAX_FACTOR)
    upscaled = cv2.resize(gray, None, fx=factor, fy=factor, interpolation=cv2.INTER_CUBIC)
    return upscaled, factor


def _preprocess_for_ocr(image: Image.Image) -> np.ndarray:
    """Grayscale -> upscale (if small) -> deskew -> adaptive threshold.

    Order matters: deskew needs the gradient information a grayscale image
    still has; running threshold first would collapse the image to flat
    black/white and remove the edges deskew detects rotation from.
    Upscaling happens before deskew so the rotation-angle detection also
    benefits from the extra resolution.
    """
    rgb = np.array(image.convert("RGB"))
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    gray, upscale_factor = _upscale_if_small(gray)
    deskewed = _deskew(gray)

    block_size = max(3, int(31 * upscale_factor))
    if block_size % 2 == 0:
        block_size += 1

    thresholded = cv2.adaptiveThreshold(
        deskewed,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        blockSize=block_size,
        C=15,
    )
    return thresholded


# Single-word header tokens, checked per-word (not as substrings of the
# joined line) so one ambiguous word can't satisfy two groups at once —
# e.g. "Service" alone would otherwise match both "description" (via
# "service") and "date" (via the phrase "service date") on a line like
# "Patient: ... Service Date: 2026-03-15", which is a label:value line,
# not a table header. Confirmed live: an earlier substring-based version
# of this matched exactly that false positive on a real bill photo.
_TABLE_HEADER_WORD_GROUPS: tuple[tuple[str, ...], ...] = (
    ("date", "dos"),
    ("description", "service", "procedure", "item"),
    ("code", "cpt", "hcpcs"),
    ("billed", "charge", "amount", "qty", "quantity"),
    ("pmts", "payments", "paid"),
    ("adjustment", "adjustments", "adj"),
    ("bal", "balance", "responsibility", "resp"),
)
_MIN_HEADER_WORDS_MATCHED = 3


def _tesseract_words_with_boxes(data: dict[str, list]) -> list[dict[str, Any]]:
    """Flatten pytesseract.image_to_data's parallel-array output into one
    dict per confident word, keeping its bounding box and line grouping."""
    words: list[dict[str, Any]] = []
    for i, text in enumerate(data["text"]):
        if not text.strip():
            continue
        conf = data["conf"][i]
        if conf in ("-1", -1):
            continue
        words.append(
            {
                "text": text,
                "left": data["left"][i],
                "top": data["top"][i],
                "width": data["width"][i],
                "height": data["height"][i],
                "line_key": (data["block_num"][i], data["par_num"][i], data["line_num"][i]),
            }
        )
    return words


def _cluster_words_into_table(data: dict[str, list]) -> list[list[list[str]]] | None:
    """Reconstruct a real table (rows x columns) from Tesseract's
    word-level bounding boxes, per Professor Vo's parser-vs-gold
    feedback item 4: "Cluster word boxes by y-overlap into rows and by
    x-position into columns, then return real tables instead of []."

    Deliberately conservative: only returns a table when a line is found
    where at least _MIN_HEADER_WORDS_MATCHED distinct words each match a
    distinct header-keyword group from the same vocabulary
    _parse_line_items_from_tables already checks for (date/description/
    code/billed/etc.) — i.e. the same confidence bar the PDF table path
    implicitly relies on via pdfplumber's own table detection. If no such
    line is found, returns None so the caller falls back to the existing,
    already-working text-based line-item parser unchanged. This bar
    exists specifically so a photo of a non-tabular page (or one where
    OCR garbled the header beyond recognition) can't produce a
    confidently-wrong table that's worse than the text fallback.

    Column boundaries are anchored to the header row's own word
    positions (each header word's x-center defines one column); every
    word in every row below the header is assigned to its nearest
    column anchor. This mirrors the actual visual column structure of
    the bill rather than guessing a fixed layout.
    """
    words = _tesseract_words_with_boxes(data)
    if not words:
        return None

    lines: dict[tuple[int, int, int], list[dict[str, Any]]] = {}
    for word in words:
        lines.setdefault(word["line_key"], []).append(word)

    ordered_line_keys = sorted(lines, key=lambda key: min(w["top"] for w in lines[key]))

    header_key: tuple[int, int, int] | None = None
    header_words: list[dict[str, Any]] | None = None
    for key in ordered_line_keys:
        line_words = sorted(lines[key], key=lambda w: w["left"])
        # Label:value lines ("Service Date:", "Account #:") are never
        # table headers — exclude them outright rather than risk an
        # ambiguous word inside one being miscounted as a header match.
        if any(w["text"].rstrip().endswith(":") for w in line_words):
            continue

        matched_group_indices: set[int] = set()
        for word in line_words:
            token = re.sub(r"[^a-z0-9]", "", word["text"].lower())
            if not token:
                continue
            for group_index, group in enumerate(_TABLE_HEADER_WORD_GROUPS):
                if group_index in matched_group_indices:
                    continue
                if token in group:
                    matched_group_indices.add(group_index)
                    break

        if len(matched_group_indices) >= _MIN_HEADER_WORDS_MATCHED:
            header_key = key
            header_words = line_words
            break

    if header_key is None or header_words is None:
        return None

    column_anchors = [word["left"] + word["width"] / 2 for word in header_words]
    header_row = [word["text"] for word in header_words]
    header_top = min(word["top"] for word in header_words)

    data_line_keys = [
        key for key in ordered_line_keys if min(w["top"] for w in lines[key]) > header_top
    ]

    table_rows: list[list[str]] = [header_row]
    for key in data_line_keys:
        line_words = sorted(lines[key], key=lambda w: w["left"])
        cell_words: list[list[str]] = [[] for _ in column_anchors]
        for word in line_words:
            word_center = word["left"] + word["width"] / 2
            nearest_idx = min(
                range(len(column_anchors)),
                key=lambda i: abs(column_anchors[i] - word_center),
            )
            cell_words[nearest_idx].append(word["text"])
        table_rows.append([" ".join(cell) if cell else "" for cell in cell_words])

    return [table_rows]


def _extract_image_content(path: Path) -> tuple[str, list[list[list[Any]]], int, float]:
    """OCR a bill photo into the same (text, tables, page_count, confidence)
    shape _extract_pdf_content returns, so it feeds the same downstream
    pipeline. Unlike the PDF path's fixed 1.0, confidence here is the real
    measured OCR confidence (0.0-1.0) for this specific photo — used to
    populate _provenance on every field extracted from it.

    Tables is always empty — Tesseract gives us text, not table structure —
    which means callers fall back to the existing text-based line-item
    parser, the same fallback PDFs already use when their table extraction
    comes up empty.
    """
    image = _load_image(path)
    processed = _preprocess_for_ocr(image)

    data = pytesseract.image_to_data(
        processed,
        config=f"--psm {OCR_PSM_MODE}",
        output_type=pytesseract.Output.DICT,
    )
    confidences = [float(c) for c in data["conf"] if c not in ("-1", -1)]
    mean_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    word_count = len([w for w in data["text"] if w.strip()])

    if mean_confidence < OCR_MIN_CONFIDENCE or word_count < OCR_MIN_WORD_COUNT:
        raise LowConfidenceOCRError(
            f"OCR confidence too low to trust (confidence={mean_confidence:.0f}/100, "
            f"words found={word_count}). The photo may be blurry, poorly lit, at a "
            "steep angle, or not a bill at all."
        )

    # Reconstruct real line breaks from Tesseract's block/paragraph/line
    # numbers rather than joining every word with a single space — many of
    # the downstream regexes (patient name, guarantor, totals, etc.) rely
    # on line-based structure the same way pdfplumber's extract_text()
    # naturally preserves for PDFs. Flattening to one line loses that.
    lines: dict[tuple[int, int, int], list[str]] = {}
    for i, word in enumerate(data["text"]):
        if not word.strip():
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        lines.setdefault(key, []).append(word)

    text = "\n".join(" ".join(words) for words in lines.values())
    tables = _cluster_words_into_table(data)
    return text, (tables or []), 1, round(mean_confidence / 100, 4)


def _math_consistency_check(
    text: str, line_items: list[dict[str, Any]]
) -> dict[str, Any]:
    """Compare summed line items against the bill's stated patient balance.

    For insured bills, the line-item ``amount``/``billed_amount`` total is
    not what the patient owes. Prefer summed ``patient_balance`` when present,
    and also check whether each row reconciles as:
    billed - insurance payments - adjustments = patient balance.
    """
    def sum_field(field: str, fallback: str | None = None) -> float | None:
        values: list[float] = []
        for item in line_items:
            value = item.get(field)
            if value is None and fallback:
                value = item.get(fallback)
            if isinstance(value, (int, float)):
                values.append(float(value))
        if not values:
            return None
        return round(sum(values), 2)

    stated_match = TOTAL_DUE_PATTERN.search(text)
    stated_total = _parse_amount(stated_match.group(1)) if stated_match else None
    totals = _extract_bill_totals(text)

    summed_billed = sum_field("billed_amount", fallback="amount")
    summed_insurance_payments = sum_field("insurance_payments")
    summed_adjustments = sum_field("adjustments")
    summed_patient_balance = sum_field("patient_balance")
    summed_total = summed_patient_balance if summed_patient_balance is not None else _line_item_total(line_items)

    row_violations: list[dict[str, Any]] = []
    tolerance_base = stated_total or summed_total or 1
    row_tolerance = max(tolerance_base * MATH_CONSISTENCY_TOLERANCE, 0.01)
    for index, item in enumerate(line_items, start=1):
        billed = item.get("billed_amount")
        insurance = item.get("insurance_payments")
        adjustments = item.get("adjustments")
        patient_balance = item.get("patient_balance")
        if not all(isinstance(value, (int, float)) for value in [billed, insurance, adjustments, patient_balance]):
            continue
        expected_patient_balance = round(float(billed) - float(insurance) - float(adjustments), 2)
        difference = round(abs(expected_patient_balance - float(patient_balance)), 2)
        if difference > row_tolerance:
            row_violations.append(
                {
                    "line_item_number": index,
                    "description": item.get("description"),
                    "expected_patient_balance": expected_patient_balance,
                    "actual_patient_balance": patient_balance,
                    "difference": difference,
                }
            )

    if stated_total is None or summed_total is None:
        return {
            "checked": False,
            "consistent": None,
            "stated_total": stated_total,
            "summed_total": summed_total,
            "summed_billed": summed_billed,
            "summed_insurance_payments": summed_insurance_payments,
            "summed_adjustments": summed_adjustments,
            "summed_patient_balance": summed_patient_balance,
            "row_reconciliation_violations": row_violations,
            "reason": "Could not find both a stated total and summed line items to compare.",
        }

    tolerance = max(stated_total * MATH_CONSISTENCY_TOLERANCE, 0.01)
    stated_vs_summed_consistent = abs(stated_total - summed_total) <= tolerance

    total_reconciliation_consistent = None
    if (
        summed_billed is not None
        and summed_insurance_payments is not None
        and summed_adjustments is not None
        and summed_patient_balance is not None
    ):
        expected_patient_total = round(
            summed_billed - summed_insurance_payments - summed_adjustments, 2
        )
        total_reconciliation_consistent = (
            abs(expected_patient_total - summed_patient_balance) <= tolerance
        )

    header_total_consistent = None
    header_patient_balance = totals.get("patient_balance")
    if isinstance(header_patient_balance, (int, float)):
        header_total_consistent = abs(stated_total - header_patient_balance) <= tolerance

    consistency_checks = [stated_vs_summed_consistent]
    if total_reconciliation_consistent is not None:
        consistency_checks.append(total_reconciliation_consistent)
    if header_total_consistent is not None:
        consistency_checks.append(header_total_consistent)
    if row_violations:
        consistency_checks.append(False)

    consistent = all(consistency_checks)

    result = {
        "checked": True,
        "consistent": consistent,
        "stated_total": stated_total,
        "summed_total": summed_total,
        "difference": round(abs(stated_total - summed_total), 2),
        "summed_billed": summed_billed,
        "summed_insurance_payments": summed_insurance_payments,
        "summed_adjustments": summed_adjustments,
        "summed_patient_balance": summed_patient_balance,
        "row_reconciliation_violations": row_violations,
        "total_reconciliation_consistent": total_reconciliation_consistent,
        "header_total_consistent": header_total_consistent,
    }
    if not consistent:
        result["recommended_guidance_if_false"] = (
            "The extracted bill numbers do not fully reconcile. State the "
            "bill's stated total amount due if asked what the patient owes, "
            "avoid presenting the mismatched line-item math as final, and "
            "recommend the patient verify the full breakdown with Cedars-Sinai "
            "Patient Financial Services before paying."
        )
    return result


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


def _looks_like_id(value: str) -> bool:
    """Return whether a captured value plausibly looks like an ID/account
    number rather than a mismatched neighboring label.

    OCR on multi-column bill layouts can jumble a label from one column
    with a value from the next (e.g. reading "Account Number: Primary
    Insurance" when the actual number sits in a different column than
    Tesseract expects). Real account/guarantor numbers observed on both
    synthetic and real bills always contain at least one digit
    ("CS-2026-00441", "22237958", "272"); a pure-alphabetic word like
    "Primary" is a sign the match grabbed the wrong neighboring text.
    """
    return any(char.isdigit() for char in value)


def _extract_guarantor_info(text: str) -> dict[str, str | None]:
    """Extract guarantor details from bill header text."""
    guarantor_name = None
    match = GUARANTOR_NAME_PATTERN.search(text)
    if match:
        guarantor_name = match.group(1).strip()

    guarantor_number = None
    match = GUARANTOR_NUMBER_PATTERN.search(text)
    if match:
        candidate = match.group(1).strip()
        if _looks_like_id(candidate):
            guarantor_number = candidate

    return {
        "guarantor_name": guarantor_name,
        "guarantor_account_number": guarantor_number,
    }


def _extract_bill_header_fields(text: str, pdf_path: Path | None = None) -> dict[str, Any]:
    """Extract patient, insurance, contact, and bill-level total fields.

    pdf_path, when given, enables word-position-based insurance extraction
    (see _extract_insurance_by_line_clustering) instead of the regex-over-
    flattened-text fallback — pass it for real PDFs, not OCR'd photo text.
    """
    service_date = None
    match = SERVICE_DATE_PATTERN.search(text)
    if match:
        service_date = _normalize_date(match.group(1))

    statement_date = None
    match = STATEMENT_DATE_PATTERN.search(text)
    if match:
        statement_date = _normalize_date(match.group(1).strip())

    due_date = None
    match = DUE_DATE_PATTERN.search(text)
    if match:
        due_date = _normalize_date(match.group(1).strip())

    facility_name = None
    match = FACILITY_NAME_PATTERN.search(text)
    if match:
        facility_name = match.group(1).strip()

    account_number = None
    match = ACCOUNT_NUMBER_PATTERN.search(text)
    if match:
        candidate = match.group(1).strip()
        if _looks_like_id(candidate):
            account_number = candidate

    return {
        "patient": {
            "patient_name": _extract_patient_name(text),
            "patient_account_number": account_number,
            "service_date": service_date,
        },
        "guarantor": _extract_guarantor_info(text),
        "insurance": (
            (pdf_path and _extract_insurance_by_line_clustering(pdf_path))
            or _extract_insurance_info(text)
        ),
        "contact_info": _extract_contact_info(text),
        "statement_date": statement_date,
        "due_date": due_date,
        "facility_name": facility_name,
        **_extract_bill_totals(text),
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


# Bill-level total fields tracked in _provenance — not every field in the
# output, just the ones most likely to feed a derived number (FPL
# calculations, "how much do I owe" answers) and the ones
# _math_consistency_check already independently evaluates. Extending this
# to insurance/patient-name fields would need _extract_bill_header_fields
# to expose which extraction path won (regex vs. position clustering),
# which is a real but separate piece of plumbing, not built here.
PROVENANCE_TRACKED_FIELDS = [
    "total_billed",
    "total_insurance_payments",
    "total_adjustments",
    "outstanding_balance",
    "patient_balance",
    "total_amount_due",
]


def _build_provenance(
    header_fields: dict[str, Any],
    source_type: str,
    extraction_confidence: float,
    math_consistency: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Return a _provenance entry per bill-total field: how it was
    extracted, how confident that extraction is, and any reason to doubt
    it.

    Per Professor Vo's parser-vs-gold feedback (item 3): any field
    carrying a warning or below-threshold confidence should be stated
    with the uncertainty attached and never used as an input to a
    derived number. This block makes that reasoning inspectable per
    field instead of only at the whole-bill level (which
    math_consistency.recommended_guidance_if_false already covers).
    """
    method = "ocr" if source_type == "photo" else "text_regex"
    confidence = round(extraction_confidence, 4)
    reconciliation_failed = math_consistency.get("consistent") is False

    provenance: dict[str, dict[str, Any]] = {}
    for field_name in PROVENANCE_TRACKED_FIELDS:
        if header_fields.get(field_name) is None:
            continue
        warnings: list[str] = []
        if reconciliation_failed:
            warnings.append("fails_total_reconciliation")
        if source_type == "photo" and confidence < OCR_SOFT_CONFIDENCE_THRESHOLD:
            warnings.append("low_ocr_confidence")
        provenance[field_name] = {
            "method": method,
            "confidence": confidence,
            "warnings": warnings,
        }
    return provenance


def parse_bill_file(file_path: str) -> dict[str, Any]:
    """Parse a bill PDF or photo and return structured extraction results."""
    path = _resolve_bill_path(file_path)
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        text, tables, page_count, extraction_confidence = _extract_pdf_content(path)
    elif suffix in IMAGE_EXTENSIONS or suffix in HEIC_EXTENSIONS:
        text, tables, page_count, extraction_confidence = _extract_image_content(path)
    else:
        raise ValueError(
            f"Unsupported file type: {suffix}. Expected a PDF or a photo "
            "(.pdf, .jpg, .jpeg, .png, .heic, .heif)."
        )

    table_items = _parse_line_items_from_tables(tables)
    text_items = _parse_line_items_from_text(text)
    line_items = table_items if table_items else text_items

    billing_codes = _extract_billing_codes(text)
    for item in line_items:
        for code in item.get("billing_codes", []):
            if code not in {entry["code"] for entry in billing_codes}:
                billing_codes.append({"code": code, "type": "unknown"})
    billing_flags = _bill_flags(text, line_items)
    header_fields = _extract_bill_header_fields(text, pdf_path=path if suffix == ".pdf" else None)

    result = {
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
        "source_type": "pdf" if suffix == ".pdf" else "photo",
    }

    result["math_consistency"] = _math_consistency_check(text, line_items)
    result["_provenance"] = _build_provenance(
        result,
        result["source_type"],
        extraction_confidence,
        result["math_consistency"],
    )

    return result


# Backwards-compatible alias; existing callers/tests use this name.
parse_bill_pdf = parse_bill_file


@tool(
    name="bill_parser",
    description=(
        "Parse an uploaded patient bill — PDF or photo (.pdf, .jpg, .jpeg, "
        ".png, .heic, .heif) — and return structured JSON with patient "
        "name, service date, insurance, contact info, line items, billing "
        "codes (CPT, HCPCS, ICD-10), service dates, and dollar amounts. "
        "Pass the uploaded filename or full path."
    ),
    parameters={
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": (
                    "Filename or path of the uploaded bill file "
                    "(e.g. 'sample_bill.pdf' or 'bill_photo.jpg')"
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
        result = parse_bill_file(file_path)
        return json.dumps(result)
    except LowConfidenceOCRError as exc:
        return json.dumps(
            {
                "error": str(exc),
                "error_type": "low_confidence_ocr",
                "suggested_response": (
                    "I couldn't clearly read this photo. Could you retake it "
                    "with better lighting, holding the camera flat and "
                    "square to the page, or upload the bill as a PDF instead?"
                ),
            }
        )
    except UnidentifiedImageError:
        return json.dumps(
            {
                "error": "File could not be read as an image.",
                "error_type": "invalid_image",
                "suggested_response": (
                    "That file doesn't look like a valid photo — it may not "
                    "have uploaded correctly. Could you try uploading it "
                    "again, or as a PDF instead?"
                ),
            }
        )
    except FileNotFoundError as exc:
        return json.dumps({"error": str(exc)})
    except ValueError as exc:
        return json.dumps({"error": str(exc)})
    except Exception as exc:
        logger.exception("Failed to parse bill file")
        return json.dumps({"error": f"Failed to parse bill file: {exc}"})
