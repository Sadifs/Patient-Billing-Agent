"""Sanic web server — the main entrypoint for the healthcare bill agent.

Run locally:
    export PYTHONPATH=src
    python -m app.server

Or via Docker:
    docker compose up --build

Endpoints:
    GET  /            — Serves the chat UI (static/index.html)
    POST /chat        — Send a user message, receive streamed agent response (SSE)
    POST /upload      — Upload a bill image/PDF to the knowledge base
    GET  /health      — Health check for container orchestration
"""

import asyncio
import json
import logging
import os
import re
import sys
from pathlib import Path

from sanic import Sanic, response
from sanic.request import Request

# ── Path setup ──────────────────────────────────────────────────────────
_APP_DIR = Path(__file__).resolve().parent
_SRC_DIR = _APP_DIR.parent
sys.path.insert(0, str(_SRC_DIR))
sys.path.insert(0, str(_APP_DIR))

from agent_harness import AgentHarness, Message, OpenAICompatibleClient
from app.rag.indexer import KnowledgeBaseIndexer
from app.rag.search import LocalSearchService
from app.tools import TOOLS as REGISTERED_TOOLS
from app.tools.calculate_fpl import calculate_fpl
from app.tools.search_bills import create_search_bills_tool
from app.hooks import HOOKS as REGISTERED_HOOKS
from app.hooks.phi_redaction import PHIRedactionHook
from app.skills import build_system_prompt

logger = logging.getLogger(__name__)

# ── Configuration (from environment variables) ──────────────────────────
API_KEY = os.environ.get("API_KEY", "")
API_ENDPOINT = os.environ.get("API_ENDPOINT", "")
API_MODEL = os.environ.get("API_MODEL", "gpt-4o")
API_PROVIDER = os.environ.get("API_PROVIDER", "openai")
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8000"))

# ── Sanic app ───────────────────────────────────────────────────────────
app = Sanic("BillAgent")
app.static("/static", str(_APP_DIR / "static"))

# ── Knowledge base ──────────────────────────────────────────────────────
KNOWLEDGE_DIR = _APP_DIR.parent.parent / "knowledge-docs"
UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", "/tmp/uploads")).expanduser()
indexer = KnowledgeBaseIndexer(knowledge_dir=str(KNOWLEDGE_DIR))
search_service = LocalSearchService(indexer)
input_redactor = PHIRedactionHook()


