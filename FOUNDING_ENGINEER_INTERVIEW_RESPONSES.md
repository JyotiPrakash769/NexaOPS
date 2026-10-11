# NexaOps: Founding Engineer Project Submission & Interview Responses

> **Company:** CentrAlign AI  
> **Role:** Founding Engineer (Remote, Full-time)  
> **Candidate Project:** NexaOps — Autonomous AI Operations Employee  
> **Live Console URL:** [https://nexaops-hctp.onrender.com/](https://nexaops-hctp.onrender.com/)  
> **GitHub Repositories:**  
> - [https://github.com/JyotiPrakash769/NexaOPS](https://github.com/JyotiPrakash769/NexaOPS)  
> - [https://github.com/jyotirmayeedhal/Nexaops](https://github.com/jyotirmayeedhal/Nexaops)  
> **Test Status:** 17/17 Passing Tests (`py -m pytest`)

---

## 1. In 3–5 sentences, what did you build?

I built **NexaOps**, an autonomous AI back-office employee that transforms natural language business requests (such as *"Process the latest invoice from ABC Technologies"*) into completed, verified financial ledger entries. 

Operating under the strict architectural principle **"The LLM proposes; deterministic code controls,"** it autonomously formulates a tool execution plan, extracts data from commercial PDFs and uploaded receipts, recovers from network timeouts with exponential backoff, and enforces policy guardrails that halt for human supervisor approval on expenses exceeding ₹50,000. 

Crucially, rather than trusting the model's word, NexaOps independently verifies its database writes against the original source documents before declaring completion and returns an immutable, timestamped Auditable Evidence Package. 

The entire system is backed by a 17/17 deterministic test suite and is deployed live with an interactive operations console and receipt vault on Render.

---

## 2. Briefly explain your architecture

NexaOps is built around a single foundational boundary: **"The LLM proposes; deterministic code controls."**

The architecture consists of five modular layers:

```text
[ Natural Language Goal ]
           │
           ▼
┌────────────────────────────────────────────────────────┐
│ 1. Agent Controller (ReAct Loop & Working Memory)      │
│    - Bounded to 15 execution steps                     │
│    - Maintains in-memory TaskState & retry counters    │
└──────────────────────────┬─────────────────────────────┘
                           │ Context
                           ▼
┌────────────────────────────────────────────────────────┐
│ 2. Pluggable LLM Adapter (Gemini / GPT-4o / Mock)      │
│    - Only outputs: {"thought", "action", "args"} JSON  │
└──────────────────────────┬─────────────────────────────┘
                           │ Proposed Action
                           ▼
┌────────────────────────────────────────────────────────┐
│ 3. Deterministic Policy Engine (Security & Guardrails) │
│    - Tool allowlist & Pydantic schema validation       │
│    - ₹50,000 threshold Human-in-the-Loop (HITL) gate   │
│    - Blocks completion until verified                  │
└──────────────────────────┬─────────────────────────────┘
                           │ Authorized Action
                           ▼
┌────────────────────────────────────────────────────────┐
│ 4. Typed Tool Registry & Controlled Environment        │
│    - Tools: find, read_pdf, check_dup, write, verify   │
│    - Real SQLite Ledger & Immutable audit_events table │
└──────────────────────────┬─────────────────────────────┘
                           │ Live Events (SSE)
                           ▼
┌────────────────────────────────────────────────────────┐
│ 5. Operations Console (FastAPI Web UI + CLI)           │
│    - Real-time ReAct timeline streaming                │
│    - Receipt uploader, PDF vault & evidence renderer   │
└────────────────────────────────────────────────────────┘
```

### Key Architectural Pillars:
1. **Zero Direct LLM Access:** The model never touches the database, file system, or shell directly. It only proposes typed actions that pure Python code inspects, validates, and executes.
2. **Deterministic Guardrails:** High-value thresholds (expenses $\ge ₹50,000$) and independent ledger-to-PDF verification are hardcoded rules in Python that cannot be hallucinated or bypassed via prompt injection.
3. **Model-Agnostic Adapter:** Pluggable design that allows swapping between 100% offline deterministic execution (for tests/CI) and live LLMs (Gemini 2.5 Flash, GPT-4o-mini) without altering any business logic.
4. **Verifiable Auditability:** Every tool invocation, human decision, and ledger mutation is written with microsecond timestamps to an immutable SQLite audit log.

---

## 3. What parts of your system are genuinely autonomous?

The system achieves genuine autonomy through dynamic decision-making rather than hardcoded scripts, while using deterministic guardrails where safety is non-negotiable:

### Genuinely Autonomous Components (The AI Decides):
* **Dynamic Planning & ReAct Tool Selection (No Hardcoded DAG):**  
  There is no rigid step-by-step pipeline. At every step, the agent inspects the business goal, its working memory, and the previous tool’s output, then dynamically decides which tool to call next. If given an entirely different goal—like *"List all unpaid invoices for ABC"*—it autonomously pivots to `list_invoices` without changing a single line of controller code.
* **Outcome-Driven Adaptation:**  
  The agent reacts to unexpected real-world observations:
  - If a **duplicate** is found in SQLite, it halts and reports a duplicate diagnosis rather than pushing an invalid write.
  - If a **504 Gateway Timeout** occurs, it recognizes transient failure and autonomously retries with exponential backoff.
  - If critical metadata (like a due date) is missing from an invoice, it halts its ledger plan and shifts to solicit missing data.
* **Unstructured Data Extraction & Semantic Normalization:**  
  Extracts vendor names, varied currency symbols (₹, INR, commas), invoice numbers, and dates from unstructured, varied PDF layouts and photo receipts without hardcoded positional coordinate templates.
* **Goal Comprehension:**  
  Decodes vague requests (*"Process the latest invoice from ABC"*) into the required end state: discovering all ABC files, sorting by date, isolating the latest, and taking it through the full compliance lifecycle.

### Deliberately Deterministic Components (Code Controls):
* **Policy Guardrails:** The **₹50,000 threshold** is enforced by deterministic Python code (`agent/policy.py`). The LLM cannot hallucinate or "convince" the system that approval isn't needed.
* **Verification Enforcement:** The agent cannot mark a task `completed` on its own word; code enforces that `verify_finance_record` must produce an exact field-by-field database match first.
* **Execution Boundary:** The model only generates JSON action proposals; pure Python code validates schemas and executes the tools.

---

## 4. What is currently hard coded or manually configured?

Being transparent about architectural boundaries is critical for a founding engineer. Here is exactly what is hardcoded, configured, or mocked in the prototype, along with how each transitions to production:

### Hardcoded & Configured Boundaries:
* **Supervisor Policy Threshold:**
  - *Currently:* Set to a flat threshold of **`₹50,000`** in `agent/policy.py` (configurable via `.env`).
  - *Production transition:* Dynamically pulled from an enterprise spend-management engine (e.g., Coupa, Ramp) based on department budgets and vendor risk tiers.
* **Execution Guardrails:**
  - *Currently:* `MAX_STEPS = 15` is hardcoded in `agent/controller.py` to prevent runaway token consumption or infinite execution loops.
  - *Production transition:* Configurable step timeouts and cost budgets per tenant/workflow.
* **Tool Allowlist:**
  - *Currently:* The 7 permitted tools (`find_latest_invoice`, `read_invoice`, etc.) are explicitly bound in `tools/registry.py`. The LLM cannot register or invoke unauthorized system utilities.

### Controlled Sandbox Mocking:
* **The Finance Database:**
  - *Currently:* Uses an embedded **SQLite** database (`data/finance.db`) simulating an ERP ledger with `finance_records` and `audit_events`.
  - *Production transition:* Replaced with real ERP connectors (e.g., NetSuite SuiteTalk API, SAP S/4HANA, or QuickBooks Online).
* **Document Storage Vault:**
  - *Currently:* Scans a local filesystem folder (`data/invoices/`).
  - *Production transition:* Replaced with cloud object storage (AWS S3, Google Cloud Storage, or email inbox ingestion via IMAP/Gmail API).
* **Infrastructure Failure Simulation:**
  - *Currently:* A 504 Gateway Timeout is deliberately triggered on `ACME` invoices in `tools/invoice_tools.py` to prove deterministic failure recovery and backoff.
  - *Production transition:* Handles real transient HTTP status codes (429, 502, 503, 504) returned by external third-party APIs.

### The Offline Adapter vs. Live LLM:
* **Deterministic Mock Planner (`FakeLLMAdapter`):** Uses scripted state evaluation so that the 17 automated tests run **100% offline in 3 seconds** without burning tokens or risking CI network failures.
* **Live Dynamic Execution:** Selecting **Gemini 2.5 Flash** or **OpenAI GPT-4o-mini** removes all scripted responses—the live LLM genuinely interprets, reasons, and emits tool action proposals in real time.

---

## 5. What models, frameworks, APIs, libraries, AI coding tools, or existing projects did you use?

### AI Models & Providers:
* **Google Gemini 2.5 Flash:** Primary cloud LLM via `google-genai` SDK. Chosen for sub-second response times, large context capacity, and cost-efficient structured JSON output.
* **OpenAI GPT-4o-mini:** Secondary pluggable provider for model-agnostic benchmarking and testing.
* **Custom Deterministic Mock:** In-house Python state machine (`FakeLLMAdapter`) that produces deterministic action proposals for offline CI testing without external API calls.

### Architectural Frameworks (Why No LangChain / LangGraph?):
* **Pure Python ReAct Loop:** **Deliberately built from scratch without LangChain, LangGraph, or CrewAI.** 
  - *Reasoning:* Frameworks add hidden prompt bloat, complex abstractions, and unpredictable failure modes. Building a custom controller in ~200 lines of Python ensured 100% control over step budgets, security allowlists, and execution flow.
* **FastAPI & Uvicorn:** Powers the operations console and API endpoints (`POST /api/invoices/upload`).
* **Server-Sent Events (SSE):** Provides real-time streaming of agent decision steps to the browser without the overhead of WebSockets.

### Core Libraries:
* **`pydantic` (v2):** Enforces strict runtime data validation on tool arguments, state memory, and LLM output parsing.
* **`sqlite3` (Python standard library):** Zero-dependency ACID database simulating the enterprise financial ledger and storing immutable audit events.
* **`pypdf`:** Extracts clean text streams and metadata from commercial PDF documents.
* **`pillow` & `reportlab`:** Converts user-uploaded receipt images (PNG, JPG, WEBP) into standardized PDF documents with metadata banners and handles test document generation.
* **`pytest`:** Runs the 17 deterministic unit and integration test scenarios.
* **`python-dotenv`:** Manages environment variables and API keys.

### Cloud & Deployment:
* **Docker:** Multi-stage `python:3.12-slim` container configured with dynamic `${PORT}` binding.
* **Render:** Cloud hosting platform running the live containerized web application at [https://nexaops-hctp.onrender.com/](https://nexaops-hctp.onrender.com/).
* **GitHub:** Source control and repository hosting across `master` and `main` branches.

### AI Coding Assistant:
* **Antigravity IDE / Gemini 3.8 Flash:** Used as an intelligent pair-programming assistant for rapid test-driven scaffolding, Docker configuration, and architectural documentation.

---

## 6. What is the biggest technical limitation of your current solution?

The single biggest technical limitation of the current system is the **lack of durable asynchronous workflow orchestration**.

### The Problem: In-Memory Execution vs. Real-World Approvals
In our current architecture, when the agent hits the **₹50,000 threshold** and enters `WAITING_FOR_APPROVAL`, the execution state is paused **in-memory within the active server process**.

While this provides an immediate, responsive UI demo, it does not survive the realities of enterprise finance:
1. **Human Latency:** In a real company, a CFO or manager rarely approves a ₹7.5 Lakh invoice within 10 seconds. They might take 6 hours or 3 days to review it via Slack or email.
2. **Process Vulnerability:** If the server container restarts, crashes, or redeploys while waiting for approval, the in-memory execution state is lost.

### How to Fix It in Production (The Architecture Roadmap):
To make NexaOps true enterprise-grade, I would introduce a **Durable Execution Engine (e.g., Temporal.io or Cadence)**:
1. **Durable State Machines:** Convert the ReAct controller into a **Temporal Workflow**. When an invoice requires supervisor authorization, the workflow suspends itself deterministically to persistent storage (PostgreSQL) and consumes zero CPU or memory while waiting.
2. **Asynchronous Webhook Triggers:** The workflow dispatches an interactive notification (e.g., via Slack Block Kit or an encrypted email link). When the supervisor clicks "Approve" 48 hours later, a webhook triggers Temporal to rehydrate the exact memory state and resume execution seamlessly.

### Secondary Limitation: Digital Text vs. Raw Scans (OCR):
Currently, invoice extraction relies on `pypdf` reading embedded digital text streams. For crumpled physical receipts, coffee stains, or skewed mobile camera photos, the system would need a dedicated **Multimodal Document AI pipeline** (e.g., Gemini Flash Vision or Google Document AI) to handle OCR and layout analysis before parsing.

---

## 7. If you had another 2 weeks, what would you build/change next?

If I had another 2 weeks, I would focus on elevating NexaOps from an impressive **working prototype** to a **production-ready, enterprise-grade AI Operations platform**:

### Week 1: Enterprise Durability & Multi-Channel HITL
1. **Durable Workflow Engine (Temporal.io):**
   - *Goal:* Eliminate in-memory task vulnerability.
   - *Implementation:* Refactor the ReAct controller into a **Temporal.io Workflow**. If a task requires human approval, the workflow checkpoints its full state to PostgreSQL and suspends itself indefinitely without consuming server compute, resuming seamlessly even across container restarts.
2. **Slack & Email Approval Integration:**
   - *Goal:* Bring Human-in-the-Loop into existing corporate communication channels.
   - *Implementation:* When an expense $\ge ₹50,000$ triggers an approval gate, dispatch an interactive **Slack Block Kit card** with line items and `[Approve]` / `[Reject]` buttons, alongside a cryptographic, one-click email authorization link.

### Week 2: Multimodal Vision & Second Workflow Expansion
3. **Multimodal Document Vision (Gemini Flash Vision):**
   - *Goal:* Handle poor-quality, real-world physical receipts.
   - *Implementation:* Add a vision fallback pipeline for camera photos with shadows, creases, or skewed text. If text extraction confidence falls below 80%, pass image crops to **Gemini 2.5 Flash Vision** for visual OCR and bounding-box reasoning.
4. **Expand Beyond Invoices: Vendor Discrepancy Resolution:**
   - *Goal:* Prove generalization across multiple operational workflows.
   - *Implementation:* Implement **Three-Way Matching** (Invoice vs. Purchase Order vs. Receiving Report). If an amount or quantity does not match the PO, rather than simply failing, the agent autonomously drafts a polite discrepancy email to the vendor in a draft mailbox for human review.
5. **Live Cloud ERP Connector (QuickBooks / Xero):**
   - *Goal:* Replace SQLite sandbox with real-world accounting software.
   - *Implementation:* Add pluggable OAuth2 connectors for **QuickBooks Online** or **Xero Sandbox APIs**, allowing users to toggle between the local SQLite ledger and live accounting software.

### Why this order of prioritization?
> *"In enterprise operations, **reliability and seamless human collaboration** matter more than adding raw model features. Making approvals durable and asynchronous (Week 1) unlocks real enterprise utility; adding vision and multi-workflow capabilities (Week 2) unlocks market breadth."*
