# NexaOps - Limitations & Future Roadmap

---

## 1. Current Limitations

1. **Digital PDFs Only (No OCR)**:
   - The invoice extraction tool uses `pypdf` to extract embedded text streams.
   - It handles digital, vector-generated PDFs reliably, but does not currently perform Optical Character Recognition (OCR) on low-quality scanned paper images.

2. **Single-Tenant Local Execution**:
   - The agent operates in a single CLI process or single-instance FastAPI server.
   - It is designed for clean, transparent demonstration rather than distributed, multi-tenant enterprise queues.

3. **Currency Conversion**:
   - Approval thresholds are evaluated as a flat numeric amount (default $10,000 USD).
   - Multi-currency invoices (EUR, GBP, JPY) are recorded with their native currency tag, but dynamic FX conversion against the threshold is not yet implemented.

4. **Synchronous Human Approval**:
   - In CLI mode, the agent pauses synchronously for user input (`y/n`).
   - In production, approvals would typically trigger asynchronous webhooks, email alerts, or Slack interactive buttons.

---

## 2. What I'd Build Next

1. **Document AI / Vision Integration**:
   - Add a fallback vision pipeline (e.g. Gemini 2.5 Flash Vision) for poorly formatted scans, handwriting, and rotated receipts.

2. **Distributed Orchestration with Temporal / Celery**:
   - Move task execution into a durable distributed state machine (like Temporal or Celery + Redis) to support pausing tasks for days while waiting for asynchronous supervisor approvals.

3. **Live ERP Adapters**:
   - Implement real accounting connectors (NetSuite SuiteTalk, QuickBooks Online, SAP S/4HANA REST API) alongside the current SQLite store.

4. **Multi-Factor Supervisor Authentication**:
   - Introduce cryptographic signing or JWT-backed approvals for large payment authorizations exceeding $100,000.
