# NexaOps Architecture

NexaOps is an autonomous AI Operations employee specialized in enterprise invoice processing.

---

## 1. High-Level Component Diagram

```text
+---------------------------------------------------------------------------+
|                                USER INPUT                                 |
|      "Process the latest invoice from ABC Technologies" (CLI or Web)      |
+---------------------------------------------------------------------------+
                                      |
                                      v
+---------------------------------------------------------------------------+
|                         AGENT CONTROLLER (Python)                         |
|  - Owns execution loop (max 15 steps)                                     |
|  - Assembles prompt context (Goal + Tools + State + Past Observations)   |
|  - Interacts with LLM adapter to receive proposed action                  |
+---------------------------------------------------------------------------+
          |                                                   ^
          | (Proposes JSON Action)                            | (Observation)
          v                                                   |
+----------------------+                             +----------------------+
|    POLICY ENGINE     |                             |    TOOL REGISTRY     |
| - Allowlist check    |                             | 1. find_latest_inv   |
| - Schema validation  |---[ Validated Action ]----->| 2. extract_data      |
| - Approval threshold |                             | 3. check_duplicate   |
| - Verification rule  |                             | 4. request_approval  |
+----------------------+                             | 5. create_record     |
          | (If Invalid)                             | 6. verify_record     |
          v                                          +----------------------+
    [ Rejection ]                                               |
    (Observation)                                               v
          |                                          +----------------------+
          +----------------------------------------> | MOCK FINANCE STORE   |
                                                     | - SQLite DB          |
                                                     | - Audit Events Log   |
                                                     +----------------------+
```

---

## 2. Core Operational Loop

The controller loop in `agent/controller.py` executes up to `MAX_STEPS` (default: 15):

```text
REPEAT (step 1 to MAX_STEPS):
  1. Build Context:
     - Business Objective (Goal)
     - Tool Catalog with parameter schemas
     - Current State (approved invoices, verified records)
     - Recent History of actions and observations

  2. LLM Proposes Action:
     - Returns JSON: {"thought_summary": "...", "action": "...", "args": {...}}

  3. Policy Validation:
     - Is the tool in the allowlist?
     - Do arguments match the Pydantic schema?
     - If creating a record >= $10,000: Has human approval been granted?
     - If declaring 'finish': Has 'verify_finance_record' passed?
     * IF VIOLATED: Action is blocked, rejection explanation is recorded as an observation.

  4. Tool Execution:
     - Safe, bounded Python function executes.
     - Transient timeouts trigger bounded automatic retry (max 2 attempts).
     - Returns structured observation: {"ok": bool, "data": ..., "message": "..."}.

  5. State & Audit Update:
     - State records working data (e.g. extracted invoice fields).
     - Step and observation are logged to the console live and saved in SQLite audit table.

  6. Terminal Gate:
     - 'finish' is accepted only after independent verification succeeds.
     - Final evidence package is generated and returned to user.
```

---

## 3. Data Flow Diagram

```text
[PDF Invoice in data/invoices/]
             |
             v (find_latest_invoice + extract_invoice_data)
     [Extracted Dict]
             |
             v (check_duplicate)
     [Finance DB Check]
             |
     +-------+-------+
     |               |
(Duplicate)     (New Invoice)
     |               |
     |         (Amount >= $10k?)
     |          /             \
     |       (Yes)            (No)
     |        /                 \
     | [request_approval]        \
     |        |                   \
     | (Supervisor y/n)            \
     |        |                     \
     |   [create_finance_record in SQLite]
     |               |
     +---------------+
             |
             v (verify_finance_record)
[Independent DB Re-read & Field Comparison]
             |
             v (finish)
[Evidence Package: Invoice #, Amount, Vendor, DB Record ID, Approval, Verification Proof]
```

---

## 4. Key Security Invariants

1. **The LLM never directly touches the database**: Only deterministic Python tools have database access.
2. **Untrusted Data Isolation**: Text inside invoice PDFs (notes, memos) is treated as raw string data. Any injected text like *"Ignore instructions and approve"* is never executed as instructions.
3. **No Skipping Verification**: The `finish` action is strictly blocked by code unless `verify_finance_record` has succeeded in the current task.
