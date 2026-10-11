# NexaOps: Comprehensive Project Context & Discussion Archive

> **Date**: October 2026  
> **Project**: NexaOps — Autonomous AI Operations Employee  
> **Context**: CentrAlign AI Founding Engineer Assignment  
> **Status**: Fully Implemented, Tested (17/17 passing tests), Running on `http://localhost:8000`

---

## 1. Executive Summary & Core Identity

### What is NexaOps?
**NexaOps** is an autonomous AI Operations worker that executes corporate back-office workflows. Rather than functioning as a conversational chatbot, NexaOps acts as an **autonomous employee**:
1. It accepts high-level business objectives in natural language (e.g., *"Process the latest invoice from ABC Technologies"*).
2. It autonomously determines the required plan and selects typed, bounded tools.
3. It extracts data from unstructured commercial PDF documents and receipt images.
4. It observes real execution outputs against a controlled corporate finance environment.
5. It handles infrastructure failures (e.g., simulated 504 timeouts) through automated classification and retry backoff.
6. It enforces non-negotiable enterprise policies, halting for human supervisor approval on high-value transactions.
7. It independently verifies ledger writes against source documents before declaring completion.
8. It compiles an immutable, auditable evidence package for human reviewers.

### Core Architectural Contract
$$\text{\bf "The LLM proposes; deterministic code controls."}$$
- The LLM never has direct access to the database, shell, or file write permissions.
- The LLM only proposes structured JSON action proposals. Pure Python code inspects, authorizes, and executes tools.

---

## 2. Simple Explanation (Hinglish & Layman Guide)

### Problem (Yeh Kyu Banaya Gaya?)
Badi companies mein roz hazaron bills aate hain:
- **Human Problem:** Accountants ghanton baith kar ek-ek PDF kholte hain, manually software mein type karte hain, aur galti se double payment hone ka risk rehta hai.
- **Aam AI Problem:** Standard chatbots (jaise ChatGPT) ko directly kaam do toh woh missing dates ya amounts apne mann se jhooth bol dete hain (hallucination), ya prompt injection ke fraud mein fas sakte hain.

### Solution (NexaOps Kaise Kaam Karta Hai?)
User sirf bolta hai: *"ABC Technologies ka latest bill process karo."*

Uske baad NexaOps khud yeh 7 steps execute karta hai:
1. **Find File:** Folder scan karke sabse naya bill dhoondhta hai.
2. **Read Document:** PDF/Receipt read karke Vendor, Invoice Number, Amount aur Due Date extract karta hai.
3. **Double-Entry Check:** Database check karta hai ki yeh bill pehle se paid toh nahi hai na.
4. **Boss ki Permission (Approval Gate):** Agar bill ₹50,000 se bada hai (e.g. ₹7,50,000), toh AI paise nahi bhejta. Screen par ruk kar human supervisor se approval mangta hai.
5. **Ledger Write:** Approval ke baad finance database mein record insert karta hai.
6. **Double Check (Independent Verification):** Database se dobara record nikal kar original bill se 100% cross-check karta hai.
7. **Proof Return:** Audit evidence package taiyaar karke screen par dikha deta hai.

---

## 3. CentrAlign AI Founding Engineer Objectives Mapping

| Objective | Requirement | NexaOps Implementation | Status |
| :--- | :--- | :--- | :---: |
| **O1. Understand Intended Outcome** | Natural language goals ko decode karna. | Short prompt *"Process latest invoice from ABC"* se vendor decode karke latest date wali PDF pick karta hai. | ✅ Pass |
| **O2. Plan the Work** | Goal ko dynamic actions mein break karna. | ReAct planning loop (`agent/controller.py`) dynamically plan aur tool selection karta hai. | ✅ Pass |
| **O3. Execute with Real Tools** | Real sandbox tools run karna (no mocks). | Disk se real PDF files read karta hai, real SQLite queries execute karta hai. | ✅ Pass |
| **O4. Observe and Adapt** | Result dekh kar adapt karna. | Duplicate milne par abort karta hai; missing due date par user se input mangta hai; high-value par approval mangta hai. | ✅ Pass |
| **O5. Recover from Failures** | Errors ko retry karna. | 504 Gateway Timeout aane par automated exponential retry backoff karta hai. 15-step hard execution limit. | ✅ Pass |
| **O6. Maintain State & Context** | Working memory manage karna. | `AgentState` in-memory memory manage karta hai aur SQLite `audit_events` mein har action log hota hai. | ✅ Pass |
| **O7. Human-in-the-Loop** | Sensitive steps par human input. | ₹50,000 threshold par `WAITING_FOR_APPROVAL` modal; missing field par clarification form. | ✅ Pass |
| **O8. Verify Outcome** | Independent validation of work. | `verify_finance_record` tool database ko dobara read karke match karta hai. Verification ke bina `finish` blocked hai. | ✅ Pass |
| **O9. Return Evidence** | Auditable proof package. | Full timeline, match confirmations, timestamps, aur SQLite compliance audit trail. | ✅ Pass |

---

## 4. Newly Added Feature: Receipt & PDF File Uploader

### Problem Addressed:
Users wanted the ability to upload their **own custom receipts (images) and PDF invoices** directly into the console, rather than relying only on pre-seeded demo files.

