"""Automated grounding check for agent responses.

Regex-extracts dollar amounts, dates, and CPT/HCPCS/ICD-10 billing codes
from an agent's response text and verifies each one traces back to the
parsed bill JSON (what bill_parser actually extracted and handed the LLM)
or the conversation itself (patient_input/patient_followup — a patient's
own stated income or household size is legitimately grounded even though
it isn't in the bill). Catches most numeric hallucination without an LLM
judge — see Professor Vo's parser-vs-gold feedback, item 3.

A third grounding source, beyond the bill and the conversation: FPL
threshold dollar amounts (e.g. "$15,960"). When a patient gives income
and household size, the server (app.server._fpl_context_message) calls
the real calculate_fpl tool and hands the model its exact JSON result —
but that system-level injection is never echoed back into the
conversation history the eval harness records, so a correctly-grounded
FPL threshold would otherwise look "ungrounded" here. Rather than
hand-copy the constant (which would silently drift the moment Cedars
updates the FPL table), this imports FPL_BASE_USD / FPL_ADDITIONAL_
PERSON_USD directly from app.tools.calculate_fpl — the same values the
production tool actually computes with — and derives every household
size's 100%-FPL threshold from them. See FPL_REFERENCE_THRESHOLDS below.

Scope, matching Vo's literal spec: dollar amounts, dates, and billing
codes only. Not every kind of hallucination is numeric in this shape —
e.g. a fabricated policy tier like "401%-600% FPL" is a percentage/policy
claim, not a dollar amount, date, or code, and this check will not catch
it. That's a real gap, not an oversight; extending to percentages/policy
claims would be a different, broader check.

Known amounts also recognize bare numbers (no "$") immediately next to
an explicit currency keyword ("paid", "balance", "charged", "billed",
"due", "total", "owed", "cost") — see BARE_AMOUNT_PATTERN. This matters
for the ~30% of the dataset where input_format is "text": the patient
types the bill inline ("Ins paid 2100. Balance 1850.") rather than
uploading a document, and without this, every one of those cases would
have its correct amounts flagged as "ungrounded" simply because the
source text never wrote a "$". The keyword anchor is deliberately
narrow — it only fires directly next to one of those words — so it
doesn't start treating account numbers, CPT codes, or phone numbers as
dollar amounts; a negative lookahead also excludes anything immediately
followed by another digit or "/", so "Due 07/01/26" doesn't get read as
"$07".

This validates against already-recorded responses (e.g. the midterm
scoring CSV) or fresh bill_parser output, not live agent calls. Wiring
this to run automatically "on every PR" would need a CI pipeline this
repo doesn't have yet, plus a live-agent-calling step with its own API
costs — that's a separate infrastructure decision, not a code change.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from typing import Any

_AGENT_HARNESS_SRC = Path(__file__).resolve().parents[1] / "agent-harness" / "src"
if str(_AGENT_HARNESS_SRC) not in sys.path:
    sys.path.insert(0, str(_AGENT_HARNESS_SRC))


def _load_fpl_constants() -> tuple[int, int]:
    """Load FPL_BASE_USD / FPL_ADDITIONAL_PERSON_USD straight from the
    production module's file, bypassing `app.tools`' package __init__
    (which imports bill_parser, and with it cv2/pdfplumber/pytesseract —
    heavy OCR dependencies this evaluation environment has no reason to
    need just to read two integer constants)."""
    module_path = _AGENT_HARNESS_SRC / "app" / "tools" / "calculate_fpl.py"
    spec = importlib.util.spec_from_file_location("_cedars_calculate_fpl", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.FPL_BASE_USD, module.FPL_ADDITIONAL_PERSON_USD


FPL_BASE_USD, FPL_ADDITIONAL_PERSON_USD = _load_fpl_constants()

# 100%-FPL dollar threshold for every household size from 1 up to this
# cap. No real synthetic case exceeds single digits, but the arithmetic
# is free, so this errs generous rather than risk excluding a legitimate
# larger-household threshold the agent correctly cites.
_MAX_HOUSEHOLD_SIZE_CONSIDERED = 20
FPL_REFERENCE_THRESHOLDS: set[float] = {
    float(FPL_BASE_USD + (household_size - 1) * FPL_ADDITIONAL_PERSON_USD)
    for household_size in range(1, _MAX_HOUSEHOLD_SIZE_CONSIDERED + 1)
}

AMOUNT_PATTERN = re.compile(r"\$\s*([\d,]+(?:\.\d{2})?)")
_CURRENCY_CONTEXT_KEYWORDS = r"(?:paid|balance|charge[sd]?|bill(?:ed)?|due|total|ow(?:e|es|ed)|cost)"
BARE_AMOUNT_PATTERN = re.compile(
    rf"\b{_CURRENCY_CONTEXT_KEYWORDS}\b[:\s]*\$?\s*([\d,]+(?:\.\d{{2}})?)(?![\d/])",
    re.IGNORECASE,
)
DATE_PATTERNS = [
    re.compile(r"\b(\d{1,2}/\d{1,2}/\d{2,4})\b"),
    re.compile(r"\b(\d{4}-\d{2}-\d{2})\b"),
]
CODE_PATTERN = re.compile(r"\bCPT\s*(\d{5})\b|\bHCPCS\s*([A-Z]\d{4})\b", re.IGNORECASE)


def _normalize_amount(raw: str) -> float | None:
    cleaned = raw.replace("$", "").replace(",", "").strip()
    if not cleaned:
        return None
    try:
        return round(float(cleaned), 2)
    except ValueError:
        return None


def extract_claimed_values(response_text: str) -> dict[str, list[str]]:
    """Pull dollar amounts, dates, and billing codes out of response text."""
    amounts = AMOUNT_PATTERN.findall(response_text)
    dates: list[str] = []
    for pattern in DATE_PATTERNS:
        dates.extend(pattern.findall(response_text))
    codes = [
        group
        for match in CODE_PATTERN.findall(response_text)
        for group in match
        if group
    ]
    return {"amounts": amounts, "dates": dates, "codes": codes}


def _walk_values(node: Any, amounts: set[float], dates: set[str], codes: set[str]) -> None:
    if isinstance(node, dict):
        for value in node.values():
            _walk_values(value, amounts, dates, codes)
    elif isinstance(node, list):
        for item in node:
            _walk_values(item, amounts, dates, codes)
    elif isinstance(node, (int, float)):
        amounts.add(round(float(node), 2))
    elif isinstance(node, str):
        for pattern in DATE_PATTERNS:
            dates.update(pattern.findall(node))
        for raw in AMOUNT_PATTERN.findall(node):
            value = _normalize_amount(raw)
            if value is not None:
                amounts.add(value)
        for raw in BARE_AMOUNT_PATTERN.findall(node):
            value = _normalize_amount(raw)
            if value is not None:
                amounts.add(value)
        for match in CODE_PATTERN.findall(node):
            codes.update(group for group in match if group)
        # Bare 5-digit CPT codes without an explicit "CPT" label often
        # appear directly in parsed billing_codes entries.
        codes.update(re.findall(r"\b\d{5}\b", node))


def collect_known_values(
    bill_json: dict[str, Any], conversation_text: str = ""
) -> dict[str, set]:
    """Flatten every dollar amount, date, and billing code appearing
    anywhere in a parsed bill JSON — plus, optionally, the patient's own
    conversation turns, which are a legitimate grounding source even
    though they aren't part of the bill (e.g. a stated household income) —
    plus the fixed set of per-household-size FPL dollar thresholds, which
    are always legitimately citable regardless of this patient's own
    household size (see module docstring)."""
    amounts: set[float] = set(FPL_REFERENCE_THRESHOLDS)
    dates: set[str] = set()
    codes: set[str] = set()
    _walk_values(bill_json, amounts, dates, codes)
    if conversation_text:
        _walk_values(conversation_text, amounts, dates, codes)
    return {"amounts": amounts, "dates": dates, "codes": codes}


def check_grounding(
    response_text: str,
    bill_json: dict[str, Any],
    conversation_text: str = "",
    amount_tolerance: float = 0.01,
) -> dict[str, Any]:
    """Return which dollar amounts/codes in a response don't trace back to
    the parsed bill or conversation. Dates are reported but not treated as
    grounding failures on their own (see docstring below) — an all-empty
    ungrounded_* list means everything numeric checks out.

    Dates are excluded from the pass/fail signal deliberately: a response
    routinely restates the current date, a due date computed from bill
    data, or a relative reference ("within 30 days") that renders as a
    date-shaped string without being a claim traceable to a single source
    value. Flagging every date mismatch produced far more noise than
    signal in testing; amounts and codes are the reliable half of this
    check.
    """
    claimed = extract_claimed_values(response_text)
    known = collect_known_values(bill_json, conversation_text)

    ungrounded_amounts = []
    for raw in claimed["amounts"]:
        value = _normalize_amount(raw)
        if value is None:
            continue
        if not any(abs(value - k) <= amount_tolerance for k in known["amounts"]):
            ungrounded_amounts.append(raw)

    ungrounded_codes = [c for c in claimed["codes"] if c not in known["codes"]]

    return {
        "claimed": claimed,
        "ungrounded_amounts": ungrounded_amounts,
        "ungrounded_codes": ungrounded_codes,
        "grounded": not ungrounded_amounts and not ungrounded_codes,
    }
