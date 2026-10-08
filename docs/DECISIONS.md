# NexaOps - Architectural Decisions & Rationale

This document explains the key engineering choices made while building NexaOps.

---

### 1. Why No LangChain or Complex Agent Frameworks?

* **Total Predictability**: LangChain and similar frameworks introduce hidden abstractions, prompt monkey-patching, and complex graph runtimes that obscure the actual execution flow.
* **Explainability**: In a production environment or technical interview, every single line of code in `agent/controller.py` can be read, traced, and explained in 2 minutes without relying on framework magic.
* **Minimal Dependencies**: The core agent relies strictly on standard Python and Pydantic. It is lightweight, fast, and does not break with upstream framework version bumps.

---

### 2. Why a Deterministic Policy Layer in Code?

* **The LLM Proposes; Deterministic Code Controls**: LLMs are probabilistic reasoners. If an LLM is asked to decide *"Is this invoice above the approval limit?"*, it might hallucinate, miscalculate, or be influenced by adversarial prompt injections.
* **Hard Enforcement**: `agent/policy.py` checks policies in pure Python:
  - If `amount >= $10,000`, the action `create_finance_record` is blocked unless human approval was already recorded in state.
  - If `finish` is attempted before `verify_finance_record` succeeds, it is blocked.
* The model cannot bypass these rules because the controller loop strictly interrogates the policy layer before calling any tool.

---

### 3. Why SQLite for the Mock Finance System?

* **Zero External Infrastructure**: SQLite is included in the Python standard library (`sqlite3`). A reviewer or evaluator can clone the repo and run it immediately without starting Docker containers or provisioning cloud databases.
* **ACID Transactions & Real SQL**: Unlike in-memory Python dictionaries, SQLite enforces real database schemas, unique constraints (duplicate prevention), and persistent storage.
* **Auditability**: All agent step executions are written directly into an `audit_events` table for permanent compliance tracking.

---

### 4. Why Is Verification Independent from the Write Action?

* **Trust but Verify**: When `create_finance_record` runs, receiving an "OK" from the write API only means the request was accepted. It does not prove that the database stored the exact amounts and dates accurately without truncation or corruption.
* **Separate Tool (`verify_finance_record`)**:
  1. The agent must make a separate read-only query to the database using the invoice number.
  2. Code compares every critical field (vendor name, total amount, due date) against the original extracted data.
  3. Only when all fields match does the state record the invoice as verified.
* If a simulated corruption occurs, verification fails and prevents the task from falsely reporting completion.
