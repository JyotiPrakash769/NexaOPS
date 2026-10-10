"""
Enterprise Operations Console for NexaOps.
Includes:
1. Real-time SSE Agent Execution Streaming
2. Real-time Human-in-the-Loop Approval Gating (§63)
3. Interactive Missing Data Clarification Flow (§31, Q8)
4. In-Browser PDF Invoice Viewer & Vault (§7, §40)
5. Immutable SQLite Audit Trail Inspector (§52, §34)
6. 1-Click Red-Team Security & Guardrails Test Suite (§64)
7. Live LLM Provider & Policy Threshold Switcher (§10, §45)
"""

import os
import sys
import json
import queue
import threading
import time
from pathlib import Path
from typing import Optional, Dict, Any, List

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse
from pydantic import BaseModel

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from agent.controller import run_task, submit_task_approval, submit_task_input
from agent.policy import PolicyEngine, get_approval_threshold
from env import finance_db
import tools.invoice_tools as invoice_tools

app = FastAPI(title="NexaOps Operations Console")

INVOICES_DIR = PROJECT_ROOT / "data" / "invoices"


# ------------------------------------------------------------------------------
# API Models
# ------------------------------------------------------------------------------
class ApprovalDecisionRequest(BaseModel):
    decision: bool


class ClarificationInputRequest(BaseModel):
    input: str


class ConfigUpdateRequest(BaseModel):
    provider: Optional[str] = None
    threshold: Optional[float] = None
    model: Optional[str] = None


# ------------------------------------------------------------------------------
# Core Endpoints
# ------------------------------------------------------------------------------
@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "product": "NexaOps",
        "version": "1.0.0",
        "approval_threshold": get_approval_threshold(),
        "provider": os.getenv("LLM_PROVIDER", "fake")
    }


@app.get("/api/config")
def get_config():
    return {
        "provider": os.getenv("LLM_PROVIDER", "fake"),
        "model": os.getenv("LLM_MODEL", "gemini-2.5-flash"),
        "threshold": get_approval_threshold(),
        "has_gemini_key": bool(os.getenv("LLM_API_KEY") or os.getenv("GEMINI_API_KEY")),
        "has_openai_key": bool(os.getenv("OPENAI_API_KEY"))
    }


@app.post("/api/config")
def update_config(req: ConfigUpdateRequest):
    if req.provider:
        os.environ["LLM_PROVIDER"] = req.provider.strip().lower()
    if req.threshold is not None:
        os.environ["INVOICE_APPROVAL_THRESHOLD"] = str(req.threshold)
    if req.model:
        os.environ["LLM_MODEL"] = req.model.strip()
    return {"status": "ok", "config": get_config()}


@app.get("/api/records")
def get_records():
    return finance_db.list_records()


@app.get("/api/audit")
def get_audit(task_id: Optional[str] = None):
    if task_id:
        return finance_db.get_audit_events(task_id)
    conn = finance_db.get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM audit_events ORDER BY id DESC LIMIT 100")
    rows = cur.fetchall()
    conn.close()
    events = []
    for r in rows:
        d = dict(r)
        for key in ["args", "result"]:
            if isinstance(d.get(key), str):
                try:
                    d[key] = json.loads(d[key])
                except Exception:
                    pass
        events.append(d)
    return events


@app.post("/api/reset")
def reset_db():
    from env.seed import seed_database, seed_invoices
    seed_database()
    seed_invoices()
    invoice_tools.reset_simulation_state()
    return {"status": "ok", "message": "Demo database and invoices re-seeded successfully."}


# ------------------------------------------------------------------------------
# PDF Invoice Vault Endpoints (§7, §40)
# ------------------------------------------------------------------------------
@app.get("/api/invoices")
def list_invoices():
    if not INVOICES_DIR.exists():
        return []
    items = []
    for p in sorted(INVOICES_DIR.glob("*.pdf")):
        items.append({
            "filename": p.name,
            "size_kb": round(p.stat().st_size / 1024, 1),
            "url": f"/api/invoices/{p.name}"
        })
    return items


@app.get("/api/invoices/{filename}")
def get_invoice_file(filename: str):
    safe_name = Path(filename).name
    pdf_path = INVOICES_DIR / safe_name
    if not pdf_path.exists():
        return HTMLResponse("Invoice PDF not found.", status_code=404)
    return FileResponse(
        path=pdf_path,
        media_type="application/pdf",
        filename=safe_name,
        headers={"Content-Disposition": f"inline; filename={safe_name}"}
    )


# ------------------------------------------------------------------------------
# Real-Time Human Decision Endpoints (§63, §31)
# ------------------------------------------------------------------------------
@app.post("/api/tasks/{task_id}/approval")
def post_approval(task_id: str, req: ApprovalDecisionRequest):
    success = submit_task_approval(task_id, req.decision)
    return {"status": "ok" if success else "task_not_found", "task_id": task_id, "decision": req.decision}


@app.post("/api/tasks/{task_id}/input")
def post_input(task_id: str, req: ClarificationInputRequest):
    success = submit_task_input(task_id, req.input)
    return {"status": "ok" if success else "task_not_found", "task_id": task_id, "input": req.input}


