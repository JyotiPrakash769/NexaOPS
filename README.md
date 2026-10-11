# NexaOps: Autonomous AI Operations Employee

> **Take-Home Project for CentrAlign AI (Founding Engineer Assignment)**  
> An autonomous AI Operations worker that receives business objectives in natural language, selects real tools, executes actions against a controlled company environment, observes results, adapts to failures, requests human approval when required, independently verifies outcomes, and returns verifiable evidence.
>
> 📖 **[Comprehensive Master Project & Demonstration Guide](file:///C:/Users/jyoti/.gemini/antigravity-ide/scratch/nexaops/MASTER_PROJECT_GUIDE.md)**: Full breakdown of objectives, company rules alignment, usage, live interview demo pitch, and Q&A answers.

---

## 1. Core Architectural Principle

```text
The LLM proposes; deterministic code controls.
```

- **The LLM never directly touches the database, runs SQL, or executes arbitrary shell commands.**
- It only outputs structured JSON actions: `{"thought_summary": "...", "action": "...", "args": {...}}`.
- Pure Python code (`agent/policy.py`) enforces:
  - Allowed tools allowlist
  - Pydantic schema validation
  - Supervisor approval gates (for invoices $\ge \$10,000$)
  - Mandatory independent verification before task completion (`verify_finance_record`)
  - Bounded step limits (max 15 steps)
  - Immunity to prompt injection inside invoice documents

---

## 2. Technology Stack (Minimal & Explainable)

- **Language**: Python 3.11+ / 3.12 (standard library + lightweight utilities)
- **Data Validation**: `pydantic` v2 (schemas for all tools & state models)
- **Storage**: `sqlite3` (Python stdlib) for mock finance system & audit event logging
- **PDF Extraction**: `pypdf` for extracting text streams from invoices
- **PDF Generation**: `reportlab` for generating reproducible test invoices
- **AI Providers**: Pluggable adapter in `agent/llm.py` supporting `fake` (offline deterministic), `gemini` (Gemini 2.5 Flash), and `openai` (GPT-4o Mini)
- **Testing**: `pytest` (17/17 passing deterministic offline tests)
- **Optional Web Viewer**: `fastapi` + `uvicorn` single-page dashboard with PDF preview & receipt upload

*No LangChain, no vector databases, no Docker required for local execution, no React bloat.*

---

## 3. Project Structure

```text
nexaops/
├── README.md                  # Project overview, setup, and demo guide
├── requirements.txt           # Minimal dependencies
├── .env.example               # Config template (LLM provider, threshold, etc.)
├── main.py                    # CLI entry point
│
├── agent/
│   ├── controller.py          # The core loop (Plan -> Validate -> Execute -> Observe -> Verify)
│   ├── policy.py              # Deterministic guardrails (Allowlist, $10k approval, verification check)
│   ├── state.py               # TaskState model (goal, steps, working data, approvals, evidence)
│   ├── llm.py                 # Provider adapter (Fake deterministic mock, Gemini, OpenAI)
│   ├── prompts.py             # System prompt and dynamic step prompt builder
│   └── events.py              # Real-time console printer and SQLite audit logger
│
├── tools/
│   ├── registry.py            # Central tool catalog with schemas and metadata (read_only, retryable)
│   └── invoice_tools.py       # The 6 core tools (+ 1 generalization tool)
│
├── env/
│   ├── finance_db.py          # SQLite store for finance records and audit events
│   └── seed.py                # Initializes DB and creates 6 sample invoice PDFs
│
├── data/invoices/             # Sample PDF invoices (ABC, Delta, XYZ, Acme, InnoTech)
├── web/                       # Optional FastAPI single-page task viewer
├── tests/
│   └── test_agent.py          # 12 deterministic test scenarios covering all edge cases
└── docs/
    ├── ARCHITECTURE.md        # ASCII component and data flow diagrams
    ├── DECISIONS.md           # Why no LangChain, why SQLite, why deterministic policy
    ├── LIMITATIONS.md         # Current limitations & future roadmap
    └── DEMO_SCRIPT.md         # 3-5 minute step-by-step interview walkthrough
```

---

## 4. Quickstart Setup

### Step 1: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 2: Initialize Database and Sample Invoices
```bash
python env/seed.py
```
This generates the SQLite database (`data/finance.db`) and 6 sample invoice PDFs in `data/invoices/`.

---

## 5. Demo Walkthrough Commands

### Scenario A: The Happy Path (Under Approval Threshold)
```bash
python main.py "Process the latest invoice from ABC Technologies"
```
* **What happens**: Finds `INV-ABC-002.pdf` (latest date 2026-10-01), extracts data, verifies not a duplicate, creates record ($4,850.00 < $10,000 threshold), verifies DB record independently, and returns evidence.

### Scenario B: Human-in-the-Loop Approval Required
```bash
python main.py "Process the latest invoice from Delta Systems"
```
* **What happens**: Delta Systems' invoice is $75,000.00. The policy engine blocks automatic creation and prompts the user in the CLI: `Approve this invoice? (y/n):`. Type `y` to approve and complete, or `n` to safely reject without saving to the DB.

### Scenario C: Transient Timeout with Automatic Retry
```bash
python main.py --fail-mode timeout "Process the latest invoice from ABC Technologies"
```
* **What happens**: The finance API returns a simulated 504 gateway timeout. The controller observes the transient error, waits with backoff, automatically retries, and succeeds.

### Scenario D: Duplicate Invoice Prevention
```bash
python main.py "Process the latest invoice from XYZ Solutions"
```
* **What happens**: `INV-XYZ-102` was already seeded in the database. The agent discovers the record, prevents creating a duplicate entry, verifies the existing record, and reports success.

### Scenario E: Missing Required Data (No Fabrication)
```bash
python main.py "Process the latest invoice from Acme Corp"
```
* **What happens**: `INV-ACME-404.pdf` lacks a Due Date. The agent refuses to invent or hallucinate data, pauses safely, and outputs `TASK NEEDS_INPUT`.

### Scenario F: Workflow Generalization (Second Business Flow)
```bash
python main.py "List all invoices from ABC Technologies"
```
* **What happens**: Without changing a single line in `agent/controller.py`, the agent adapts to an entirely different business request and calls `list_invoices`.

### Scenario G: Upload Custom Receipts & PDF Invoices (Web Console)
1. Start the web console:
```bash
python -m web.app
```
2. Open **`http://localhost:8000`** in your browser.
3. Click the **"📤 Upload Receipt / PDF"** button (in Task Controller or Vault tab).
4. Drag & drop or select **any PDF invoice or receipt image** (PNG, JPG, JPEG, WEBP).
5. The system automatically inspects the file, converts receipt images into standardized PDFs with metadata banners, catalogs them in `data/invoices/`, and offers an instant **"⚡ Upload & Dispatch Agent"** one-click workflow!

---

## 6. Running the Test Suite

Run all 17 deterministic test scenarios offline without an API key:
```bash
pytest tests/ -v
```

Expected output:
```text
tests/test_agent.py::test_happy_path PASSED
tests/test_agent.py::test_approval_granted PASSED
tests/test_agent.py::test_approval_rejected PASSED
tests/test_agent.py::test_duplicate_invoice PASSED
tests/test_agent.py::test_timeout_retry PASSED
tests/test_agent.py::test_missing_data PASSED
tests/test_agent.py::test_verification_mismatch PASSED
tests/test_agent.py::test_policy_forbidden_tool PASSED
tests/test_agent.py::test_policy_finish_before_verification PASSED
tests/test_agent.py::test_step_cap_enforcement PASSED
tests/test_agent.py::test_prompt_injection_immunity PASSED
tests/test_agent.py::test_generalization_list_invoices PASSED
============================== 12 passed in 2.13s ==============================
```

---

## 7. Optional: Single-Page Web Viewer

To inspect past tasks, recorded invoices, and audit event logs in a visual browser dashboard:
```bash
python -m web.app
```
Then open `http://localhost:8000` in your browser.
