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


def _extract_fpl_inputs(text: str) -> dict[str, int | float] | None:
    """Extract simple household size and income values from patient text."""
    household_match = re.search(
        r"\b(?:household|family)\s*(?:size)?\s*(?:is|:)?\s*(\d{1,2})\b",
        text,
        re.IGNORECASE,
    )
    income_match = re.search(
        r"\b(?:household\s*)?(?:income|make|earn|salary)\b[^$\d]{0,20}\$?\s*([\d,]+(?:\.\d{2})?)",
        text,
        re.IGNORECASE,
    )

    if not household_match or not income_match:
        return None

    return {
        "household_size": int(household_match.group(1)),
        "annual_income_usd": float(income_match.group(1).replace(",", "")),
    }


def _fpl_context_message(user_message: str) -> Message | None:
    """Pre-calculate FPL context when the user supplies both required values."""
    fpl_inputs = _extract_fpl_inputs(user_message)
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

    if any(word in text for word in ("bill", "charge", "charges", "uploaded", "pdf")):
        return (
            "I’m sorry, I ran into a technical issue while preparing that bill "
            "explanation. Please try again without including sensitive details "
            "like SSNs, MRNs, dates of birth, or account numbers. You can ask "
            "something like: “I uploaded the bill. Can you explain the total "
            "amount due and next steps?”"
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

    user_message_has_phi = _message_has_phi(user_message)
    messages = []
    for msg in history:
        messages.append(
            Message(
                role=msg["role"],
                content=_redact_message_for_model(msg["content"]),
            )
        )
    fpl_context = _fpl_context_message(user_message)
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
