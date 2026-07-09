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
    match = re.search(
        r"\b(?:household|family)\s*(?:size)?\s*(?:is|:)?\s*(\d{1,2})\b",
        text,
        re.IGNORECASE,
    )
    return int(match.group(1)) if match else None


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


def _fpl_context_message(user_message: str, history: list[dict] | None = None) -> Message | None:
    """Pre-calculate FPL context when the user supplies both required values."""
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


def _direct_fpl_answer(user_message: str, history: list[dict] | None = None) -> str | None:
    """Return a deterministic FPL answer when both required inputs are present."""
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

    return (
        "Based on the household size and income you shared, you may be a "
        f"{assistance_tier.lower()}.\n\n"
        f"For a household of {household_size}, 100% of the {result['fpl_year']} "
        f"Federal Poverty Level is {_format_usd(fpl_100)}. Your household "
        f"income is {_format_usd(annual_income)}, so your estimated FPL is "
        f"{fpl_percentage}%.\n\n"
        f"What this means: {guidance} This does not guarantee approval, but it "
        "means applying is worth asking about.\n\n"
        "Next step: contact Cedars-Sinai Patient Financial Services at "
        "[866-803-1777](tel:8668031777) or patient.billing@cshs.org and ask "
        "for the financial-assistance application. You can tell them your "
        f"household size is {household_size} and your approximate annual "
        f"household income is {_format_usd(annual_income)}."
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
