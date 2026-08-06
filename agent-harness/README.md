# Healthcare Bill Agent — Capstone Starter

A starter harness for building an AI-powered healthcare bill analysis agent. This project provides the scaffolding for you to create your own tools, hooks, skills, and knowledge-base integrations.

## Architecture

```
agent-harness/
├── src/
│   ├── agent_harness/          # Core framework (DO NOT MODIFY)
│   │   ├── core.py             # Agent loop: call model → execute tools → repeat
│   │   ├── tools.py            # Tool definition (@tool decorator, create_tool factory)
│   │   ├── hooks.py            # Hook base class (safety checks before/after tools)
│   │   ├── messages.py         # Message, ToolCall, StreamChunk data types
│   │   └── clients/            # LLM provider clients (OpenAI, Anthropic, Azure)
│   │
│   └── app/                    # YOUR APPLICATION (extend this)
│       ├── server.py           # Sanic web server (main entrypoint)
│       ├── rag/                # Knowledge base indexing & search
│       │   ├── indexer.py      # Reads PDFs, text, Excel → searchable chunks
│       │   └── search.py       # TF-IDF search (replace with embeddings)
│       ├── tools/              # Agent tools (add your own here)
│       │   ├── bill_parser.py  # Parses uploaded bill PDFs/photos
│       │   ├── calculate_fpl.py# FPL percentage calculator
│       │   └── search_bills.py # Knowledge base search
│       ├── hooks/              # Safety hooks (add your own here)
│       │   ├── phi_redaction.py# Redact PHI from outputs
│       │   └── content_filter.py# Block dangerous operations
│       ├── skills/             # Procedural instructions (markdown)
│       │   ├── bill_analysis.md
│       │   └── bill_explanation.md
│       └── static/             # Frontend UI
│           └── index.html      # Chat interface
│
├── Dockerfile                  # Container build
├── docker-compose.yml          # Container orchestration
├── requirements.txt            # Python dependencies
├── .env.example                # Configuration template
└── README.md                   # This file
```

## Quick Start

### 1. Setup Environment

```bash
# Clone/copy this directory
cd agent-harness

# Create virtual environment
python -m venv venv
source venv/bin/activate  # or: venv\Scripts\activate (Windows)

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure API Keys

```bash
# Copy the example env file
cp .env.example .env

# Edit .env with your API credentials
# You need at minimum: API_KEY and API_ENDPOINT
```

### 3. Run Locally

```bash
# Set PYTHONPATH and run
export PYTHONPATH=src  # or: set PYTHONPATH=src (Windows)
python -m app.server
```

Then open http://localhost:8000 in your browser.

### 4. Run with Docker

```bash
docker compose up --build
```

## How to Extend

### Adding a Tool

Tools give the agent new capabilities. Create a file in `src/app/tools/`:

```python
# src/app/tools/my_tool.py
from agent_harness import tool
import json

@tool(
    name="my_tool",
    description="What this tool does (the model reads this)",
    parameters={
        "type": "object",
        "properties": {
            "param1": {"type": "string", "description": "What this param is"},
        },
        "required": ["param1"],
    },
)
def my_tool(args: dict) -> str:
    result = do_something(args["param1"])
    return json.dumps(result)
```

Then register it in `src/app/tools/__init__.py`:

```python
from app.tools.my_tool import my_tool
TOOLS = [..., my_tool]
```

### Adding a Hook

Hooks enforce safety rules. Create a file in `src/app/hooks/`:

```python
# src/app/hooks/my_hook.py
from agent_harness import Hook, HookResult

class MyHook(Hook):
    def before_tool_call(self, tool_name, args):
        if something_dangerous(args):
            return HookResult(allowed=False, reason="Blocked because...")
        return HookResult(allowed=True)

    def after_tool_call(self, tool_name, args, result):
        return redact_sensitive_data(result)
```

Register it in `src/app/hooks/__init__.py`.

### Adding a Skill

Skills are markdown instructions loaded into the system prompt:

1. Create `src/app/skills/my_skill.md` with procedural instructions
2. Add the filename to `SKILL_FILES` in `src/app/skills/__init__.py`

### Adding to the Knowledge Base

Drop files into the `Knowledge Docs/` directory (one level up from this project):
- PDFs, text files, and Excel files are indexed automatically on startup
- Photos (.jpg/.jpeg/.png/.heic/.heif) are stored as references, not indexed for search — the `bill_parser` tool OCRs bill photos directly on request, the same way it reads PDFs
- Use the `/upload` endpoint or the Upload button in the UI to add files at runtime

### Improving Search (RAG)

The starter uses TF-IDF keyword search. For better results:

1. Add `sentence-transformers` and `chromadb` to requirements.txt
2. Replace `LocalSearchService` in `src/app/rag/search.py` with embedding-based search
3. Update the indexer to generate embeddings during indexing

### Adding External APIs

To integrate external services (insurance lookup, medical code databases, etc.):

1. Create a tool that calls the API
2. Add any required API keys to `.env.example` and `.env`
3. Read the key in your tool: `os.environ.get("MY_API_KEY")`

## Key Concepts

| Concept | What It Is | Where |
|---------|-----------|-------|
| **Tool** | A function the LLM can call | `src/app/tools/` |
| **Hook** | Safety check before/after tools | `src/app/hooks/` |
| **Skill** | Instructions loaded into the prompt | `src/app/skills/` |
| **RAG** | Search over local documents | `src/app/rag/` |
| **Client** | LLM provider connection | `src/agent_harness/clients/` |

## Deliverables

Your final product should be a working web interface that:
1. Accepts patient bill uploads (images, PDFs)
2. Uses the agent harness with your custom tools, hooks, and skills
3. Searches the knowledge base (local file RAG) for relevant policies
4. Provides clear, empathetic explanations and next-step recommendations
5. Runs in a Docker container

## Troubleshooting

- **"API_KEY not set"**: Copy `.env.example` to `.env` and fill in your credentials
- **PDF indexing fails**: Make sure `pdfplumber` is installed (`pip install pdfplumber`)
- **Port 8000 in use**: Change PORT in `.env` or use `docker compose up` with a different port mapping
- **Module not found**: Make sure PYTHONPATH includes `src/` (set in Dockerfile automatically)