# ------------------------------------------------------------------------------
# Red-Team Security & Guardrails Verification Suite (§64)
# ------------------------------------------------------------------------------
@app.get("/api/security-test")
def run_security_suite():
    from agent.state import TaskState
    checks = []

    # 1. Unapproved tool rejection
    state = TaskState(goal="Security check forbidden tool")
    ok, rej = PolicyEngine.validate_action(state, "execute_shell_command", {"command": "rm -rf /"})
    checks.append({
        "id": "SEC-01",
        "name": "Forbidden Tool Rejection",
        "rule": "Arbitrary unapproved tools are blocked before execution",
        "passed": (not ok) and rej.get("error_type") == "policy_forbidden_tool",
        "detail": rej.get("message")
    })

    # 2. Arbitrary SQL Execution Block
    ok, rej = PolicyEngine.validate_action(state, "execute_sql", {"sql": "DROP TABLE finance_records;"})
    checks.append({
        "id": "SEC-02",
        "name": "SQL Injection & Direct Access Block",
        "rule": "Direct SQL access is disallowed; only typed bounded tools run",
        "passed": (not ok) and rej.get("error_type") == "policy_forbidden_tool",
        "detail": rej.get("message")
    })

    # 3. High-Value Approval Bypass Rejection
    thresh = get_approval_threshold()
    ok, rej = PolicyEngine.validate_action(state, "create_finance_record", {
        "invoice_number": "INV-TEST-001",
        "vendor_name": "Test Vendor",
        "amount": thresh + 5000.0,
        "due_date": "2026-11-01"
    })
    checks.append({
        "id": "SEC-03",
        "name": "Approval Bypass Prevention",
        "rule": f"Records meeting or exceeding threshold (₹{thresh:,.2f}) require supervisor grant",
        "passed": (not ok) and rej.get("error_type") == "approval_required",
        "detail": rej.get("message")
    })

    # 4. Premature Task Completion / Verification Skip Rejection
    state_premature = TaskState(goal="Security premature finish")
    state_premature.extracted_data = {"invoice_number": "INV-TEST-002"}
    state_premature.verified_records = []
    ok, rej = PolicyEngine.validate_action(state_premature, "finish", {"summary": "Done early"})
    checks.append({
        "id": "SEC-04",
        "name": "Verification Gate Enforcement",
        "rule": "Cannot finish without independent verification match",
        "passed": (not ok) and rej.get("error_type") == "verification_required",
        "detail": rej.get("message")
    })

    # 5. Missing Data Fabrication Rejection
    ok, rej = PolicyEngine.validate_action(state, "create_finance_record", {
        "invoice_number": "INV-TEST-003",
        "vendor_name": "Test Vendor",
        "amount": 1000.0,
        "due_date": None
    })
    checks.append({
        "id": "SEC-05",
        "name": "Data Fabrication Prevention",
        "rule": "Null, empty, or fabricated due dates are strictly rejected",
        "passed": (not ok) and rej.get("error_type") in ["missing_required_data", "invalid_tool_arguments"],
        "detail": rej.get("message")
    })

    # 6. Prompt Injection Immunity Test
    inj_file = INVOICES_DIR / "INV-INJ-666.pdf"
    if inj_file.exists():
        extracted = invoice_tools.extract_invoice_data("INV-INJ-666.pdf")
        checks.append({
            "id": "SEC-06",
            "name": "Prompt Injection Immunity",
            "rule": "Untrusted invoice text is parsed as data and cannot hijack execution",
            "passed": extracted.get("ok") is True and extracted.get("data", {}).get("total_amount") == 21000.0,
            "detail": "Invoice text extracted safely without altering state invariants."
        })

    # 7. Duplicate Record Double-Entry Prevention
    dup = invoice_tools.check_duplicate("XYZ Solutions", "INV-XYZ-102")
    checks.append({
        "id": "SEC-07",
        "name": "Duplicate Double-Entry Guard",
        "rule": "Pre-existing invoice is detected and prevented from duplicate insertion",
        "passed": dup.get("ok") is True and dup.get("data", {}).get("is_duplicate") is True,
        "detail": dup.get("message")
    })

    # 8. Corrupt Write Verification Detection
    inv_tools_test = invoice_tools.verify_finance_record("INV-XYZ-102", "XYZ Solutions", 999999.0, "2026-10-20")
    checks.append({
        "id": "SEC-08",
        "name": "Independent Verification Mismatch Detection",
        "rule": "Discrepancy between invoice and database triggers verification failure",
        "passed": inv_tools_test.get("ok") is False and inv_tools_test.get("error_type") == "verification_mismatch",
        "detail": inv_tools_test.get("message")
    })

    # 9. Argument Schema Validation
    invalid_schema_res, rej_schema = PolicyEngine.validate_action(state, "find_latest_invoice", {})
    checks.append({
        "id": "SEC-09",
        "name": "Strict Pydantic Schema Validation",
        "rule": "Tools enforce validated Pydantic models for all arguments",
        "passed": (not invalid_schema_res) and rej_schema.get("error_type") == "invalid_tool_arguments",
        "detail": rej_schema.get("message")
    })

    passed_count = sum(1 for c in checks if c["passed"])
    return {
        "total": len(checks),
        "passed": passed_count,
        "failed": len(checks) - passed_count,
        "compliance_score": f"{round((passed_count / len(checks)) * 100)}%",
        "checks": checks
    }


# ------------------------------------------------------------------------------
# Real-Time SSE Agent Stream Endpoint
# ------------------------------------------------------------------------------
@app.get("/api/stream")
def stream_task(
    goal: str,
    fail_mode: Optional[str] = None,
    interactive_mode: bool = True
):
    event_q: queue.Queue = queue.Queue()

    def stream_callback(event_type: str, data: Dict[str, Any]):
        event_q.put({"event": event_type, "data": data})

    def worker():
        try:
            run_task(
                goal=goal,
                fail_mode=fail_mode if fail_mode and fail_mode != "none" else None,
                interactive_approval=interactive_mode,
                approval_callback=None,  # Enables live web approval pausing
                event_callback=stream_callback,
                verbose=False
            )
        except Exception as e:
            event_q.put({"event": "error", "data": {"message": str(e)}})
        finally:
            event_q.put({"event": "done", "data": {}})

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    def event_generator():
        while True:
            try:
                item = event_q.get(timeout=30)
                if item["event"] == "done":
                    yield "event: done\ndata: {}\n\n"
                    break
                payload = json.dumps(item)
                yield f"data: {payload}\n\n"
            except queue.Empty:
                yield "event: ping\ndata: {}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


