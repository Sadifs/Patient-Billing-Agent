# Confronting the Confusion Around Healthcare Bills

**LMU MSBA Capstone Project | Cedars-Sinai Health System**

An AI-powered agent that helps patients understand their hospital bills by providing plain-language explanations, identifying relevant financial assistance programs, and generating talking points for conversations with billing departments and insurers.

## Problem Statement

Getting a bill after a hospital stay is often a stressful, confusing experience. Even people with industry experience are frequently confused by what appears on a bill. This project provides patients with:

- AI-generated explanations of all line items on a bill
- A list of resources to reach out to (financial assistance, Patient Services, insurance contacts)
- Talking points and questions to ask when contacting those resources

## Project Structure

```
LMU Capstone/
├── agent-harness/              # Application code (Python + Docker)
│   ├── src/
│   │   ├── agent_harness/      # Core agent framework (DO NOT MODIFY)
│   │   └── app/                # Your application (extend this)
│   │       ├── server.py       # Sanic web server (entrypoint)
│   │       ├── rag/            # Knowledge base indexing & search
│   │       ├── tools/          # Agent tools (bill explanation, FPL calc, search)
│   │       ├── hooks/          # Safety hooks (PHI redaction, content filter)
│   │       ├── roles/          # Sub-agent identities (markdown)
│   │       ├── skills/         # Procedural instructions (markdown)
│   │       └── static/         # Chat UI
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── requirements.txt
│
├── knowledge-docs/             # Domain knowledge for RAG
│   ├── billing-faq.pdf         # Cedars-Sinai billing FAQ
│   ├── key-definitions-glossary.pdf  # Insurance/billing terminology
│   ├── full-fap-english.pdf    # Financial Assistance Policy (full)
│   ├── plain-language-summary-english.pdf  # FAP plain-language summary
│   ├── fap-application-english.pdf   # FAP application form
│   ├── fpl-percentage.pdf      # Federal Poverty Level percentages
│   ├── debt-collection-policy-english.pdf  # Debt collection policy
│   ├── amounts-generally-billed.pdf  # Standard billing amounts
│   ├── cedars-sinai-chargemaster-july-2024.xlsx  # Full chargemaster
│   ├── cedars-sinai-25-common-op-procedures-2024.xlsx  # Common procedure prices
│   ├── sample_bill_pdf.pdf     # Sample bill (PDF)
│   ├── sample_bill_jpeg.jpg    # Sample bill (image)
│   ├── fap-user-report.pdf     # FAP user report
│   ├── hh-fap-user-report.pdf  # Home Health FAP user report
│   └── mdrh-fap-user-report.pdf  # Marina del Rey Hospital FAP report
│
├── synthetic-data/             # Synthetic validation dataset (current expanded set)
│   ├── README.md               # Dataset overview, schema, validation rubric
│   ├── synthetic_validation_dataset.csv       # Master answer key — 135 labeled test cases
│   ├── generate_v2_bills.py    # V2 bill generation for bills 01–15
│   ├── generate_v2_csv.py      # V2 validation CSV for bills 01–15
│   ├── generate_new_bills.py   # Generates bills 16–25 (reproducible)
│   ├── generate_v2_pdfs.py     # PDF renderer for all v2 bills
│   ├── edge-cases/             # Planning CSVs (reference, not used in evaluation)
│   ├── synthetic_bills_v2/     # V2 — 70 evaluator bills (JSON + PDF, full metadata)
│   └── synthetic_bills_v2_agent/  # V2 — 70 LLM-safe bills (JSON, metadata stripped)
│
├── research-docs/              # Independent research by track
│   ├── billing-fundamentals.pdf     # Healthcare billing fundamentals
│   ├── financial-assistance.pdf     # Financial assistance & FPL policy
│   ├── ai-agent-architecture.pdf    # Agent architecture & RAG
│   └── evaluation-methods.pdf       # Evaluation methods & rubric
│
├── instructions/               # Project scope & requirements
│   ├── Cedars MSBA Capstone Project Description.pdf
│   └── LMU MSBA Cedars Capstone Outline Plan.pptx
│
└── README.md                   # This file
```

## Quick Start

```bash
cd agent-harness

# Create virtual environment
python -m venv venv
source venv/bin/activate        # Linux/Mac
venv\Scripts\activate           # Windows

# Install dependencies
pip install -r requirements.txt

# Configure API credentials
cp .env.example .env
# Edit .env with your API_KEY and API_ENDPOINT

# Run the server
set PYTHONPATH=src              # Windows
export PYTHONPATH=src           # Linux/Mac
python -m app.server
```

Open http://localhost:8000 in your browser.

### Docker

```bash
cd agent-harness
docker compose up --build
```

## Knowledge Base

The `knowledge-docs/` directory contains Cedars-Sinai billing and financial assistance documents that are indexed on startup and searchable via RAG. Key resources include:

| Document | Purpose |
|----------|---------|
| Billing FAQ | Common patient questions about billing, payments, insurance |
| Glossary | Definitions of billing/insurance terms (deductible, coinsurance, EOB, etc.) |
| Financial Assistance Policy | Eligibility criteria and application process for charity care |
| FPL Percentages | Federal Poverty Level thresholds for assistance qualification |
| Chargemaster | Full list of hospital charges |
| Common Procedures | Pricing for 25 most common outpatient procedures |
| Debt Collection Policy | Patient rights and collection process |