### Implementation Details:
1. **Frontend Dropzone & Modal (`#uploadModal`)**:
   - Modern drag & drop UI with file selection.
   - Accepts `.pdf`, `.png`, `.jpg`, `.jpeg`, `.webp`.
   - Dynamic file preview and size calculation.
   - Smart metadata inference (guesses Vendor and Amount from filename).
   - "Save to Vault" and "⚡ Upload & Dispatch Agent Immediately" buttons.

2. **Backend Upload Endpoint (`POST /api/invoices/upload`)**:
   - Base64 payload decoding (zero dependency on external `python-multipart`).
   - If PDF: Saves directly to `data/invoices/<filename>.pdf`.
   - If Receipt Image (PNG/JPG): Uses **Pillow + ReportLab** to convert the image into a standardized commercial expense PDF with metadata headers (`Vendor:`, `Invoice Number:`, `Total Amount:`, `Due Date:`) and draws the receipt image proportionally.
   - Auto-extracts fields using `tools/invoice_tools.py` and returns structured summary.

3. **Tool & Agent Generalization**:
   - `find_latest_invoice` updated to match vendor names across both PDF text streams and filename stems.
   - `extract_invoice_data` regexes enhanced for receipts (`Merchant:`, `Store:`, `Receipt #:`, `Total Paid:`, etc.).
   - `agent/llm.py` offline adapter supports direct filename targets as well as natural language vendor goals.

4. **Automated Test Coverage**:
   - Test 16: Custom PDF invoice upload & end-to-end agent processing.
   - Test 17: Custom Image receipt upload, automatic PDF conversion & end-to-end agent processing.
   - Total test suite: **17 passed in 3.5s with 0 warnings**.

---

## 5. Practical Usage Guide (How to Run and Test)

### Step 1: Start the Web Console
```powershell
py -m web.app
```
Starts FastAPI server on **`http://localhost:8000`**.

### Step 2: Open in Browser
Visit **`http://localhost:8000`**.

### Step 3: Test Scenarios in UI

#### 1. The 10-Second Happy Path Test:
- Click chip **`✨ Happy Path (ABC)`**.
- Click **`Dispatch Agent`**.
- Watch real-time execution steps on the timeline.
- Observe the green **Auditable Evidence Package** appear on the right.

#### 2. The Approval Gate Test (High-Value Invoices):
- Click chip **`🛡️ Approval Gate (Delta ₹7.5L)`**.
- Click **`Dispatch Agent`**.
- Notice the agent pause before database insertion.
- An interactive **Human Decision Card** appears: click **Approve** to continue or **Reject** to abort safely.

#### 3. Upload Your Own Receipt / PDF:
- Click **`📤 Upload Receipt / PDF`** (available in Presets row or Vault tab).
- Select any receipt image or PDF file.
- Click **`⚡ Upload & Dispatch Agent`**.
- The agent immediately reads your document, runs duplicate checks, inserts the record, and presents the audit evidence!

#### 4. Inspect Audit & Raw Files:
- Click **`📁 Invoice PDF Vault`** tab to preview any PDF in-browser.
- Click **`📊 Database Records`** to inspect the SQLite ledger.
- Click **`📜 Audit Trail`** to search compliance logs.
- Click **`🛡️ Security Suite`** to execute the 9 red-team policy tests with 1 click.

---

## 6. Project File Layout Reference

```text
nexaops/
├── README.md                          # Main project documentation & demo walkthrough
├── MASTER_PROJECT_GUIDE.md            # In-depth architectural guide & interview pitch
├── PROJECT_DISCUSSION_CONTEXT.md      # Complete context archive of all discussions & features
├── requirements.txt                   # Minimal dependencies (FastAPI, pydantic, pypdf, reportlab, pillow)
├── main.py                            # CLI entry point
│
├── agent/
│   ├── controller.py                  # Core ReAct engine (Plan, Execute, Observe, Adapt, Verify)
│   ├── policy.py                      # Deterministic Python guardrails (Approval gate, verification check)
│   ├── state.py                       # TaskState memory & evidence model
│   ├── llm.py                         # Pluggable adapter (Fake offline, Gemini Flash, OpenAI)
│   ├── prompts.py                     # System prompt & dynamic context builder
│   └── events.py                      # Real-time event streaming & SQLite audit logger
│
├── tools/
│   ├── registry.py                    # Tool decorator, Pydantic validator & catalog
│   └── invoice_tools.py               # Invoice & receipt tools (find, extract, duplicate check, ledger, verify)
│
├── env/
│   ├── finance_db.py                  # SQLite database (finance_records & audit_events)
│   └── seed.py                        # Seed script generating sample PDFs & DB records
│
├── data/
│   ├── finance.db                     # Live SQLite database file
│   └── invoices/                      # Storage vault for PDF invoices & uploaded receipts
│
├── web/
│   └── app.py                         # Single-page operations console (SSE, PDF viewer, upload modal)
│
├── tests/
│   └── test_agent.py                  # 17 deterministic unit & integration tests
│
└── docs/
    ├── ARCHITECTURE.md                # Layer diagrams & data flow
    ├── DECISIONS.md                   # Architectural trade-off rationale
    ├── DEMO_SCRIPT.md                 # 5-minute live interview demo script
    └── LIMITATIONS.md                 # Production roadmap & known constraints
```

---

*This document serves as the permanent contextual source of truth for the NexaOps project.*
