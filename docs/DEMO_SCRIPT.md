# NexaOps - 3-5 Minute Interview Demo Script

This script walks through the key capabilities of NexaOps step-by-step.

---

### Step 0: Quick Setup (30 seconds)

Ensure dependencies are installed and database is seeded:
```bash
python env/seed.py
```

---

### Scenario 1: The Happy Path (Under Threshold) — 1 Minute

**Command:**
```bash
python main.py "Process the latest invoice from ABC Technologies"
```

**What to explain to the interviewer:**
1. Notice the agent picks `INV-ABC-002.pdf` (dated 2026-10-01) over the older `INV-ABC-001.pdf` (dated 2026-09-15) based on **actual invoice dates**, not filenames.
2. It extracts the vendor, invoice number, due date, and amount ($4,850.00).
3. It checks for duplicates in SQLite.
4. Because the amount ($4,850.00) is below the $10,000 approval threshold, it automatically creates the record.
5. It runs an **independent verification query** to confirm the data stored matches the source document before declaring completion.
6. Returns an auditable evidence package with exact record IDs and timestamps.

---

### Scenario 2: Human-in-the-Loop Approval — 1 Minute

**Command:**
```bash
python main.py "Process the latest invoice from Delta Systems"
```

**What to explain to the interviewer:**
1. Delta Systems' invoice is for **$75,000.00**.
2. The deterministic policy engine blocks automatic entry because `$75,000 >= $10,000`.
3. The agent pauses execution and displays a prompt: `Approve this invoice? (y/n):`.
4. Type `y` to grant approval.
5. The agent resumes, creates the record, independently verifies it, and outputs the evidence package showing `approved_by_supervisor: True`.

*(Optional test: Re-run and type `n` to demonstrate safe rejection without writing to the database).*

---

### Scenario 3: Transient Gateway Timeout & Automatic Recovery — 1 Minute

**Command:**
```bash
python main.py --fail-mode timeout "Process the latest invoice from ABC Technologies"
```

**What to explain to the interviewer:**
1. The simulated finance API throws a transient `504 Gateway Timeout`.
2. Rather than crashing, the agent classifies the error as `timeout` (marked `retryable` in the tool definition).
3. The controller automatically pauses for a short backoff and retries the action.
4. The retry succeeds, and the task finishes normally.

---

### Scenario 4: Duplicate Invoice Handling — 45 Seconds

**Command:**
```bash
python main.py "Process the latest invoice from XYZ Solutions"
```

**What to explain to the interviewer:**
1. Invoice `INV-XYZ-102` was already recorded in the finance system during database seeding.
2. The agent runs `check_duplicate`, spots the existing record (ID: 1), and adapts.
3. Instead of creating a duplicate or failing, it retrieves the existing record, verifies it, and finishes cleanly with the note: *"No duplicate created."*

---

### Scenario 5: Missing Required Data (Acme Corp) — 30 Seconds

**Command:**
```bash
python main.py "Process the latest invoice from Acme Corp"
```

**What to explain to the interviewer:**
1. `INV-ACME-404.pdf` intentionally omits the Due Date.
2. Rather than hallucinating or fabricating a date, the agent identifies the missing field and halts safely with `TASK NEEDS_INPUT`.

---

### Scenario 6: Workflow Generalization — 30 Seconds

**Command:**
```bash
python main.py "List all invoices from ABC Technologies"
```

**What to explain to the interviewer:**
1. Demonstrates that the controller is not a hard-coded invoice processing script.
2. Without changing a single line in `agent/controller.py`, the agent interprets a completely different business request, calls `list_invoices`, and returns the results.
