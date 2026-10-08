"""
Single-Page FastAPI Web Viewer for NexaOps.
Provides an interactive dashboard to:
1. Submit business goals (or choose demo presets).
2. Watch the agent loop execute in real time.
3. View the finance system of record records.
4. Inspect the persistent audit trail.
"""

import sys
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any, List

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
    return {"status": "ok", "product": "NexaOps"}


@app.get("/api/records")
def get_records():
    return finance_db.list_records()


@app.get("/api/audit")
def get_audit(task_id: Optional[str] = None):
    if task_id:
        return finance_db.get_audit_events(task_id)
    # Return last 50 audit events from DB
    conn = finance_db.get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM audit_events ORDER BY id DESC LIMIT 50")
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.post("/api/run")
def api_run_task(req: RunTaskRequest):
    def approval_mock(inv_num, amount, reason):
        return req.approval_granted

    state = run_task(
        goal=req.goal,
        fail_mode=req.fail_mode,
        approval_callback=approval_mock,
        verbose=False
    )

    return {
        "task_id": state.task_id,
        "goal": state.goal,
        "status": state.status,
        "summary": state.summary,
        "evidence": state.evidence,
        "steps": [s.model_dump() for s in state.history]
    }


@app.get("/", response_class=HTMLResponse)
def index_view():
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>NexaOps — Autonomous AI Operations Console</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <style>
    :root {
      --bg: #0f172a;
      --card: #1e293b;
      --border: #334155;
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --primary: #38bdf8;
      --success: #4ade80;
      --warning: #facc15;
      --danger: #f87171;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
    body { background-color: var(--bg); color: var(--text); padding: 24px; line-height: 1.5; }
    header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border); padding-bottom: 16px; margin-bottom: 24px; }
    h1 { font-size: 1.5rem; font-weight: 700; color: var(--primary); display: flex; align-items: center; gap: 8px; }
    .badge { background: #0369a1; color: #e0f2fe; padding: 2px 8px; border-radius: 9999px; font-size: 0.75rem; }
    .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }
    .card { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 20px; }
    h2 { font-size: 1.1rem; margin-bottom: 16px; color: var(--text); border-bottom: 1px solid var(--border); padding-bottom: 8px; }
    .presets { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
    button.preset-btn { background: #334155; color: #e2e8f0; border: none; padding: 6px 12px; border-radius: 6px; font-size: 0.8rem; cursor: pointer; transition: background 0.15s; }
    button.preset-btn:hover { background: #475569; }
    .input-group { display: flex; gap: 8px; margin-bottom: 12px; }
    input[type="text"] { flex: 1; background: #0f172a; border: 1px solid var(--border); border-radius: 6px; padding: 10px 14px; color: var(--text); font-size: 0.9rem; }
    input[type="text"]:focus { outline: none; border-color: var(--primary); }
    button.primary-btn { background: #0284c7; color: white; border: none; padding: 10px 20px; border-radius: 6px; font-weight: 600; cursor: pointer; }
    button.primary-btn:hover { background: #0369a1; }
    .timeline { display: flex; flex-direction: column; gap: 12px; max-height: 480px; overflow-y: auto; padding-right: 4px; }
    .step-item { background: #0f172a; border-left: 3px solid var(--primary); border-radius: 4px; padding: 10px 14px; font-size: 0.85rem; }
    .step-header { display: flex; justify-content: space-between; margin-bottom: 4px; font-weight: 600; }
    .step-action { color: var(--primary); }
    .step-thought { color: var(--text-muted); font-style: italic; margin-bottom: 4px; }
    .step-obs { color: var(--text); background: rgba(255,255,255,0.03); padding: 4px 8px; border-radius: 4px; }
    .table-container { max-height: 240px; overflow-y: auto; }
    table { width: 100%; border-collapse: collapse; font-size: 0.8rem; }
    th, td { text-align: left; padding: 8px; border-bottom: 1px solid var(--border); }
    th { color: var(--text-muted); font-weight: 600; }
    .status-completed { color: var(--success); font-weight: 600; }
    .status-rejected { color: var(--danger); font-weight: 600; }
    .status-needs_input { color: var(--warning); font-weight: 600; }
    pre { background: #0f172a; padding: 10px; border-radius: 6px; font-size: 0.75rem; overflow-x: auto; color: #38bdf8; }
  </style>
</head>
<body>
  <header>
    <h1>NexaOps <span class="badge">Autonomous Employee Console</span></h1>
    <span style="font-size: 0.85rem; color: var(--text-muted);">CentrAlign AI Founding Engineer Take-Home</span>
  </header>

  <div class="grid">
    <!-- Left Column: Task Execution -->
    <div class="card">
      <h2>1. Task Controller</h2>
      <div class="presets">
        <button class="preset-btn" onclick="setGoal('Process the latest invoice from ABC Technologies')">Happy Path (ABC)</button>
        <button class="preset-btn" onclick="setGoal('Process the latest invoice from Delta Systems')">Approval &gt; $10k (Delta)</button>
        <button class="preset-btn" onclick="setGoal('Process the latest invoice from XYZ Solutions')">Duplicate (XYZ)</button>
        <button class="preset-btn" onclick="setGoal('Process the latest invoice from Acme Corp')">Missing Due Date (Acme)</button>
        <button class="preset-btn" onclick="setGoal('List all invoices from ABC Technologies')">Generalization (List)</button>
      </div>

      <div class="input-group">
        <input type="text" id="goalInput" value="Process the latest invoice from ABC Technologies">
        <button class="primary-btn" id="runBtn" onclick="runTask()">Dispatch Agent</button>
      </div>

      <div style="margin-bottom: 16px; font-size: 0.8rem; color: var(--text-muted); display: flex; gap: 16px;">
        <label><input type="checkbox" id="failTimeout"> Simulate Timeout (504)</label>
        <label><input type="checkbox" id="supervisorApproval" checked> Grant Supervisor Approval</label>
      </div>

      <div id="statusBanner" style="display:none; padding: 10px; border-radius: 6px; margin-bottom: 12px; font-size: 0.85rem;"></div>

      <h3 style="font-size: 0.95rem; margin-bottom: 8px;">Execution Timeline</h3>
      <div class="timeline" id="timeline">
        <div style="color: var(--text-muted); font-size: 0.85rem; padding: 20px; text-align: center;">
          Ready to dispatch. Select a preset or type a goal above.
        </div>
      </div>
    </div>

    <!-- Right Column: Database & Evidence -->
    <div style="display: flex; flex-direction: column; gap: 24px;">
      <div class="card">
        <h2>2. Finance System of Record (SQLite)</h2>
        <div class="table-container">
          <table id="recordsTable">
            <thead>
              <tr><th>ID</th><th>Invoice #</th><th>Vendor</th><th>Amount</th><th>Due Date</th><th>Status</th></tr>
            </thead>
            <tbody>
              <tr><td colspan="6" style="text-align: center; color: var(--text-muted);">Loading records...</td></tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="card">
        <h2>3. Auditable Evidence Package</h2>
        <div id="evidenceBox">
          <div style="color: var(--text-muted); font-size: 0.85rem;">No task completed yet.</div>
        </div>
      </div>
    </div>
  </div>

  <script>
    function setGoal(text) {
      document.getElementById('goalInput').value = text;
    }

    async function loadRecords() {
      try {
        const res = await fetch('/api/records');
        const data = await res.json();
        const tbody = document.querySelector('#recordsTable tbody');
        if (data.length === 0) {
          tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;">No records yet</td></tr>';
          return;
        }
        tbody.innerHTML = data.map(r => `
          <tr>
            <td>#${r.id}</td>
            <td><strong>${r.invoice_number}</strong></td>
            <td>${r.vendor_name}</td>
            <td>$${Number(r.total_amount).toLocaleString('en-US', {minimumFractionDigits: 2})}</td>
            <td>${r.due_date || 'N/A'}</td>
            <td><span class="badge" style="background:#059669;">${r.status}</span></td>
          </tr>
        `).join('');
      } catch (err) {
        console.error('Failed to load records:', err);
      }
    }

    async function runTask() {
      const goal = document.getElementById('goalInput').value;
      const failTimeout = document.getElementById('failTimeout').checked;
      const approvalGranted = document.getElementById('supervisorApproval').checked;
      const runBtn = document.getElementById('runBtn');
      const timeline = document.getElementById('timeline');
      const banner = document.getElementById('statusBanner');
      const evidenceBox = document.getElementById('evidenceBox');

      runBtn.disabled = true;
      runBtn.innerText = 'Agent Running...';
      timeline.innerHTML = '<div style="color: var(--primary); padding: 20px; text-align: center;">Agent is planning and executing tools...</div>';
      banner.style.display = 'none';

      try {
        const res = await fetch('/api/run', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            goal: goal,
            fail_mode: failTimeout ? 'timeout' : null,
            approval_granted: approvalGranted
          })
        });
        const data = await res.json();

        // Render Status Banner
        banner.style.display = 'block';
        if (data.status === 'COMPLETED') {
          banner.style.background = 'rgba(74, 222, 128, 0.15)';
          banner.style.border = '1px solid var(--success)';
          banner.innerHTML = `<span class="status-completed">[TASK COMPLETED]</span> ${data.summary}`;
        } else if (data.status === 'REJECTED') {
          banner.style.background = 'rgba(248, 113, 113, 0.15)';
          banner.style.border = '1px solid var(--danger)';
          banner.innerHTML = `<span class="status-rejected">[TASK REJECTED]</span> ${data.summary}`;
        } else {
          banner.style.background = 'rgba(250, 204, 21, 0.15)';
          banner.style.border = '1px solid var(--warning)';
          banner.innerHTML = `<span class="status-needs_input">[TASK ${data.status}]</span> ${data.summary}`;
        }

        // Render Timeline
        if (data.steps && data.steps.length > 0) {
          timeline.innerHTML = data.steps.map(s => `
            <div class="step-item">
              <div class="step-header">
                <span>Step ${s.step}: <span class="step-action">${s.action}</span></span>
                <span class="badge" style="background:#1e293b; border:1px solid #475569;">${s.status}</span>
              </div>
              ${s.thought_summary ? `<div class="step-thought">"${s.thought_summary}"</div>` : ''}
              <div class="step-obs"><strong>Observation:</strong> ${s.observation ? s.observation.message : 'N/A'}</div>
            </div>
          `).join('');
        } else {
          timeline.innerHTML = '<div style="padding:10px;">No steps recorded.</div>';
        }

        // Render Evidence Box
        if (data.evidence) {
          evidenceBox.innerHTML = `<pre>${JSON.stringify(data.evidence, null, 2)}</pre>`;
        } else {
          evidenceBox.innerHTML = `<div style="color: var(--text-muted); font-size: 0.85rem;">${data.summary}</div>`;
        }

        // Refresh database records
        await loadRecords();
      } catch (err) {
        timeline.innerHTML = `<div style="color:var(--danger); padding:20px;">Execution failed: ${err.message}</div>`;
      } finally {
        runBtn.disabled = false;
        runBtn.innerText = 'Dispatch Agent';
      }
    }

    // Load initial records on page load
    loadRecords();
  </script>
</body>
</html>
"""


if __name__ == "__main__":
    import uvicorn
    print("Starting NexaOps Web Console on http://localhost:8000 ...")
    uvicorn.run("web.app:app", host="127.0.0.1", port=8000, reload=False)