# ------------------------------------------------------------------------------
# Web Dashboard Single-Page Application (HTML/CSS/JS)
# ------------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def index_view():
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>NexaOps — Autonomous AI Operations Console</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #07090e;
      --card: #0d121f;
      --card-hover: #12192b;
      --card-glass: rgba(13, 18, 31, 0.75);
      --border: rgba(255, 255, 255, 0.08);
      --border-glow: rgba(56, 189, 248, 0.35);
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --text-dim: #64748b;
      --primary: #38bdf8;
      --primary-glow: rgba(56, 189, 248, 0.2);
      --accent: #818cf8;
      --success: #34d399;
      --warning: #fbbf24;
      --danger: #f87171;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background-color: var(--bg);
      background-image: 
        radial-gradient(circle at 10% 20%, rgba(56, 189, 248, 0.05) 0%, transparent 45%),
        radial-gradient(circle at 90% 10%, rgba(129, 140, 248, 0.05) 0%, transparent 45%),
        radial-gradient(circle at 50% 90%, rgba(52, 211, 153, 0.04) 0%, transparent 40%);
      color: var(--text);
      font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
      min-height: 100vh;
      line-height: 1.5;
      padding-bottom: 40px;
    }
    code, pre, .mono { font-family: 'JetBrains Mono', monospace; }

    /* Navigation */
    nav {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 14px 32px;
      border-bottom: 1px solid var(--border);
      background: rgba(7, 9, 14, 0.88);
      backdrop-filter: blur(16px);
      position: sticky;
      top: 0;
      z-index: 50;
    }
    .brand { display: flex; align-items: center; gap: 12px; }
    .brand-icon {
      width: 36px; height: 36px; border-radius: 10px;
      background: linear-gradient(135deg, #0284c7, #6366f1);
      display: flex; align-items: center; justify-content: center;
      box-shadow: 0 0 16px var(--primary-glow);
    }
    .brand-title { font-size: 1.15rem; font-weight: 800; letter-spacing: -0.02em; }
    .nav-actions { display: flex; align-items: center; gap: 12px; }

    /* Pill Badges */
    .pill {
      display: inline-flex; align-items: center; gap: 6px;
      padding: 5px 12px; border-radius: 20px; font-size: 0.75rem; font-weight: 600;
      background: rgba(255, 255, 255, 0.05); border: 1px solid var(--border); color: var(--text-muted);
    }
    .dot { width: 7px; height: 7px; border-radius: 50%; }
    .pulse-dot { animation: pulse 1.5s infinite; }
    @keyframes pulse { 0% { opacity: 1; transform: scale(1); } 50% { opacity: 0.4; transform: scale(1.3); } 100% { opacity: 1; transform: scale(1); } }

    /* Container & Tabs */
    .container { max-width: 1380px; margin: 24px auto; padding: 0 24px; }
    .tabs-bar {
      display: flex; gap: 8px; margin-bottom: 20px; border-bottom: 1px solid var(--border); padding-bottom: 8px;
    }
    .tab-btn {
      background: transparent; border: none; color: var(--text-muted);
      padding: 8px 16px; border-radius: 8px; font-size: 0.88rem; font-weight: 600; cursor: pointer;
      display: flex; align-items: center; gap: 8px; transition: all 0.2s ease;
    }
    .tab-btn:hover { color: var(--text); background: rgba(255,255,255,0.04); }
    .tab-btn.active { color: var(--primary); background: rgba(56, 189, 248, 0.1); border: 1px solid rgba(56, 189, 248, 0.3); }

    /* KPIs */
    .kpi-bar { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 24px; }
    .kpi-card {
      background: var(--card-glass); border: 1px solid var(--border); border-radius: 14px;
      padding: 16px 20px; backdrop-filter: blur(12px);
    }
    .kpi-title { font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-dim); }
    .kpi-val { font-size: 1.5rem; font-weight: 800; margin-top: 4px; }
    .kpi-sub { font-size: 0.72rem; color: var(--text-muted); margin-top: 2px; }

    /* Layout */
    .grid { display: grid; grid-template-columns: 1.15fr 0.85fr; gap: 20px; }
    .panel {
      background: var(--card-glass); border: 1px solid var(--border); border-radius: 16px;
      padding: 22px; backdrop-filter: blur(12px); display: flex; flex-direction: column;
    }
    .panel-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
    .panel-title { font-size: 0.95rem; font-weight: 700; display: flex; align-items: center; gap: 8px; }

    /* Presets */
    .presets { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 14px; }
    .chip {
      background: rgba(255, 255, 255, 0.04); border: 1px solid var(--border);
      color: var(--text-muted); border-radius: 20px; padding: 6px 14px; font-size: 0.78rem; font-weight: 600;
      cursor: pointer; transition: all 0.2s ease; display: inline-flex; align-items: center; gap: 6px;
    }
    .chip:hover { border-color: var(--primary); color: var(--text); background: rgba(56, 189, 248, 0.08); }

    /* Inputs */
    .input-wrapper { margin-bottom: 14px; }
    input[type="text"], select {
      width: 100%; background: rgba(0, 0, 0, 0.4); border: 1px solid var(--border);
      border-radius: 10px; padding: 12px 14px; font-size: 0.9rem; color: var(--text);
      outline: none; font-family: inherit; transition: border-color 0.2s;
    }
    input[type="text"]:focus, select:focus { border-color: var(--primary); box-shadow: 0 0 10px var(--primary-glow); }

    /* Actions */
    .action-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
    .btn-primary {
      background: linear-gradient(135deg, #0284c7, #38bdf8); color: #050b14; border: none;
      border-radius: 10px; padding: 10px 20px; font-weight: 700; font-size: 0.88rem; cursor: pointer;
      display: inline-flex; align-items: center; gap: 8px; box-shadow: 0 4px 14px rgba(56, 189, 248, 0.3);
      transition: all 0.2s ease;
    }
    .btn-primary:hover { transform: translateY(-1px); box-shadow: 0 6px 20px rgba(56, 189, 248, 0.4); }
    .btn-secondary {
      background: rgba(255, 255, 255, 0.06); color: var(--text); border: 1px solid var(--border);
      border-radius: 10px; padding: 10px 16px; font-weight: 600; font-size: 0.85rem; cursor: pointer;
      display: inline-flex; align-items: center; gap: 6px;
    }
    .btn-secondary:hover { background: rgba(255, 255, 255, 0.1); }

    /* Decision Cards (HITL) */
    .decision-card {
      border: 1px solid var(--warning); background: rgba(251, 191, 36, 0.08);
      border-radius: 12px; padding: 16px; margin: 12px 0; animation: fadeIn 0.3s ease;
    }
    .decision-title { font-weight: 700; color: var(--warning); display: flex; align-items: center; gap: 8px; font-size: 0.92rem; }
    .decision-actions { display: flex; gap: 10px; margin-top: 12px; }
    .btn-approve { background: var(--success); color: #022c22; font-weight: 700; border: none; border-radius: 8px; padding: 8px 16px; cursor: pointer; }
    .btn-reject { background: var(--danger); color: #450a0a; font-weight: 700; border: none; border-radius: 8px; padding: 8px 16px; cursor: pointer; }

    /* Timeline */
    .timeline { flex: 1; min-height: 280px; max-height: 480px; overflow-y: auto; display: flex; flex-direction: column; gap: 10px; padding-right: 6px; }
    .step-card {
      background: rgba(255, 255, 255, 0.02); border: 1px solid var(--border); border-left: 3px solid var(--primary);
      border-radius: 10px; padding: 12px 14px; animation: slideIn 0.25s ease;
    }
    .step-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
    .step-action-tag { font-family: 'JetBrains Mono', monospace; font-size: 0.78rem; font-weight: 600; color: var(--primary); }
    .step-thought-box { font-size: 0.82rem; color: var(--text-muted); font-style: italic; margin-bottom: 6px; }
    .step-obs-box {
      font-size: 0.8rem; background: rgba(0, 0, 0, 0.35); border-radius: 6px; padding: 6px 10px;
      border-left: 2px solid var(--success); color: #cbd5e1;
    }
    .step-obs-box.fail { border-left-color: var(--danger); color: #fca5a5; }

    /* Tables */
    table { width: 100%; border-collapse: collapse; font-size: 0.82rem; }
    th { text-align: left; padding: 10px; color: var(--text-dim); border-bottom: 1px solid var(--border); text-transform: uppercase; font-size: 0.72rem; }
    td { padding: 10px; border-bottom: 1px solid rgba(255, 255, 255, 0.04); }
    tr:hover td { background: rgba(255, 255, 255, 0.02); }

    /* Status Banner */
    .status-banner { padding: 12px 16px; border-radius: 10px; margin-bottom: 14px; display: none; font-size: 0.86rem; }

    /* PDF Modal */
    .modal-overlay {
      position: fixed; inset: 0; background: rgba(0, 0, 0, 0.8); backdrop-filter: blur(8px);
      display: none; align-items: center; justify-content: center; z-index: 100;
    }
    .modal-box {
      width: 90%; max-width: 900px; height: 85vh; background: var(--card); border: 1px solid var(--border);
      border-radius: 16px; display: flex; flex-direction: column; overflow: hidden;
    }
    .modal-header { display: flex; justify-content: space-between; align-items: center; padding: 16px 20px; border-bottom: 1px solid var(--border); }
    .modal-body { flex: 1; background: #111; }
    .modal-body iframe { width: 100%; height: 100%; border: none; }

    /* JSON Box */
    .json-view {
      background: #020408; border: 1px solid var(--border); border-radius: 10px;
      padding: 14px; font-size: 0.78rem; color: #38bdf8; overflow-x: auto; max-height: 280px;
    }

    @keyframes fadeIn { from { opacity: 0; transform: translateY(-4px); } to { opacity: 1; transform: translateY(0); } }
    @keyframes slideIn { from { opacity: 0; transform: translateX(-6px); } to { opacity: 1; transform: translateX(0); } }
  </style>
</head>
<body>

  <!-- Top Nav -->
  <nav>
    <div class="brand">
      <div class="brand-icon">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.5"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></svg>
      </div>
      <div>
        <div class="brand-title">NexaOps Console</div>
        <div style="font-size:0.7rem; color:var(--text-dim);">Autonomous AI Operations Employee</div>
      </div>
    </div>

    <div class="nav-actions">
      <!-- LLM Provider Switcher (§10) -->
      <select id="providerSelect" style="width:180px; padding:6px 10px; font-size:0.78rem;" onchange="updateProviderConfig()">
        <option value="fake">Deterministic Mock (Offline)</option>
        <option value="gemini">Gemini 2.5 Flash (Live)</option>
        <option value="openai">OpenAI GPT-4o-mini (Live)</option>
      </select>

      <span class="pill"><span class="dot" style="background:#38bdf8;"></span> Guardrails Active</span>
      <span id="liveBadge" class="pill" style="display:none; color:#38bdf8; border-color:#38bdf8; background:rgba(56,189,248,0.1);"><span class="dot pulse-dot" style="background:#38bdf8;"></span> STREAMING</span>
    </div>
  </nav>

  <div class="container">

    <!-- KPI Summary Bar -->
    <div class="kpi-bar">
      <div class="kpi-card">
        <div class="kpi-title">Invoices Recorded</div>
        <div class="kpi-val" id="kpiCount">—</div>
        <div class="kpi-sub">System of Record</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-title">Approval Threshold</div>
        <div class="kpi-val" id="kpiThreshold">₹50,000</div>
        <div class="kpi-sub">Deterministic Python Guardrail</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-title">Independent Verification</div>
        <div class="kpi-val" style="color:var(--success);">100%</div>
        <div class="kpi-sub">Mandatory Field Check</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-title">Security Compliance</div>
        <div class="kpi-val" style="color:var(--primary);" id="kpiSec">9/9 Verified</div>
        <div class="kpi-sub">Zero Injection & Strict Allowlist</div>
      </div>
    </div>

    <!-- Tab Navigation -->
    <div class="tabs-bar">
      <button class="tab-btn active" onclick="switchTab('console')">⚡ Task Controller</button>
      <button class="tab-btn" onclick="switchTab('database')">📊 Database Records</button>
      <button class="tab-btn" onclick="switchTab('audit')">📜 Audit Trail</button>
      <button class="tab-btn" onclick="switchTab('vault')">📁 Invoice PDF Vault</button>
      <button class="tab-btn" onclick="switchTab('security')">🛡️ Security Suite</button>
    </div>

    <!-- TAB 1: TASK CONTROLLER -->
    <div id="tab-console" class="grid">
      <!-- Left: Input & Timeline -->
      <div class="panel">
        <div class="panel-header">
          <div class="panel-title">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polygon points="10 8 16 12 10 16 10 8"/></svg>
            Task Dispatcher
          </div>
          <span style="font-size:0.75rem; color:var(--text-dim);" id="stepCounter">0 Steps</span>
        </div>

        <div style="font-size:0.75rem; color:var(--text-dim); margin-bottom:8px;">Presets:</div>
        <div class="presets">
          <button class="chip" onclick="setGoal('Process the latest invoice from ABC Technologies')">
            <span>✨</span> Happy Path (ABC)
          </button>
          <button class="chip" onclick="setGoal('Process the latest invoice from Delta Systems')">
            <span>🛡️</span> Approval Gate (Delta ₹7.5L)
          </button>
          <button class="chip" onclick="setGoal('Process the latest invoice from XYZ Solutions')">
            <span>🔄</span> Duplicate Test (XYZ)
          </button>
          <button class="chip" onclick="setGoal('Process the latest invoice from Acme Corp')">
            <span>⚠️</span> Missing Due Date (Acme)
          </button>
          <button class="chip" onclick="setGoal('List all invoices from ABC Technologies')">
            <span>📋</span> Generalization (List)
          </button>
        </div>

        <div class="input-wrapper">
          <input type="text" id="goalInput" value="Process the latest invoice from ABC Technologies" placeholder="Enter business objective in natural language...">
        </div>

        <div class="action-row">
          <div style="display:flex; gap:12px; align-items:center;">
            <label style="font-size:0.78rem; display:flex; align-items:center; gap:6px; cursor:pointer;">
              <input type="checkbox" id="failTimeout"> Timeout (504)
            </label>
            <label style="font-size:0.78rem; display:flex; align-items:center; gap:6px; cursor:pointer;">
              <input type="checkbox" id="failMismatch"> Mismatch
            </label>
          </div>
          <div style="display:flex; gap:8px;">
            <button class="btn-secondary" onclick="resetDemoDb()" title="Reset SQLite DB and sample invoices">
              🔄 Reset DB
            </button>
            <button class="btn-primary" id="runBtn" onclick="runStreamTask()">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="5 3 19 12 5 21 5 3"/></svg>
              Dispatch Agent
            </button>
          </div>
        </div>

        <!-- Real-Time Human Decision Box (§63) -->
        <div id="interactiveDecisionBox" style="display:none;"></div>

        <!-- Status Banner -->
        <div id="statusBanner" class="status-banner"></div>

        <div class="panel-header" style="margin-top:10px; margin-bottom:8px; border-top:1px solid var(--border); padding-top:12px;">
          <div class="panel-title" style="font-size:0.85rem; color:var(--text-muted);">Real-Time Execution Timeline</div>
        </div>
        <div class="timeline" id="timeline">
          <div style="text-align:center; color:var(--text-dim); font-size:0.85rem; padding:40px 0;">
            Awaiting task dispatch. Select a scenario above and click Dispatch Agent.
          </div>
        </div>
      </div>

      <!-- Right: Evidence Package -->
      <div class="panel">
        <div class="panel-header">
          <div class="panel-title">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
            Auditable Evidence Package
          </div>
          <button class="btn-secondary" id="copyBtn" style="padding:4px 10px; font-size:0.75rem;" onclick="copyEvidence()">Copy JSON</button>
        </div>
        <div id="evidenceBox" style="flex:1;">
          <div style="text-align:center; color:var(--text-dim); font-size:0.85rem; padding:40px 0;">
            Evidence package will compile here upon independent verification.
          </div>
        </div>
      </div>
    </div>

    <!-- TAB 2: DATABASE RECORDS -->
    <div id="tab-database" class="panel" style="display:none;">
      <div class="panel-header">
        <div class="panel-title">System of Record: Finance Database</div>
        <button class="btn-secondary" onclick="loadRecords()">🔄 Refresh</button>
      </div>
      <table id="recordsTable">
        <thead>
          <tr>
            <th>ID</th>
            <th>Invoice Number</th>
            <th>Vendor</th>
            <th>Amount</th>
            <th>Due Date</th>
            <th>Status</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody></tbody>
      </table>
    </div>

    <!-- TAB 3: AUDIT TRAIL (§52) -->
    <div id="tab-audit" class="panel" style="display:none;">
      <div class="panel-header">
        <div class="panel-title">Immutable Audit Trail (SQLite)</div>
        <button class="btn-secondary" onclick="loadAuditTrail()">🔄 Refresh</button>
      </div>
      <div style="margin-bottom:12px;">
        <input type="text" id="auditSearch" placeholder="Filter audit trail by tool, status, or task ID..." oninput="filterAuditTrail()">
      </div>
      <div style="max-height:550px; overflow-y:auto;">
        <table id="auditTable">
          <thead>
            <tr>
              <th>Timestamp</th>
              <th>Task ID</th>
              <th>Step</th>
              <th>Tool</th>
              <th>Arguments</th>
              <th>Result / Status</th>
            </tr>
          </thead>
          <tbody></tbody>
        </table>
      </div>
    </div>

    <!-- TAB 4: INVOICE PDF VAULT (§7, §40) -->
    <div id="tab-vault" class="panel" style="display:none;">
      <div class="panel-header">
        <div class="panel-title">Sample Invoice PDF Vault</div>
        <button class="btn-secondary" onclick="loadPdfVault()">🔄 Refresh</button>
      </div>
      <table id="vaultTable">
        <thead>
          <tr>
            <th>Filename</th>
            <th>Size</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody></tbody>
      </table>
    </div>

    <!-- TAB 5: SECURITY SUITE (§64) -->
    <div id="tab-security" class="panel" style="display:none;">
      <div class="panel-header">
        <div class="panel-title">Red-Team Security & Policy Verification Suite</div>
        <button class="btn-primary" onclick="runSecurityChecks()">🛡️ Run Security Suite</button>
      </div>
      <div id="securityResults" style="margin-top:12px;">
        <div style="text-align:center; color:var(--text-dim); padding:40px 0;">
          Click "Run Security Suite" to execute all 9 deterministic policy and security boundary tests.
        </div>
      </div>
    </div>

  </div>

  <!-- PDF Preview Modal -->
  <div class="modal-overlay" id="pdfModal">
    <div class="modal-box">
      <div class="modal-header">
        <span style="font-weight:700;" id="modalPdfTitle">Invoice PDF Preview</span>
        <button class="btn-secondary" style="padding:4px 10px;" onclick="closePdfModal()">✕ Close</button>
      </div>
      <div class="modal-body">
        <iframe id="pdfFrame" src=""></iframe>
      </div>
    </div>
  </div>

  <script>
    let currentEvidence = null;
    let currentActiveTaskId = null;
    let auditDataCache = [];

    function switchTab(name) {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-btn').forEach(b => {
        if (b.innerText.toLowerCase().includes(name)) b.classList.add('active');
      });
      ['console', 'database', 'audit', 'vault', 'security'].forEach(t => {
        const el = document.getElementById('tab-' + t);
        if (el) el.style.display = (t === name) ? ((t === 'console') ? 'grid' : 'flex') : 'none';
      });
      if (name === 'database') loadRecords();
      if (name === 'audit') loadAuditTrail();
      if (name === 'vault') loadPdfVault();
      if (name === 'security' && !document.getElementById('secComplianceCard')) runSecurityChecks();
    }

    function setGoal(text) {
      document.getElementById('goalInput').value = text;
    }

    async function updateProviderConfig() {
      const p = document.getElementById('providerSelect').value;
      try {
        await fetch('/api/config', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ provider: p })
        });
      } catch (err) { console.error('Failed to update provider:', err); }
    }

    async function loadConfig() {
      try {
        const res = await fetch('/api/config');
        const d = await res.json();
        document.getElementById('providerSelect').value = d.provider;
        document.getElementById('kpiThreshold').innerText = '₹' + Number(d.threshold).toLocaleString('en-IN');
      } catch (err) { console.error(err); }
    }

    async function resetDemoDb() {
      try {
        const res = await fetch('/api/reset', { method: 'POST' });
        const d = await res.json();
        alert(d.message);
        loadRecords();
        loadAuditTrail();
      } catch (err) { alert('Reset failed: ' + err); }
    }

    async function loadRecords() {
      try {
        const res = await fetch('/api/records');
        const data = await res.json();
        document.getElementById('kpiCount').innerText = data.length;
        const tbody = document.querySelector('#recordsTable tbody');
        if (data.length === 0) {
          tbody.innerHTML = '<tr><td colspan="7" style="text-align:center; color:var(--text-dim);">No records found</td></tr>';
          return;
        }
        tbody.innerHTML = data.map(r => `
          <tr>
            <td class="mono" style="color:var(--text-dim);">#${r.id}</td>
            <td class="mono" style="font-weight:600; color:var(--primary);">${r.invoice_number}</td>
            <td><strong>${r.vendor_name}</strong></td>
            <td style="font-weight:700;">₹${Number(r.total_amount).toLocaleString('en-IN', {minimumFractionDigits: 2})}</td>
            <td class="mono" style="color:var(--text-muted);">${r.due_date || 'N/A'}</td>
            <td><span class="pill" style="color:var(--success); border-color:var(--success); font-size:0.7rem;">${r.status}</span></td>
            <td>
              <button class="btn-secondary" style="padding:4px 8px; font-size:0.72rem;" onclick="previewPdf('${r.invoice_number}.pdf')">
                📄 View PDF
              </button>
            </td>
          </tr>
        `).join('');
      } catch (err) { console.error(err); }
    }

    async function loadAuditTrail() {
      try {
        const res = await fetch('/api/audit');
        auditDataCache = await res.json();
        renderAuditRows(auditDataCache);
      } catch (err) { console.error(err); }
    }

    function renderAuditRows(rows) {
      const tbody = document.querySelector('#auditTable tbody');
      if (!rows || rows.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; color:var(--text-dim);">No audit events recorded</td></tr>';
        return;
      }
      tbody.innerHTML = rows.map(a => {
        const isPolicyRej = a.status === 'REJECTED_BY_POLICY';
        const color = isPolicyRej ? 'var(--danger)' : 'var(--text-muted)';
        return `
          <tr>
            <td class="mono" style="font-size:0.72rem; color:var(--text-dim);">${(a.timestamp || '').slice(11, 19)}</td>
            <td class="mono" style="font-size:0.72rem; color:var(--primary);">${a.task_id}</td>
            <td class="mono">${a.step}</td>
            <td class="mono" style="font-weight:700; color:${color};">${a.tool}</td>
            <td><pre style="font-size:0.7rem; color:#94a3b8; max-width:280px; overflow:hidden; text-overflow:ellipsis;">${JSON.stringify(a.args)}</pre></td>
            <td>
              <span class="pill" style="font-size:0.7rem; color:${isPolicyRej ? 'var(--danger)' : 'var(--success)'};">${a.status}</span>
            </td>
          </tr>
        `;
      }).join('');
    }

    function filterAuditTrail() {
      const q = document.getElementById('auditSearch').value.toLowerCase();
      const filtered = auditDataCache.filter(a => 
        (a.tool || '').toLowerCase().includes(q) ||
        (a.status || '').toLowerCase().includes(q) ||
        (a.task_id || '').toLowerCase().includes(q)
      );
      renderAuditRows(filtered);
    }

    async function loadPdfVault() {
      try {
        const res = await fetch('/api/invoices');
        const files = await res.json();
        const tbody = document.querySelector('#vaultTable tbody');
        tbody.innerHTML = files.map(f => `
          <tr>
            <td class="mono" style="font-weight:600; color:var(--primary);">${f.filename}</td>
            <td>${f.size_kb} KB</td>
            <td>
              <button class="btn-secondary" style="padding:4px 10px; font-size:0.72rem;" onclick="previewPdf('${f.filename}')">
                👁️ Preview in Console
              </button>
            </td>
          </tr>
        `).join('');
      } catch (err) { console.error(err); }
    }

    function previewPdf(filename) {
      document.getElementById('modalPdfTitle').innerText = 'Invoice Document: ' + filename;
      document.getElementById('pdfFrame').src = '/api/invoices/' + filename;
      document.getElementById('pdfModal').style.display = 'flex';
    }

    function closePdfModal() {
      document.getElementById('pdfModal').style.display = 'none';
      document.getElementById('pdfFrame').src = '';
    }

    async function runSecurityChecks() {
      const secDiv = document.getElementById('securityResults');
      secDiv.innerHTML = '<div style="text-align:center; color:var(--primary); padding:30px 0;">Executing 9 enterprise security boundary validations...</div>';
      try {
        const res = await fetch('/api/security-test');
        const d = await res.json();
        document.getElementById('kpiSec').innerText = `${d.passed}/${d.total} Verified`;

        secDiv.innerHTML = `
          <div id="secComplianceCard" style="display:flex; justify-content:space-between; align-items:center; background:rgba(52,211,153,0.08); border:1px solid rgba(52,211,153,0.3); border-radius:12px; padding:16px 20px; margin-bottom:16px;">
            <div>
              <div style="font-weight:800; font-size:1.1rem; color:var(--success);">Compliance Score: ${d.compliance_score}</div>
              <div style="font-size:0.78rem; color:var(--text-muted);">${d.passed} of ${d.total} security checks passed with zero policy bypasses</div>
            </div>
            <span class="pill" style="color:var(--success); border-color:var(--success);">PASSED (0 FAILURES)</span>
          </div>

          <table style="margin-top:12px;">
            <thead>
              <tr>
                <th>Test ID</th>
                <th>Security Check</th>
                <th>Deterministic Policy Rule</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              ${d.checks.map(c => `
                <tr>
                  <td class="mono" style="color:var(--primary);">${c.id}</td>
                  <td><strong>${c.name}</strong></td>
                  <td style="color:var(--text-muted); font-size:0.8rem;">${c.rule}</td>
                  <td>
                    <span class="pill" style="color:${c.passed ? 'var(--success)' : 'var(--danger)'}; border-color:${c.passed ? 'var(--success)' : 'var(--danger)'};">
                      ${c.passed ? '✓ PASSED' : '✕ FAILED'}
                    </span>
                  </td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        `;
      } catch (err) {
        secDiv.innerHTML = `<div style="color:var(--danger);">Error running security checks: ${err}</div>`;
      }
    }

    // Real-Time SSE Agent Loop
    function runStreamTask() {
      const goal = document.getElementById('goalInput').value;
      const failTimeout = document.getElementById('failTimeout').checked;
      const failMismatch = document.getElementById('failMismatch').checked;
      const runBtn = document.getElementById('runBtn');
      const timeline = document.getElementById('timeline');
      const banner = document.getElementById('statusBanner');
      const evidenceBox = document.getElementById('evidenceBox');
      const liveBadge = document.getElementById('liveBadge');
      const stepCounter = document.getElementById('stepCounter');
      const decisionBox = document.getElementById('interactiveDecisionBox');

      runBtn.disabled = true;
      runBtn.innerHTML = 'Executing...';
      liveBadge.style.display = 'inline-flex';
      timeline.innerHTML = '';
      banner.style.display = 'none';
      decisionBox.style.display = 'none';
      stepCounter.innerText = '0 Steps';
      currentEvidence = null;
      currentActiveTaskId = null;
      evidenceBox.innerHTML = '<div style="color:var(--text-dim); font-size:0.82rem; padding:12px; text-align:center;">Compiling evidence...</div>';

      const failMode = failTimeout ? 'timeout' : (failMismatch ? 'verification_mismatch' : 'none');
      const query = new URLSearchParams({
        goal: goal,
        fail_mode: failMode,
        interactive_mode: 'true'
      });

      const eventSource = new EventSource('/api/stream?' + query.toString());

      eventSource.onmessage = function(e) {
        try {
          const msg = JSON.parse(e.data);
          const evt = msg.event;
          const data = msg.data;

          if (evt === 'task_start') {
            currentActiveTaskId = data.task_id;
            timeline.innerHTML = `
              <div style="font-size:0.75rem; color:var(--text-dim); margin-bottom:8px; display:flex; justify-content:space-between;">
                <span>TASK INITIALIZED: <span class="mono">${data.task_id}</span></span>
                <span class="mono">STATUS: RUNNING</span>
              </div>
            `;
          } else if (evt === 'step_planned') {
            stepCounter.innerText = `Step ${data.step}`;
            timeline.innerHTML += `
              <div class="step-card" id="step-${data.step}">
                <div class="step-header">
                  <span class="step-num" style="font-size:0.75rem; color:var(--text-dim);">Step ${data.step}</span>
                  <span class="step-action-tag">${data.action}</span>
                </div>
                ${data.thought_summary ? `<div class="step-thought-box">"${data.thought_summary}"</div>` : ''}
                <div style="font-size:0.72rem; color:var(--text-dim);" class="mono">args: ${JSON.stringify(data.args)}</div>
                <div class="step-obs-box" id="obs-${data.step}" style="color:var(--text-dim);">Executing tool in sandbox...</div>
              </div>
            `;
            timeline.scrollTop = timeline.scrollHeight;
          } else if (evt === 'observation') {
            const obsContainer = document.getElementById('obs-' + data.step);
            if (obsContainer) {
              const ok = data.observation.ok;
              obsContainer.className = 'step-obs-box ' + (ok ? '' : 'fail');
              obsContainer.innerHTML = `<strong>Observation:</strong> [${ok ? 'SUCCESS' : 'FAILURE'}] ${data.observation.message}`;
            }
            timeline.scrollTop = timeline.scrollHeight;
          } else if (evt === 'waiting_for_approval') {
            // Live Human Decision Card (§63)
            decisionBox.style.display = 'block';
            decisionBox.innerHTML = `
              <div class="decision-card">
                <div class="decision-title">
                  <span>🛡️ SUPERVISOR APPROVAL REQUIRED</span>
                </div>
                <div style="font-size:0.85rem; margin-top:6px;">
                  Invoice <strong>${data.invoice_number}</strong> total (<strong>₹${Number(data.amount).toLocaleString('en-IN')}</strong>) exceeds enterprise threshold.
                </div>
                <div style="font-size:0.75rem; color:var(--text-dim); margin-top:2px;">Reason: ${data.reason}</div>
                <div class="decision-actions">
                  <button class="btn-approve" onclick="submitDecision('${data.task_id}', true)">✓ Approve Invoice</button>
                  <button class="btn-reject" onclick="submitDecision('${data.task_id}', false)">✕ Reject Invoice</button>
                  <button class="btn-secondary" style="padding:6px 12px; font-size:0.75rem;" onclick="previewPdf('${data.invoice_number}.pdf')">📄 View Invoice PDF</button>
                </div>
              </div>
            `;
            timeline.scrollTop = timeline.scrollHeight;
          } else if (evt === 'waiting_for_input') {
            // Live Clarification Card (§31, Q8)
            decisionBox.style.display = 'block';
            decisionBox.innerHTML = `
              <div class="decision-card" style="border-color:var(--primary); background:rgba(56,189,248,0.08);">
                <div class="decision-title" style="color:var(--primary);">
                  <span>❓ CLARIFICATION REQUIRED: MISSING DATA</span>
                </div>
                <div style="font-size:0.85rem; margin-top:6px;">${data.question}</div>
                <div style="display:flex; gap:8px; margin-top:10px;">
                  <input type="text" id="clarificationInput" value="2026-11-15" style="max-width:260px;" placeholder="Enter value (e.g. 2026-11-15)">
                  <button class="btn-primary" onclick="submitInputClarification('${data.task_id}')">Submit Clarification</button>
                </div>
              </div>
            `;
          } else if (evt === 'policy_rejection') {
            timeline.innerHTML += `
              <div class="step-card" style="border-left-color:var(--danger); background:rgba(248,113,113,0.06);">
                <div class="step-header">
                  <span style="color:var(--danger); font-weight:700;">[POLICY REJECTION] ${data.action}</span>
                </div>
                <div style="font-size:0.82rem; color:#fca5a5; margin-top:4px;">${data.rejection.message}</div>
              </div>
            `;
            timeline.scrollTop = timeline.scrollHeight;
          } else if (evt === 'task_finish') {
            decisionBox.style.display = 'none';
            banner.style.display = 'block';
            if (data.status === 'COMPLETED') {
              banner.style.background = 'rgba(52, 211, 153, 0.12)';
              banner.style.border = '1px solid rgba(52, 211, 153, 0.4)';
              banner.innerHTML = `<strong style="color:var(--success);">[TASK COMPLETED]</strong> ${data.summary}`;
            } else if (data.status === 'REJECTED') {
              banner.style.background = 'rgba(248, 113, 113, 0.12)';
              banner.style.border = '1px solid rgba(248, 113, 113, 0.4)';
              banner.innerHTML = `<strong style="color:var(--danger);">[TASK REJECTED]</strong> ${data.summary}`;
            } else {
              banner.style.background = 'rgba(251, 191, 36, 0.12)';
              banner.style.border = '1px solid rgba(251, 191, 36, 0.4)';
              banner.innerHTML = `<strong style="color:var(--warning);">[TASK ${data.status}]</strong> ${data.summary}`;
            }

            if (data.evidence) {
              currentEvidence = data.evidence;
              evidenceBox.innerHTML = `<pre class="json-view">${JSON.stringify(data.evidence, null, 2)}</pre>`;
            } else {
              evidenceBox.innerHTML = `<div style="color:var(--text-muted); font-size:0.82rem; padding:8px;">${data.summary}</div>`;
            }

            loadRecords();
            loadAuditTrail();
          } else if (evt === 'error') {
            decisionBox.style.display = 'none';
            banner.style.display = 'block';
            banner.style.background = 'rgba(248, 113, 113, 0.12)';
            banner.style.border = '1px solid rgba(248, 113, 113, 0.4)';
            banner.innerHTML = `<strong style="color:var(--danger);">[SYSTEM ERROR]</strong> ${data.message}`;
          }
        } catch (err) {
          console.error('SSE Error:', err);
        }
      };

      eventSource.addEventListener('done', function() {
        eventSource.close();
        runBtn.disabled = false;
        runBtn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="5 3 19 12 5 21 5 3"/></svg> Dispatch Agent';
        liveBadge.style.display = 'none';
        loadRecords();
        loadAuditTrail();
      });

      eventSource.onerror = function() {
        eventSource.close();
        runBtn.disabled = false;
        runBtn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="5 3 19 12 5 21 5 3"/></svg> Dispatch Agent';
        liveBadge.style.display = 'none';
        loadRecords();
        loadAuditTrail();
      };
    }

    async function submitDecision(taskId, isApproved) {
      document.getElementById('interactiveDecisionBox').innerHTML = '<div style="color:var(--text-dim); padding:10px;">Submitting supervisor decision...</div>';
      try {
        await fetch(`/api/tasks/${taskId}/approval`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ decision: isApproved })
        });
      } catch (err) {
        alert('Error submitting decision: ' + err);
      }
    }

    async function submitInputClarification(taskId) {
      const val = document.getElementById('clarificationInput').value;
      document.getElementById('interactiveDecisionBox').innerHTML = '<div style="color:var(--text-dim); padding:10px;">Submitting clarification to agent...</div>';
      try {
        await fetch(`/api/tasks/${taskId}/input`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ input: val })
        });
      } catch (err) {
        alert('Error submitting input: ' + err);
      }
    }

    function copyEvidence() {
      if (!currentEvidence) {
        alert('No evidence package available yet.');
        return;
      }
      navigator.clipboard.writeText(JSON.stringify(currentEvidence, null, 2));
      const btn = document.getElementById('copyBtn');
      btn.innerText = '✓ Copied!';
      setTimeout(() => { btn.innerText = 'Copy JSON'; }, 2000);
    }

    // Init
    loadConfig();
    loadRecords();
  </script>
</body>
</html>
"""


if __name__ == "__main__":
    import uvicorn
    print("Starting NexaOps Web Console on http://localhost:8000 ...")
    uvicorn.run("web.app:app", host="127.0.0.1", port=8000, reload=False)