def _extract_household_size(text: str) -> int | None:
    """Extract household size from a single text string."""
    patterns = [
        r"\b(?:household|family)\s*(?:size|of)?\s*(?:is|:)?\s*(\d{1,2})\b",
        r"\b(\d{1,2})\s+(?:people|persons?|members?)\b",
        r"\bi\s+have\s+(\d{1,2})\s+(?:people|persons?|members?)\b",
        r"\bjust\s+(?:me|myself)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            if "just" in pattern:
                return 1
            return int(match.group(1))
    return None


def _extract_income(text: str) -> float | None:
    """Extract annual income from a single text string. Handles k/K suffix."""
    match = re.search(
        r"\b(?:household\s*)?(?:income|make|earn|salary)\b[^$\d]{0,20}\$?\s*([\d,]+(?:\.\d{2})?)([kK])?",
        text,
        re.IGNORECASE,
    )
    if not match:
        return None
    value = float(match.group(1).replace(",", ""))
    if match.group(2):
        value *= 1000
    return value


def _extract_fpl_inputs(
    text: str, history: list[dict] | None = None
) -> dict[str, int | float] | None:
    """Extract household size and income from text, falling back to recent history."""
    household = _extract_household_size(text)
    income = _extract_income(text)

    if (household is None or income is None) and history:
        for msg in reversed(history):
            if msg.get("role") != "user":
                continue
            msg_text = msg.get("content", "")
            if household is None:
                household = _extract_household_size(msg_text)
            if income is None:
                income = _extract_income(msg_text)
            if household is not None and income is not None:
                break

    if household is None or income is None:
        return None

    return {
        "household_size": household,
        "annual_income_usd": income,
    }


def _should_use_fpl_from_message(text: str) -> bool:
    """Return whether this turn is actually asking for FPL/payment assistance."""
    normalized = text.lower()
    if _extract_household_size(text) is not None or _extract_income(text) is not None:
        return True
    return bool(
        re.search(
            r"\b("
            r"fpl|federal poverty|poverty level|financial assistance|charity care|"
            r"payment assistance|discount|discount payment|payment plan|hardship|"
            r"afford|affordable|qualify|eligib|help paying|paying my bill"
            r")\b",
            normalized,
        )
    )


def _fpl_context_message(user_message: str, history: list[dict] | None = None) -> Message | None:
    """Pre-calculate FPL context when the user supplies both required values."""
    if not _should_use_fpl_from_message(user_message):
        return None

    fpl_inputs = _extract_fpl_inputs(user_message, history)
    if not fpl_inputs:
        return None

    result = calculate_fpl.handler(fpl_inputs)
    return Message(
        role="system",
        content=(
            "The user provided household size and annual household income. "
            "Use this calculated FPL screening result in your answer instead "
            "of estimating manually. Do not guarantee eligibility. "
            f"FPL calculation result: {result}"
        ),
    )


def _format_usd(value: int | float) -> str:
    """Format a dollar value for patient-facing responses."""
    return f"${value:,.0f}"


def _is_fpl_definition_question(text: str) -> bool:
    """Return whether the user is asking what FPL means."""
    normalized = text.lower().strip()
    return bool(
        re.search(r"\bwhat(?:'s| is)\s+(?:an?\s+)?fpl\b", normalized)
        or re.search(r"\bwhat\s+does\s+fpl\s+(?:mean|stand for)\b", normalized)
        or re.search(r"\bdefine\s+fpl\b", normalized)
    )


def _direct_fpl_definition_answer(user_message: str) -> str | None:
    """Return a plain-language FPL definition without requiring income details."""
    if not _is_fpl_definition_question(user_message):
        return None

    return (
        "FPL stands for Federal Poverty Level. It is an income guideline used "
        "to estimate whether a household may qualify for certain assistance "
        "programs.\n\n"
        "For hospital financial assistance, your FPL percentage compares your "
        "annual household income to the federal guideline for your household "
        "size. A lower FPL percentage usually means a stronger chance of "
        "qualifying for help, but Cedars-Sinai makes the final decision.\n\n"
        "If you want, share your household size and approximate annual "
        "household income, and I can estimate your FPL percentage."
    )


def _is_charity_care_definition_question(text: str) -> bool:
    """Return whether the user is asking what Charity Care means."""
    normalized = text.lower().strip()
    return bool(
        re.search(r"\bwhat(?:'s| is)\s+(?:cedars[- ]sinai\s+)?charity care\b", normalized)
        or re.search(r"\bwhat\s+does\s+(?:cedars[- ]sinai\s+)?charity care\s+mean\b", normalized)
        or re.search(r"\bdefine\s+(?:cedars[- ]sinai\s+)?charity care\b", normalized)
    )


def _direct_charity_care_definition_answer(user_message: str) -> str | None:
    """Return a Cedars-specific Charity Care definition without recalculating FPL."""
    if not _is_charity_care_definition_question(user_message):
        return None

    return (
        "**Summary**\n"
        "Cedars-Sinai Charity Care is a financial-assistance option for "
        "patients who may need help paying eligible hospital bills.\n\n"
        "**What It Means**\n"
        "If a patient qualifies, Charity Care may reduce or cover part of the "
        "patient balance. Eligibility is reviewed by Cedars-Sinai and usually "
        "depends on information like household size, household income, and the "
        "bill or services involved.\n\n"
        "**Important Note**\n"
        "I can help estimate whether applying may be worth asking about, but "
        "I cannot approve Charity Care or guarantee that a bill will be "
        "forgiven.\n\n"
        "**Next Steps**\n"
        "- Contact Cedars-Sinai Patient Financial Services at "
        "[866-803-1777](tel:8668031777) or patient.billing@cshs.org.\n"
        "- Ask for the financial-assistance or Charity Care application.\n"
        "- Ask what documents they need, such as proof of income or household "
        "information."
    )


def _is_charity_care_coverage_question(text: str) -> bool:
    """Return whether the user asks whether assistance will cover the whole bill."""
    normalized = text.lower().strip()
    mentions_assistance = bool(
        re.search(r"\b(charity care|financial assistance|assistance|if i qualify|if approved)\b", normalized)
    )
    asks_full_coverage = bool(
        re.search(r"\b(pay|cover|forgive|waive)\b.*\b(all|full|entire|everything|whole)\b", normalized)
        or re.search(r"\b(all|full|entire|everything|whole)\b.*\b(bill|balance|amount)\b", normalized)
    )
    return mentions_assistance and asks_full_coverage


def _direct_charity_care_coverage_answer(user_message: str) -> str | None:
    """Answer whether Charity Care will cover the entire bill without recalculating FPL."""
    if not _is_charity_care_coverage_question(user_message):
        return None

    return (
        "**Summary**\n"
        "Not necessarily. Qualifying for Cedars-Sinai Charity Care or financial "
        "assistance does not automatically mean the entire bill will be paid, "
        "forgiven, or reduced to $0.\n\n"
        "**What This Means**\n"
        "Cedars-Sinai reviews the application and decides what assistance applies "
        "to the eligible patient balance. Depending on the review, assistance may "
        "cover part of the balance or, in some cases, more of it. The final decision "
        "has to come from Cedars-Sinai.\n\n"
        "**What To Ask Cedars-Sinai**\n"
        "- If I qualify, could my full patient balance be reduced or forgiven?\n"
        "- Would financial assistance apply to every charge on this bill?\n"
        "- Are any fees, prior balances, or collection-related charges treated differently?\n"
        "- Can billing or collections pause activity while my application is reviewed?\n\n"
        "**Next Steps**\n"
        "Contact Cedars-Sinai Patient Financial Services at "
        "[866-803-1777](tel:8668031777) or patient.billing@cshs.org and ask them "
        "to review your financial-assistance options."
    )


def _is_billing_website_question(text: str) -> bool:
    """Return whether the user is asking for the Cedars billing/payment website."""
    normalized = text.lower().strip()
    return bool(
        re.search(
            r"\b("
            r"online portal|payment portal|billing portal|pay online|pay my bill online|"
            r"website|web site|link|url"
            r")\b",
            normalized,
        )
        and re.search(r"\b(bill|billing|payment|pay|portal|cedars|link|website)\b", normalized)
    )


def _direct_billing_website_answer(user_message: str) -> str | None:
    """Return the Cedars-Sinai billing website without sending the user in circles."""
    if not _is_billing_website_question(user_message):
        return None

    return (
        "**Billing Website**\n"
        "You can start from Cedars-Sinai's billing page here: "
        "[https://www.cedars-sinai.org/patients-visitors/billing.html]"
        "(https://www.cedars-sinai.org/patients-visitors/billing.html).\n\n"
        "**What You May Need**\n"
        "Have your bill available when using the site or contacting Cedars-Sinai. "
        "You may need details from the bill, such as the patient or guarantor "
        "information, service date, and amount due. You do not need to paste full "
        "account numbers or sensitive identifiers here.\n\n"
        "**Other Ways To Get Help**\n"
        "- Phone: [866-803-1777](tel:8668031777), Monday–Friday, 8:00 AM–4:30 PM PT\n"
        "- Email: patient.billing@cshs.org"
    )


def _is_payment_plan_question(text: str) -> bool:
    """Return whether the user is asking how to set up or compare payment options."""
    normalized = text.lower().strip()
    return bool(
        re.search(
            r"\b("
            r"payment plan|payment plans|payment option|payment options|pay over time|"
            r"installment|installments|set up.*payment|make payments|monthly payment"
            r")\b",
            normalized,
        )
    )


def _direct_payment_plan_answer(user_message: str) -> str | None:
    """Return a consistent Cedars-specific payment-plan answer."""
    if not _is_payment_plan_question(user_message):
        return None

    return (
        "**How**\n"
        "Payment plans are handled through Cedars-Sinai Patient Financial "
        "Services. They can talk through options for paying the balance over "
        "time and whether financial assistance should be reviewed first.\n\n"
        "**What To Say**\n"
        "\"I received a Cedars-Sinai bill and would like to ask about payment "
        "plan options. Can you explain what monthly payment options are "
        "available and whether I should also apply for financial assistance?\"\n\n"
        "**What You May Need**\n"
        "Have the bill, service date, insurance information, and approximate "
        "household income ready. If you share your household size and approximate "
        "annual household income here, I can estimate your FPL percentage and "
        "suggest next steps before you call.\n\n"
        "**Next Steps**\n"
        "- Phone: [866-803-1777](tel:8668031777), Monday–Friday, 8:00 AM–4:30 PM PT\n"
        "- Email: patient.billing@cshs.org\n"
        "- Billing website: [Cedars-Sinai Billing](https://www.cedars-sinai.org/patients-visitors/billing.html)"
    )


def _is_general_bill_accuracy_question(text: str) -> bool:
    """Return whether the user is broadly worried the bill may be wrong."""
    normalized = text.lower().strip()
    return bool(
        re.search(
            r"\b("
            r"bill.*wrong|wrong.*bill|bill.*incorrect|incorrect.*bill|"
            r"information.*not.*correct|not.*correct|doesn'?t look right|"
            r"don'?t think.*correct|do not think.*correct|"
            r"something.*wrong|charge.*valid|valid.*charge|"
            r"wrong patient|not my bill|not mine|didn'?t receive|did not receive|"
            r"didn'?t get|did not get|never got|"
            r"never received.*service|service.*not.*receive"
            r")\b",
            normalized,
        )
    )


def _direct_bill_accuracy_answer(user_message: str) -> str | None:
    """Give scoped guidance for possible bill errors without deciding correctness."""
    if not _is_general_bill_accuracy_question(user_message):
        return None

    return (
        "**What I Can Check**\n"
        "I can help compare what is visible on the bill, such as the patient "
        "name, service date, insurance listed, line items, payments, adjustments, "
        "and total balance. If you mean a specific charge or section, tell me "
        "which one and I can help explain what it appears to be.\n\n"
        "**What Cedars-Sinai or Insurance Must Confirm**\n"
        "I cannot determine whether a charge is officially correct, incorrect, "
        "valid, or invalid. Cedars-Sinai billing or your insurer would need to "
        "confirm that.\n\n"
        "**What To Ask**\n"
        "- \"Can you confirm this bill belongs to me and matches the service date shown?\"\n"
        "- \"Can you explain why this charge appears on my bill?\"\n"
        "- \"Were insurance payments and adjustments applied correctly?\"\n"
        "- \"Is there an itemized statement or explanation of benefits I should compare this to?\"\n\n"
        "**What You May Need**\n"
        "Have the bill in front of you. Cedars-Sinai may ask for the patient "
        "name, patient account number, guarantor name/number, statement date, "
        "due date, service date, service names, CPT/HCPCS/revenue codes, total "
        "amount due, primary/secondary insurance listed, and any insurance "
        "payment or adjustment amounts shown. You do not need to paste full "
        "account numbers or sensitive identifiers here, but you may need them "
        "when speaking directly with Cedars-Sinai.\n\n"
        "**Next Steps**\n"
        "- Contact Cedars-Sinai Patient Financial Services.\n"
        "  - Phone: [866-803-1777](tel:8668031777), Monday–Friday, 8:00 AM–4:30 PM PT\n"
        "  - Email: patient.billing@cshs.org\n"
        "  - Billing website: [Cedars-Sinai Billing](https://www.cedars-sinai.org/patients-visitors/billing.html)\n"
        "- Have the bill and insurance Explanation of Benefits ready if you have one."
    )


def _is_call_prep_question(text: str) -> bool:
    """Return whether the user asks what information to have ready for contact."""
    normalized = text.lower().strip()
    return bool(
        re.search(
            r"\b("
            r"what information|what info|what details|what should i have|"
            r"what do i need|what might i need|what should i bring|"
            r"before i call|when i call|if i contact"
            r")\b",
            normalized,
        )
        and re.search(r"\b(contact|call|email|cedars|billing|them|insurance)\b", normalized)
    )


def _direct_call_prep_answer(user_message: str) -> str | None:
    """Return a concrete list of bill fields to have ready before contacting Cedars."""
    if not _is_call_prep_question(user_message):
        return None

    return (
        "**What You May Need**\n"
        "Have the bill in front of you before contacting Cedars-Sinai. They may "
        "ask for:\n"
        "- Patient name shown on the bill\n"
        "- Patient account number\n"
        "- Guarantor name and guarantor account number\n"
        "- Statement date and due date\n"
        "- Service date\n"
        "- Service names or line items you are asking about\n"
        "- CPT, HCPCS, or revenue codes shown on those line items\n"
        "- Total amount due and patient balance\n"
        "- Primary and secondary insurance listed\n"
        "- Insurance payment, adjustment, or denial amounts shown\n"
        "- Any Explanation of Benefits (EOB) from your insurer\n\n"
        "**Privacy Note**\n"
        "You do not need to paste full account numbers, MRNs, SSNs, dates of "
        "birth, or other sensitive identifiers here. If you call Cedars-Sinai "
        "using the official phone number, they may ask you to verify some bill "
        "details directly with them.\n\n"
        "**What To Say**\n"
        "\"I have a question about a Cedars-Sinai bill. Can you help me verify "
        "the patient information, service date, listed services, insurance "
        "payments, and total balance?\"\n\n"
        "**Contact**\n"
        "- Phone: [866-803-1777](tel:8668031777), Monday–Friday, 8:00 AM–4:30 PM PT\n"
        "- Email: patient.billing@cshs.org\n"
        "- Billing website: [Cedars-Sinai Billing](https://www.cedars-sinai.org/patients-visitors/billing.html)"
    )


def _is_legal_action_question(text: str) -> bool:
    """Return whether the user is asking for legal action advice."""
    normalized = text.lower().strip()
    return bool(
        re.search(r"\b(can i|should i|could i|do i)\b.*\b(sue|lawsuit|legal action|lawyer|attorney)\b", normalized)
        or re.search(r"\b(sue|lawsuit|legal action|lawyer|attorney)\b", normalized)
    )


def _direct_legal_boundary_answer(user_message: str) -> str | None:
    """Return scoped, practical guidance for legal-action questions."""
    if not _is_legal_action_question(user_message):
        return None

    return (
        "**Summary**\n"
        "I can’t give legal advice or tell you whether you should sue. What I "
        "can do is help you organize the billing issue so you can try to resolve "
        "it with Cedars-Sinai and your insurer first.\n\n"
        "**What To Do First**\n"
        "- Contact Cedars-Sinai Patient Financial Services and ask them to review "
        "the bill, patient information, service date, and listed services.\n"
        "- Contact your insurer and ask whether a claim for those services was "
        "processed under your plan.\n"
        "- Ask for an itemized statement and compare it with your Explanation of "
        "Benefits (EOB), if you have one.\n"
        "- Keep notes from every call, including dates, names, reference numbers, "
        "and what each person told you.\n\n"
        "**What You May Need**\n"
        "Have the bill, service date, patient/guarantor information, insurance "
        "information, total amount due, and any EOB ready. You do not need to "
        "paste full sensitive identifiers here.\n\n"
        "**Next Steps**\n"
        "- Phone: [866-803-1777](tel:8668031777), Monday–Friday, 8:00 AM–4:30 PM PT\n"
        "- Email: patient.billing@cshs.org\n"
        "- If the issue is not resolved or you believe you were harmed, consider "
        "speaking with a qualified legal professional for advice specific to "
        "your situation."
    )


def _direct_fpl_answer(user_message: str, history: list[dict] | None = None) -> str | None:
    """Return a deterministic FPL answer when both required inputs are present."""
    if not _should_use_fpl_from_message(user_message):
        return None

    fpl_inputs = _extract_fpl_inputs(user_message, history)
    if not fpl_inputs:
        return None

    result = json.loads(calculate_fpl.handler(fpl_inputs))
    if "error" in result:
        return None

    household_size = result["household_size"]
    annual_income = result["annual_income_usd"]
    fpl_100 = result["fpl_100_percent_usd"]
    fpl_percentage = result["fpl_percentage"]
    assistance_tier = result["assistance_tier"]
    guidance = result["guidance"]
    if assistance_tier == "Above standard FAP threshold":
        summary = (
            "Based on the household size and income you shared, this screening "
            "estimate is above the standard Cedars-Sinai financial-assistance "
            "income thresholds."
        )
        meaning = (
            f"{guidance} This does not mean you are approved or denied. It means "
            "income-based Charity Care or Discount Payment assistance may be less "
            "likely based on this estimate, but you can still ask Cedars-Sinai "
            "about payment plans or hardship review options."
        )
        next_steps = (
            "- Contact Cedars-Sinai Patient Financial Services.\n"
            "  - Phone: [866-803-1777](tel:8668031777), Monday–Friday, 8:00 AM–4:30 PM PT\n"
            "  - Email: patient.billing@cshs.org\n"
            "  - Website: [Cedars-Sinai Billing](https://www.cedars-sinai.org/patients-visitors/billing.html)\n"
            "- Ask about payment plan options and whether hardship review is available."
        )
    else:
        summary = (
            "Based on the household size and income you shared, you may be a "
            f"{assistance_tier.lower()}."
        )
        meaning = (
            f"{guidance} This does not guarantee approval, but it means applying "
            "is worth asking about."
        )
        next_steps = (
            "- Contact Cedars-Sinai Patient Financial Services.\n"
            "  - Phone: [866-803-1777](tel:8668031777), Monday–Friday, 8:00 AM–4:30 PM PT\n"
            "  - Email: patient.billing@cshs.org\n"
            "  - Website: [Cedars-Sinai Billing](https://www.cedars-sinai.org/patients-visitors/billing.html)\n"
            "- Ask for the financial-assistance application."
        )

    return (
        "**Summary**\n"
        f"{summary}\n\n"
        "**FPL Calculation Breakdown**\n"
        f"- Household size: {household_size}\n"
        f"- Annual household income: {_format_usd(annual_income)}\n"
        f"- {result['fpl_year']} Federal Poverty Guideline for household of {household_size}: {_format_usd(fpl_100)}\n"
        f"- Your estimated FPL: {fpl_percentage}% ({_format_usd(annual_income)} ÷ {_format_usd(fpl_100)})\n\n"
        "**What This Means**\n"
        f"{meaning}\n\n"
        "**Next Steps**\n"
        f"{next_steps}"
    )


def _redact_message_for_model(text: str) -> str:
    """Remove obvious PHI before sending user text to the model."""
    return input_redactor.redact(text)


def _message_has_phi(text: str) -> bool:
    """Return whether the user text changed after PHI redaction."""
    return _redact_message_for_model(text) != text


def _sensitive_info_notice() -> str:
    return (
        "You do not need to share sensitive identifiers such as SSNs, MRNs, "
        "dates of birth, or full account numbers here.\n\n"
    )


def _clean_duplicate_sensitive_notice(text: str) -> str:
    """Remove model-generated sensitive-info reminders before app prefixing."""
    patterns = [
        r"^\s*You do not need to share sensitive identifiers such as your SSN or MRN here\.\s*",
        r"^\s*You do not need to share sensitive identifiers such as SSNs?, MRNs?, dates of birth, or full account numbers here\.\s*",
        r"^\s*Please do not share sensitive identifiers such as SSNs?, MRNs?, dates of birth, or full account numbers here\.\s*",
    ]
    cleaned = text
    for pattern in patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    return cleaned.lstrip()


def _clean_internal_tool_text(text: str) -> str:
    """Remove accidental internal tool/function syntax from model text."""
    cleaned = re.sub(r"<function\.[^>]*>", "", text, flags=re.IGNORECASE)
    cleaned = re.sub(
        r"^\s*Also,\s*I will call the [^\n.]*function[^\n.]*\.?\s*$",
        "",
        cleaned,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    cleaned = re.sub(
        r"^\s*I will call the [^\n.]*function[^\n.]*\.?\s*$",
        "",
        cleaned,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    cleaned = re.sub(
        r"^\s*The [a-z_]+ function is [^\n.]*\.?\s*$",
        "",
        cleaned,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    placeholder_replacements = {
        "[REDACTED:PATIENT_ACCOUNT]": "the patient account number shown on the bill",
        "[REDACTED:JSON_ACCOUNT_NUMBER]": "the account number shown on the bill",
        "[REDACTED:GUARANTOR_ACCOUNT]": "the guarantor account number shown on the bill",
        "[REDACTED:PATIENT_NAME]": "the patient name shown on the bill",
        "[REDACTED:JSON_PATIENT_NAME]": "the patient name shown on the bill",
        "[REDACTED:MRN]": "a sensitive identifier",
        "[REDACTED:DOB]": "a date of birth",
        "[REDACTED:SSN]": "an SSN",
        "[REDACTED:EMAIL]": "a private email address",
        "[REDACTED:PATIENT_PHONE]": "a private phone number",
    }
    for placeholder, replacement in placeholder_replacements.items():
        cleaned = cleaned.replace(placeholder, replacement)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _phi_redaction_context_message(original_text: str) -> Message | None:
    """Tell the model when user-entered sensitive identifiers were removed."""
    if not _message_has_phi(original_text):
        return None

    return Message(
        role="system",
        content=(
            "The user's message included sensitive identifiers that were "
            "redacted before model processing. Do not repeat or ask for SSNs, "
            "MRNs, dates of birth, full account numbers, or similar sensitive "
            "details. The application will display a sensitive-information "
            "reminder separately, so do not add your own reminder. Answer the "
            "billing question using the remaining safe bill information."
        ),
    )


def _technical_fallback_message(user_message: str) -> str:
    """Return a relevant fallback when the model/provider errors mid-response."""
    text = user_message.lower()

    if any(word in text for word in ("insurance", "provider", "primary", "secondary")):
        return (
            "I’m sorry, I ran into a technical issue while checking that. "
            "To identify your insurance provider, I need the bill or the part "
            "of the bill that lists Primary Insurance and Secondary Insurance. "
            "Please upload the bill again or paste those lines, and I can help "
            "read them."
        )

    if any(
        phrase in text
        for phrase in (
            "help paying",
            "can't afford",
            "cannot afford",
            "financial assistance",
            "charity care",
            "payment plan",
            "household",
            "income",
            "fpl",
        )
    ):
        return (
            "I’m sorry, I ran into a technical issue while preparing that "
            "financial-assistance answer. If you share your household size and "
            "approximate annual household income, I can estimate your FPL "
            "percentage and suggest next steps."
        )

    if any(word in text for word in ("bill", "charge", "charges", "uploaded", "pdf")):
        return (
            "I’m sorry, I ran into a technical issue while preparing that bill "
            "explanation. Please try again, or ask about a specific line item, "
            "total amount due, insurance adjustment, or next step."
        )

    return (
        "I’m sorry, I ran into a technical issue while preparing that answer. "
        "Please try again, or paste the relevant bill details and I can help "
        "explain them."
    )


def _make_client():
    """Create an LLM client based on env config."""
    if API_PROVIDER == "anthropic":
        from agent_harness import AnthropicClient
        return AnthropicClient(api_key=API_KEY, model=API_MODEL)
    elif API_PROVIDER == "azure":
        from agent_harness import AzureModelClient
        return AzureModelClient(
            endpoint=API_ENDPOINT,
            deployment=API_MODEL,
            api_key=API_KEY,
        )
    else:
        return OpenAICompatibleClient(
            base_url=API_ENDPOINT,
            api_key=API_KEY,
            model=API_MODEL,
        )


def _build_harness() -> AgentHarness:
    """Build the main agent harness with all tools, hooks, and skills."""
    client = _make_client()
    system_prompt = build_system_prompt()

    # Combine registered tools with the search tool (backed by local RAG)
    all_tools = list(REGISTERED_TOOLS) + [create_search_bills_tool(search_service)]

    return AgentHarness(
        client=client,
        system_prompt=system_prompt,
        tools=all_tools,
        hooks=REGISTERED_HOOKS,
        max_iterations=15,
    )


# ── Routes ──────────────────────────────────────────────────────────────

@app.get("/")
async def index(request: Request):
    return await response.file(str(_APP_DIR / "static" / "index.html"))


@app.get("/health")
async def health(request: Request):
    return response.json({"status": "ok"})


@app.post("/chat")
async def chat(request: Request):
    """Handle a chat message. Returns Server-Sent Events (SSE) stream."""
    body = request.json or {}
    user_message = body.get("message", "")
    history = body.get("history", [])

    if not user_message:
        return response.json({"error": "message is required"}, status=400)

    direct_fpl_definition = _direct_fpl_definition_answer(user_message)
    if direct_fpl_definition:
        async def stream_direct_fpl_definition(resp):
            await resp.write(
                f"data: {json.dumps({'text': direct_fpl_definition})}\n\n".encode()
            )
            await resp.write(b"data: [DONE]\n\n")

        return response.ResponseStream(
            stream_direct_fpl_definition,
            content_type="text/event-stream",
        )

    direct_charity_care_definition = _direct_charity_care_definition_answer(user_message)
    if direct_charity_care_definition:
        async def stream_direct_charity_care_definition(resp):
            await resp.write(
                f"data: {json.dumps({'text': direct_charity_care_definition})}\n\n".encode()
            )
            await resp.write(b"data: [DONE]\n\n")

        return response.ResponseStream(
            stream_direct_charity_care_definition,
            content_type="text/event-stream",
        )

    direct_charity_care_coverage = _direct_charity_care_coverage_answer(user_message)
    if direct_charity_care_coverage:
        async def stream_direct_charity_care_coverage(resp):
            await resp.write(
                f"data: {json.dumps({'text': direct_charity_care_coverage})}\n\n".encode()
            )
            await resp.write(b"data: [DONE]\n\n")

        return response.ResponseStream(
            stream_direct_charity_care_coverage,
            content_type="text/event-stream",
        )

    direct_billing_website = _direct_billing_website_answer(user_message)
    if direct_billing_website:
        async def stream_direct_billing_website(resp):
            await resp.write(
                f"data: {json.dumps({'text': direct_billing_website})}\n\n".encode()
            )
            await resp.write(b"data: [DONE]\n\n")

        return response.ResponseStream(
            stream_direct_billing_website,
            content_type="text/event-stream",
        )

    direct_payment_plan = _direct_payment_plan_answer(user_message)
    if direct_payment_plan:
        async def stream_direct_payment_plan(resp):
            await resp.write(
                f"data: {json.dumps({'text': direct_payment_plan})}\n\n".encode()
            )
            await resp.write(b"data: [DONE]\n\n")

        return response.ResponseStream(
            stream_direct_payment_plan,
            content_type="text/event-stream",
        )

    direct_bill_accuracy = _direct_bill_accuracy_answer(user_message)
    if direct_bill_accuracy:
        async def stream_direct_bill_accuracy(resp):
            await resp.write(
                f"data: {json.dumps({'text': direct_bill_accuracy})}\n\n".encode()
            )
            await resp.write(b"data: [DONE]\n\n")

        return response.ResponseStream(
            stream_direct_bill_accuracy,
            content_type="text/event-stream",
        )

    direct_call_prep = _direct_call_prep_answer(user_message)
    if direct_call_prep:
        async def stream_direct_call_prep(resp):
            await resp.write(
                f"data: {json.dumps({'text': direct_call_prep})}\n\n".encode()
            )
            await resp.write(b"data: [DONE]\n\n")

        return response.ResponseStream(
            stream_direct_call_prep,
            content_type="text/event-stream",
        )

    direct_legal_boundary = _direct_legal_boundary_answer(user_message)
    if direct_legal_boundary:
        async def stream_direct_legal_boundary(resp):
            await resp.write(
                f"data: {json.dumps({'text': direct_legal_boundary})}\n\n".encode()
            )
            await resp.write(b"data: [DONE]\n\n")

        return response.ResponseStream(
            stream_direct_legal_boundary,
            content_type="text/event-stream",
        )

    direct_fpl_answer = _direct_fpl_answer(user_message, history)
    if direct_fpl_answer:
        async def stream_direct_fpl(resp):
            await resp.write(
                f"data: {json.dumps({'text': direct_fpl_answer})}\n\n".encode()
            )
            await resp.write(b"data: [DONE]\n\n")

        return response.ResponseStream(
            stream_direct_fpl,
            content_type="text/event-stream",
        )

    user_message_has_phi = _message_has_phi(user_message)
    messages = []
    for msg in history:
        messages.append(
            Message(
                role=msg["role"],
                content=_redact_message_for_model(msg["content"]),
            )
        )
    fpl_context = _fpl_context_message(user_message, history)
    if fpl_context:
        messages.append(fpl_context)
    phi_context = _phi_redaction_context_message(user_message)
    if phi_context:
        messages.append(phi_context)
    messages.append(Message(role="user", content=_redact_message_for_model(user_message)))

    harness = _build_harness()

    async def stream_response(resp):
        loop = asyncio.get_event_loop()

        def run_agent():
            chunks = []
            for chunk in harness.run_stream(messages):
                chunks.append(chunk)
            return chunks

        try:
            chunks = await loop.run_in_executor(None, run_agent)
        except Exception:
            logger.exception("Agent response generation failed")
            chunks = [_technical_fallback_message(user_message)]
        cleaned_text = _clean_internal_tool_text("".join(chunks))
        if cleaned_text:
            chunks = [cleaned_text]
        else:
            chunks = [_technical_fallback_message(user_message)]
        if user_message_has_phi:
            combined = _clean_duplicate_sensitive_notice("".join(chunks))
            chunks = [_sensitive_info_notice() + combined]
        for chunk in chunks:
            await resp.write(f"data: {json.dumps({'text': chunk})}\n\n".encode())
        await resp.write(b"data: [DONE]\n\n")

    return response.ResponseStream(stream_response, content_type="text/event-stream")


@app.post("/upload")
async def upload(request: Request):
    """Upload a document (PDF, image, text) to the knowledge base."""
    if not request.files:
        return response.json({"error": "No file uploaded"}, status=400)

    uploaded = request.files.get("file")
    if not uploaded:
        return response.json({"error": "No file in request"}, status=400)

    filename = Path(uploaded.name).name
    file_body = uploaded.body

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    save_path = UPLOAD_DIR / filename
    save_path.write_bytes(file_body)

    indexer.index_file(str(save_path))

    return response.json(
        {
            "status": "indexed",
            "filename": filename,
            "path": str(save_path),
        }
    )


# ── Startup ─────────────────────────────────────────────────────────────

@app.before_server_start
async def startup(app, loop):
    """Index existing knowledge base documents on startup."""
    indexer.index_all()


if __name__ == "__main__":
    if not API_KEY:
        print("ERROR: Set API_KEY environment variable before running.")
        print("See .env.example for required configuration.")
        sys.exit(1)
    app.run(host=HOST, port=PORT, debug=os.environ.get("DEBUG", "").lower() == "true")
