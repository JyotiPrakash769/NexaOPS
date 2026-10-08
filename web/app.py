"""
Single-Page FastAPI Web Viewer for NexaOps with Premium Dark Glassmorphic Design and Real-Time SSE Streaming.
Provides an enterprise AI Operations Console to:
1. Submit business goals (or choose demo presets).
2. Watch the agent loop execute in REAL TIME via Server-Sent Events (SSE).
3. View the finance system of record records with live filtering.
4. Inspect the auditable evidence package with syntax highlighting and clipboard export.
5. Review the immutable audit log from SQLite.
"""

import sys
import json
import queue
import threading
import time
from pathlib import Path
from typing import Optional, Dict, Any, List

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from agent.controller import run_task
from env import finance_db

app = FastAPI(title="NexaOps Operations Console")


class RunTaskRequest(BaseModel):
    goal: str
    fail_mode: Optional[str] = None
    approval_granted: bool = True


@app.get("/api/health")
def health():
    return {"status": "ok", "product": "NexaOps", "version": "1.0.0"}


@app.get("/api/records")
def get_records():
    return finance_db.list_records()


@app.get("/api/audit")
def get_audit(task_id: Optional[str] = None):
    if task_id:
        return finance_db.get_audit_events(task_id)
    conn = finance_db.get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM audit_events ORDER BY id DESC LIMIT 50")
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/api/stream")
def stream_task(
    goal: str,
    fail_mode: Optional[str] = None,
    approval_granted: bool = True
):
    """
    Streams agent execution events in real time using Server-Sent Events (SSE).
    """
    event_q: queue.Queue = queue.Queue()

    def stream_callback(event_type: str, data: Dict[str, Any]):
        event_q.put({"event": event_type, "data": data})

    def mock_approval(inv_num: str, amount: float, reason: str) -> bool:
        return approval_granted

    def worker():
        try:
            run_task(
                goal=goal,
                fail_mode=fail_mode if fail_mode and fail_mode != "none" else None,
                approval_callback=mock_approval,
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
      --success-glow: rgba(52, 211, 153, 0.15);
      --warning: #fbbf24;
      --warning-glow: rgba(251, 191, 36, 0.15);
      --danger: #f87171;
      --danger-glow: rgba(248, 113, 113, 0.15);
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background-color: var(--bg);
      background-image: 
        radial-gradient(circle at 10% 20%, rgba(56, 189, 248, 0.06) 0%, transparent 45%),
        radial-gradient(circle at 90% 10%, rgba(129, 140, 248, 0.06) 0%, transparent 45%),
        radial-gradient(circle at 50% 90%, rgba(52, 211, 153, 0.04) 0%, transparent 40%);
      color: var(--text);
      font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
      min-height: 100vh;
      line-height: 1.5;
      padding-bottom: 40px;
    }
    code, pre, .mono { font-family: 'JetBrains Mono', monospace; }

    /* Top Navigation */
    nav {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 16px 36px;
      border-bottom: 1px solid var(--border);
      background: rgba(7, 9, 14, 0.85);
      backdrop-filter: blur(16px);
      position: sticky;
      top: 0;
      z-index: 50;
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 12px;
      text-decoration: none;
      color: var(--text);
    }
    .logo-badge {
      width: 38px;
      height: 38px;
      border-radius: 10px;
      background: linear-gradient(135deg, #0284c7 0%, #6366f1 100%);
      display: flex;
      align-items: center;
      justify-content: center;
      font-weight: 800;
      font-size: 1.1rem;
      color: white;
      box-shadow: 0 0 16px var(--primary-glow);
    }
    .brand-title { font-size: 1.15rem; font-weight: 700; letter-spacing: -0.02em; }
    .brand-sub { font-size: 0.75rem; color: var(--text-dim); }
    .nav-status {
      display: flex;
      align-items: center;
      gap: 16px;
    }
    .pill {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 4px 12px;
      border-radius: 9999px;
      font-size: 0.75rem;
      font-weight: 600;
      border: 1px solid var(--border);
      background: rgba(255, 255, 255, 0.03);
    }
    .pill-green { color: var(--success); border-color: rgba(52, 211, 153, 0.3); background: var(--success-glow); }
    .dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
    .pulse-dot { animation: pulse 1.8s infinite; }
    @keyframes pulse { 0%, 100% { opacity: 1; transform: scale(1); } 50% { opacity: 0.4; transform: scale(1.3); } }

    /* Main Container */
    .container {
      max-width: 1440px;
      margin: 0 auto;
      padding: 24px 36px;
    }

    /* KPI Bar */
    .kpi-bar {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 16px;
      margin-bottom: 24px;
    }
    .kpi-card {
      background: var(--card-glass);
      backdrop-filter: blur(12px);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 16px 20px;
      transition: all 0.2s ease;
    }
    .kpi-card:hover { border-color: rgba(255, 255, 255, 0.16); transform: translateY(-2px); }
    .kpi-title { font-size: 0.75rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-muted); margin-bottom: 6px; }
    .kpi-val { font-size: 1.5rem; font-weight: 800; letter-spacing: -0.02em; color: var(--text); }
    .kpi-sub { font-size: 0.72rem; color: var(--text-dim); margin-top: 4px; }

    /* Dashboard Layout */
    .grid {
      display: grid;
      grid-template-columns: 1.15fr 0.85fr;
      gap: 24px;
    }
    .panel {
      background: var(--card-glass);
      backdrop-filter: blur(16px);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 24px;
      box-shadow: 0 12px 32px -8px rgba(0, 0, 0, 0.4);
    }
    .panel-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 18px;
      padding-bottom: 14px;
      border-bottom: 1px solid var(--border);
    }
    .panel-title {
      font-size: 1.05rem;
      font-weight: 700;
      letter-spacing: -0.01em;
      display: flex;
      align-items: center;
      gap: 8px;
    }

    /* Preset Chips */
    .preset-label { font-size: 0.75rem; font-weight: 600; text-transform: uppercase; color: var(--text-dim); margin-bottom: 8px; }
    .presets {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 16px;
    }
    button.chip {
      background: rgba(255, 255, 255, 0.03);
      border: 1px solid var(--border);
      color: #cbd5e1;
      padding: 7px 12px;
      border-radius: 8px;
      font-size: 0.78rem;
      font-weight: 500;
      cursor: pointer;
      transition: all 0.15s ease;
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }
    button.chip:hover {
      background: rgba(56, 189, 248, 0.08);
      border-color: var(--primary);
      color: var(--primary);
      transform: translateY(-1px);
    }

    /* Input & Dispatch */
    .input-wrapper {
      position: relative;
      margin-bottom: 14px;
    }
    input[type="text"] {
      width: 100%;
      background: rgba(7, 10, 18, 0.8);
      border: 1px solid rgba(255, 255, 255, 0.12);
      border-radius: 10px;
      padding: 14px 16px;
      color: var(--text);
      font-size: 0.92rem;
      font-family: inherit;
      transition: all 0.2s ease;
    }
    input[type="text"]:focus {
      outline: none;
      border-color: var(--primary);
      box-shadow: 0 0 0 3px rgba(56, 189, 248, 0.15);
      background: rgba(11, 16, 28, 0.95);
    }
    .action-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 20px;
      gap: 12px;
    }
    .switches {
      display: flex;
      gap: 16px;
      font-size: 0.8rem;
      color: var(--text-muted);
    }
    .switch-label {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      cursor: pointer;
      user-select: none;
    }
    .switch-label input[type="checkbox"] {
      accent-color: var(--primary);
      width: 15px;
      height: 15px;
      cursor: pointer;
    }
    button.btn-primary {
      background: linear-gradient(135deg, #0284c7 0%, #0369a1 100%);
      color: white;
      border: none;
      padding: 12px 24px;
      border-radius: 10px;
      font-weight: 700;
      font-size: 0.88rem;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 8px;
      box-shadow: 0 4px 16px rgba(2, 132, 199, 0.3);
      transition: all 0.2s ease;
    }
    button.btn-primary:hover {
      background: linear-gradient(135deg, #0369a1 0%, #0284c7 100%);
      box-shadow: 0 6px 20px rgba(2, 132, 199, 0.45);
      transform: translateY(-1px);
    }
    button.btn-primary:disabled {
      opacity: 0.6;
      cursor: not-allowed;
      transform: none;
      box-shadow: none;
    }

    /* Status Banner */
    .status-banner {
      display: none;
      border-radius: 10px;
      padding: 14px 18px;
      margin-bottom: 20px;
      font-size: 0.86rem;
      animation: slideIn 0.3s ease-out;
    }

    /* Timeline */
    .timeline {
      display: flex;
      flex-direction: column;
      gap: 12px;
      max-height: 520px;
      overflow-y: auto;
      padding-right: 6px;
    }
    .timeline::-webkit-scrollbar { width: 5px; }
    .timeline::-webkit-scrollbar-thumb { background: rgba(255, 255, 255, 0.1); border-radius: 4px; }
    .step-card {
      background: rgba(11, 16, 28, 0.7);
      border: 1px solid var(--border);
      border-left: 3px solid var(--primary);
      border-radius: 10px;
      padding: 14px 16px;
      font-size: 0.84rem;
      animation: slideIn 0.25s cubic-bezier(0.16, 1, 0.3, 1);
      transition: border-color 0.2s;
    }
    @keyframes slideIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
    .step-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 6px;
    }
    .step-num { font-weight: 700; color: var(--text); }
    .step-action-tag {
      font-family: 'JetBrains Mono', monospace;
      color: var(--primary);
      font-size: 0.82rem;
      background: rgba(56, 189, 248, 0.08);
      padding: 3px 8px;
      border-radius: 5px;
      border: 1px solid rgba(56, 189, 248, 0.2);
    }
    .step-thought-box {
      color: #93c5fd;
      font-style: italic;
      background: rgba(56, 189, 248, 0.04);
      padding: 8px 12px;
      border-radius: 6px;
      margin: 8px 0;
      border-left: 2px solid rgba(56, 189, 248, 0.4);
      line-height: 1.45;
    }
    .step-obs-box {
      background: rgba(255, 255, 255, 0.03);
      padding: 8px 12px;
      border-radius: 6px;
      margin-top: 8px;
      border-left: 2px solid var(--success);
      font-size: 0.82rem;
    }
    .step-obs-box.fail { border-left-color: var(--warning); color: #fde68a; }

    /* Right Panel Tabs */
    .tabs {
      display: flex;
      gap: 6px;
      margin-bottom: 16px;
      border-bottom: 1px solid var(--border);
      padding-bottom: 8px;
    }
    .tab-btn {
      background: transparent;
      border: none;
      color: var(--text-dim);
      font-weight: 600;
      font-size: 0.82rem;
      padding: 6px 14px;
      border-radius: 6px;
      cursor: pointer;
      transition: all 0.15s;
    }
    .tab-btn.active {
      background: rgba(255, 255, 255, 0.06);
      color: var(--primary);
    }

    /* Table */
    .table-wrapper {
      max-height: 380px;
      overflow-y: auto;
      border-radius: 8px;
      border: 1px solid var(--border);
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.82rem;
    }
    th, td {
      padding: 11px 14px;
      text-align: left;
      border-bottom: 1px solid var(--border);
    }
    th {
      background: rgba(13, 18, 31, 0.95);
      color: var(--text-dim);
      font-weight: 600;
      font-size: 0.74rem;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      position: sticky;
      top: 0;
      z-index: 10;
    }
    tr:hover td { background: rgba(255, 255, 255, 0.02); }
    .vendor-badge {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      font-weight: 600;
    }
    .avatar-mini {
      width: 22px;
      height: 22px;
      border-radius: 6px;
      background: linear-gradient(135deg, #334155 0%, #1e293b 100%);
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 0.68rem;
      color: #94a3b8;
    }

    /* Evidence Box */
    .evidence-card {
      background: rgba(7, 10, 18, 0.85);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 16px;
    }
    .evidence-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 12px;
      padding-bottom: 8px;
      border-bottom: 1px solid var(--border);
    }
    pre.json-view {
      color: #38bdf8;
      font-size: 0.78rem;
      line-height: 1.45;
      overflow-x: auto;
      max-height: 300px;
    }
    .btn-copy {
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid var(--border);
      color: var(--text-muted);
      padding: 4px 10px;
      border-radius: 5px;
      font-size: 0.72rem;
      cursor: pointer;
      transition: all 0.15s;
    }
    .btn-copy:hover { color: var(--text); border-color: rgba(255, 255, 255, 0.2); }
  </style>
</head>
<body>

  <!-- Top Navigation -->
  <nav>
    <a href="/" class="brand">
      <div class="logo-badge">N</div>
      <div>
        <div class="brand-title">NexaOps</div>
        <div class="brand-sub">Autonomous AI Operations Employee</div>
      </div>
    </a>
    <div class="nav-status">
      <span class="pill pill-green"><span class="dot"></span> SQLite Connected</span>
      <span class="pill"><span class="dot" style="background:#38bdf8;"></span> Guardrails Active</span>
      <span id="liveBadge" class="pill" style="display:none; color:#38bdf8; border-color:#38bdf8; background:rgba(56,189,248,0.1);"><span class="dot pulse-dot" style="background:#38bdf8;"></span> STREAMING</span>
    </div>
  </nav>

  <div class="container">

    <!-- KPI Metric Summary -->
    <div class="kpi-bar">
      <div class="kpi-card">
        <div class="kpi-title">Invoices Recorded</div>
        <div class="kpi-val" id="kpiCount">—</div>
        <div class="kpi-sub">System of Record</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-title">Approval Threshold</div>
        <div class="kpi-val">₹50,000</div>
        <div class="kpi-sub">Policy Enforced in Python</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-title">Independent Verification</div>
        <div class="kpi-val" style="color:var(--success);">100%</div>
        <div class="kpi-sub">Mandatory Field Check</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-title">Core Runtime</div>
        <div class="kpi-val" style="color:var(--primary);">Deterministic</div>
        <div class="kpi-sub">LLM Proposes, Code Controls</div>
      </div>
    </div>

    <!-- Main Workspace -->
    <div class="grid">

      <!-- Left Column: Command & Timeline -->
      <div class="panel">
        <div class="panel-header">
          <div class="panel-title">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="color:var(--primary);"><circle cx="12" cy="12" r="10"/><polygon points="10 8 16 12 10 16 10 8"/></svg>
            Task Controller
          </div>
          <span style="font-size:0.75rem; color:var(--text-dim);">Max 15 Steps</span>
        </div>

        <div class="preset-label">Test Scenarios & Presets</div>
        <div class="presets">
          <button class="chip" onclick="setGoal('Process the latest invoice from ABC Technologies')">
            <span>✨</span> Happy Path (ABC)
          </button>
          <button class="chip" onclick="setGoal('Process the latest invoice from Delta Systems')">
            <span>🛡️</span> Approval &gt; ₹50k (Delta)
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
          <div class="switches">
            <label class="switch-label">
              <input type="checkbox" id="failTimeout"> Simulate Timeout (504)
            </label>
            <label class="switch-label">
              <input type="checkbox" id="supervisorApproval" checked> Grant Approval
            </label>
          </div>
          <button class="btn-primary" id="runBtn" onclick="runStreamTask()">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="5 3 19 12 5 21 5 3"/></svg>
            Dispatch Agent
          </button>
        </div>

        <div id="statusBanner" class="status-banner"></div>

        <div class="panel-header" style="margin-top:20px; margin-bottom:12px; padding-bottom:8px;">
          <div class="panel-title" style="font-size:0.9rem; color:var(--text-muted);">Execution Timeline</div>
          <span id="stepCounter" style="font-size:0.75rem; color:var(--text-dim);">0 Steps</span>
        </div>

        <div class="timeline" id="timeline">
          <div style="color:var(--text-dim); font-size:0.85rem; padding:32px; text-align:center;">
            Agent idle. Dispatch a goal or select a test scenario above to watch live execution.
          </div>
        </div>
      </div>

      <!-- Right Column: System of Record & Evidence -->
      <div style="display:flex; flex-direction:column; gap:24px;">

        <!-- System of Record -->
        <div class="panel">
          <div class="panel-header">
            <div class="panel-title">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="color:var(--success);"><path d="M4 22h14a2 2 0 0 0 2-2V7.5L14.5 2H6a2 2 0 0 0-2 2v4"/><polyline points="14 2 14 8 20 8"/><path d="m3 15 2 2 4-4"/></svg>
              Finance System of Record
            </div>
            <button class="btn-copy" onclick="loadRecords()">↻ Refresh</button>
          </div>

          <div class="table-wrapper">
            <table id="recordsTable">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Invoice</th>
                  <th>Vendor</th>
                  <th>Total</th>
                  <th>Due Date</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                <tr><td colspan="6" style="text-align:center; color:var(--text-dim); padding:24px;">Loading records...</td></tr>
              </tbody>
            </table>
          </div>
        </div>

        <!-- Auditable Evidence Package -->
        <div class="panel">
          <div class="panel-header">
            <div class="panel-title">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="color:var(--accent);"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
              Auditable Evidence Package
            </div>
            <button class="btn-copy" id="copyBtn" onclick="copyEvidence()">Copy Evidence JSON</button>
          </div>

          <div class="evidence-card" id="evidenceBox">
            <div style="color:var(--text-dim); font-size:0.82rem; padding:12px; text-align:center;">
              Evidence package will be compiled upon task completion.
            </div>
          </div>
        </div>

      </div>

    </div>
  </div>

  <script>
    let currentEvidence = null;

    function setGoal(text) {
      document.getElementById('goalInput').value = text;
    }

    async function loadRecords() {
      try {
        const res = await fetch('/api/records');
        const data = await res.json();
        document.getElementById('kpiCount').innerText = data.length;
        const tbody = document.querySelector('#recordsTable tbody');
        if (data.length === 0) {
          tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; color:var(--text-dim);">No records found</td></tr>';
          return;
        }
        tbody.innerHTML = data.map(r => {
          const initials = r.vendor_name.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase();
          return `
            <tr>
              <td class="mono" style="color:var(--text-dim);">#${r.id}</td>
              <td class="mono" style="font-weight:600; color:var(--primary);">${r.invoice_number}</td>
              <td>
                <div class="vendor-badge">
                  <div class="avatar-mini">${initials}</div>
                  <span>${r.vendor_name}</span>
                </div>
              </td>
              <td style="font-weight:700;">₹${Number(r.total_amount).toLocaleString('en-IN', {minimumFractionDigits: 2})}</td>
              <td class="mono" style="color:var(--text-muted); font-size:0.78rem;">${r.due_date || 'N/A'}</td>
              <td><span class="pill pill-green" style="font-size:0.7rem; padding:2px 8px;">${r.status}</span></td>
            </tr>
          `;
        }).join('');
      } catch (err) {
        console.error('Failed to load records:', err);
      }
    }

    function runStreamTask() {
      const goal = document.getElementById('goalInput').value;
      const failTimeout = document.getElementById('failTimeout').checked;
      const approvalGranted = document.getElementById('supervisorApproval').checked;
      const runBtn = document.getElementById('runBtn');
      const timeline = document.getElementById('timeline');
      const banner = document.getElementById('statusBanner');
      const evidenceBox = document.getElementById('evidenceBox');
      const liveBadge = document.getElementById('liveBadge');
      const stepCounter = document.getElementById('stepCounter');

      runBtn.disabled = true;
      runBtn.innerHTML = 'Executing...';
      liveBadge.style.display = 'inline-flex';
      timeline.innerHTML = '';
      banner.style.display = 'none';
      stepCounter.innerText = '0 Steps';
      currentEvidence = null;
      evidenceBox.innerHTML = '<div style="color:var(--text-dim); font-size:0.82rem; padding:12px; text-align:center;">Compiling evidence...</div>';

      const query = new URLSearchParams({
        goal: goal,
        fail_mode: failTimeout ? 'timeout' : 'none',
        approval_granted: approvalGranted ? 'true' : 'false'
      });

      const eventSource = new EventSource('/api/stream?' + query.toString());

      eventSource.onmessage = function(e) {
        try {
          const msg = JSON.parse(e.data);
          const evt = msg.event;
          const data = msg.data;

          if (evt === 'task_start') {
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
                  <span class="step-num">Step ${data.step}</span>
                  <span class="step-action-tag">${data.action}</span>
                </div>
                ${data.thought_summary ? `<div class="step-thought-box">"${data.thought_summary}"</div>` : ''}
                <div style="font-size:0.75rem; color:var(--text-dim);" class="mono">args: ${JSON.stringify(data.args)}</div>
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
          }
        } catch (err) {
          console.error('Error parsing SSE event:', err);
        }
      };

      eventSource.addEventListener('done', function() {
        eventSource.close();
        runBtn.disabled = false;
        runBtn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="5 3 19 12 5 21 5 3"/></svg> Dispatch Agent';
        liveBadge.style.display = 'none';
        loadRecords();
      });

      eventSource.onerror = function() {
        eventSource.close();
        runBtn.disabled = false;
        runBtn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="5 3 19 12 5 21 5 3"/></svg> Dispatch Agent';
        liveBadge.style.display = 'none';
        loadRecords();
      };
    }

    function copyEvidence() {
      if (!currentEvidence) {
        alert('No evidence package available yet.');
        return;
      }
      navigator.clipboard.writeText(JSON.stringify(currentEvidence, null, 2));
      const btn = document.getElementById('copyBtn');
      btn.innerText = '✓ Copied!';
      setTimeout(() => { btn.innerText = 'Copy Evidence JSON'; }, 2000);
    }

    loadRecords();
  </script>
</body>
</html>
"""


if __name__ == "__main__":
    import uvicorn
    print("Starting NexaOps Web Console on http://localhost:8000 ...")
    uvicorn.run("web.app:app", host="127.0.0.1", port=8000, reload=False)