## Evaluation

The formal evaluation workflow lives in [`evaluation/README.md`](evaluation/README.md).
Use it to validate the synthetic dataset, run cases through the local agent, and
summarize scored review CSVs.

For the current evaluation artifacts:

- **Synthetic answer key, not scored review output:** [`synthetic-data/synthetic_validation_dataset.csv`](synthetic-data/synthetic_validation_dataset.csv)
- **Synthetic dataset schema:** [`synthetic-data/README.md`](synthetic-data/README.md)
- **Final evaluation scoring template:** [`evaluation/results/final_agent_evaluation_scoring_template.csv`](evaluation/results/final_agent_evaluation_scoring_template.csv)
- **Final evaluation scoring rubric:** [`evaluation/results/final_evaluation_scoring_rubric.md`](evaluation/results/final_evaluation_scoring_rubric.md)
- **Final LLM-assisted batch workflow:** [`evaluation/results/final_llm_assisted_evaluation_instructions.md`](evaluation/results/final_llm_assisted_evaluation_instructions.md)
- **Midterm scored review CSV:** [`evaluation/results/midterm_agent_evaluation_scoring.csv`](evaluation/results/midterm_agent_evaluation_scoring.csv)
- **Midterm results guide:** [`evaluation/results/README.md`](evaluation/results/README.md)
- **Midterm error analysis:** [`evaluation/results/midterm_error_analysis.md`](evaluation/results/midterm_error_analysis.md)

Basic evaluation flow:

1. Validate the synthetic dataset:
   ```bash
   python3 -m evaluation.evaluation_harness validate
   ```
2. Start the local agent:
   ```bash
   cd agent-harness
   docker compose up --build
   ```
3. In another terminal, run selected cases through the live agent:
   ```bash
   python3 -m evaluation.evaluation_harness run-live \
     --case-id DV2-021 \
     --case-id DV2-063 \
     --output evaluation/live_agent_review_selected.csv
   ```
   To batch-run all 135 final cases:
   ```bash
   python3 -m evaluation.evaluation_harness run-live \
     --output evaluation/results/final_agent_evaluation_live_outputs.csv \
     --timeout-seconds 180
   ```
4. Score the generated CSV using human review plus optional LLM assistance.
   Use [`evaluation/results/final_llm_assisted_evaluation_instructions.md`](evaluation/results/final_llm_assisted_evaluation_instructions.md)
   for the final handoff workflow and the `llm_*` scoring columns.
5. Summarize the completed review CSV:
   ```bash
   python3 -m evaluation.evaluation_harness summarize \
     evaluation/live_agent_review_selected.csv
   ```
6. Use low scores and `reviewer_notes` to decide whether fixes belong in
   prompts, parser logic, safety hooks, UI context handling, or evaluation data.

## Architecture

The application uses an **agent harness** pattern:

1. **Agent Loop** (`agent_harness/core.py`) — Calls the LLM, executes tool calls, and repeats until the agent has a final response
2. **Tools** — Functions the LLM can invoke (explain bill line items, calculate FPL eligibility, search knowledge base)
3. **Hooks** — Safety checks that run before/after each tool call (PHI redaction, content filtering)
4. **Skills** — Markdown instructions loaded into the system prompt for procedural guidance
5. **Roles** — Identity documents for specialized sub-agents
6. **RAG** — TF-IDF search over indexed knowledge documents (upgradeable to embeddings)

Supported LLM providers: OpenAI, Anthropic, Azure OpenAI.

## Key Concepts

| Concept | Description | Location |
|---------|-------------|----------|
| Tool | A function the LLM can call | `agent-harness/src/app/tools/` |
| Hook | Safety check before/after tool execution | `agent-harness/src/app/hooks/` |
| Skill | Instructions loaded into the system prompt | `agent-harness/src/app/skills/` |
| Role | Identity for a specialized sub-agent | `agent-harness/src/app/roles/` |
| RAG | Retrieval-augmented generation over local docs | `agent-harness/src/app/rag/` |

## Extending the Application

See [`agent-harness/README.md`](agent-harness/README.md) for detailed instructions on:

- Adding new tools
- Adding safety hooks
- Adding skills and sub-agent roles
- Improving RAG with embeddings
- Integrating external APIs

## Deliverables

The final product is a working web application that:

1. Accepts patient bill uploads (images, PDFs)
2. Explains all line items in plain language
3. Searches the knowledge base for relevant policies and resources
4. Calculates financial assistance eligibility (FPL-based)
5. Provides empathetic explanations and next-step recommendations
6. Runs in a Docker container

## Timeline

| Milestone | Date |
|-----------|------|
| Project Kickoff | March 31, 2026 |
| Weekly Syncs | May 18 - August 7, 2026 |
| Kick-off Presentation | June 12, 2026 |
| Final Presentation | August 7, 2026 |
| Final Report & Code Handoff | August 9, 2026 |

## Stakeholders

- **Primary beneficiary**: Patients receiving bills from Cedars-Sinai
- **Secondary beneficiary**: Billing customer service (reduced call volume)
- **Support**: Revenue Cycle team + AI team at Cedars-Sinai

## Data & Privacy

- Patient data is mocked/synthetic — no real PHI
- All non-synthetic data must remain within Cedars environments
