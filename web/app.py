"""
Single-Page FastAPI Web Viewer for NexaOps with Real-Time SSE Streaming.
Provides an interactive dashboard to:
1. Submit business goals (or choose demo presets).
2. Watch the agent loop execute in REAL TIME via Server-Sent Events (SSE).
3. View the finance system of record records.
4. Inspect the persistent audit trail.
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
    return {"status": "ok", "product": "NexaOps"}


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
  <title>NexaOps — Autonomous AI Operations Console (Live SSE)</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <style>
    :root {
      --bg: #0b1120;
      --card: #151e34;
      --border: #22304e;
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
    h1 { font-size: 1.5rem; font-weight: 700; color: var(--primary); display: flex; align-items: center; gap: 10px; }
    .badge { background: #0369a1; color: #e0f2fe; padding: 3px 10px; border-radius: 9999px; font-size: 0.75rem; font-weight: 600; }
    .badge-live { background: #065f46; color: #6ee7b7; border: 1px solid #10b981; animation: pulse 1.5s infinite; }
    @keyframes pulse { 0% { opacity: 0.7; } 50% { opacity: 1; } 100% { opacity: 0.7; } }
    .grid { display: grid; grid-template-columns: 1.1fr 0.9fr; gap: 24px; }
    .card { background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 20px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.2); }
    h2 { font-size: 1.1rem; margin-bottom: 16px; color: var(--text); border-bottom: 1px solid var(--border); padding-bottom: 8px; display: flex; justify-content: space-between; align-items: center; }
    .presets { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 14px; }
    button.preset-btn { background: #1e293b; color: #cbd5e1; border: 1px solid var(--border); padding: 6px 12px; border-radius: 6px; font-size: 0.8rem; cursor: pointer; transition: all 0.15s; }
    button.preset-btn:hover { background: #334155; color: white; border-color: var(--primary); }
    .input-group { display: flex; gap: 8px; margin-bottom: 12px; }
    input[type="text"] { flex: 1; background: #0b1120; border: 1px solid var(--border); border-radius: 6px; padding: 10px 14px; color: var(--text); font-size: 0.9rem; }
    input[type="text"]:focus { outline: none; border-color: var(--primary); box-shadow: 0 0 0 2px rgba(56,189,248,0.2); }
    button.primary-btn { background: #0284c7; color: white; border: none; padding: 10px 20px; border-radius: 6px; font-weight: 600; cursor: pointer; transition: background 0.15s; }
    button.primary-btn:hover { background: #0369a1; }
    button.primary-btn:disabled { opacity: 0.6; cursor: not-allowed; }
    .timeline { display: flex; flex-direction: column; gap: 12px; max-height: 520px; overflow-y: auto; padding-right: 4px; }
    .step-item { background: #0b1120; border-left: 3px solid var(--primary); border-radius: 6px; padding: 12px 14px; font-size: 0.85rem; animation: slideIn 0.25s ease-out; }
    @keyframes slideIn { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }
    .step-header { display: flex; justify-content: space-between; margin-bottom: 4px; font-weight: 600; }
    .step-action { color: var(--primary); font-family: monospace; font-size: 0.9rem; }
    .step-thought { color: #93c5fd; font-style: italic; margin-bottom: 6px; background: rgba(56,189,248,0.06); padding: 6px 10px; border-radius: 4px; }
    .step-obs { color: var(--text); background: rgba(255,255,255,0.04); padding: 6px 10px; border-radius: 4px; margin-top: 6px; border-left: 2px solid var(--success); }
    .step-obs.obs-fail { border-left-color: var(--warning); }
    .table-container { max-height: 260px; overflow-y: auto; }
    table { width: 100%; border-collapse: collapse; font-size: 0.8rem; }
    th, td { text-align: left; padding: 9px; border-bottom: 1px solid var(--border); }
    th { color: var(--text-muted); font-weight: 600; position: sticky; top: 0; background: var(--card); }
    .status-completed { color: var(--success); font-weight: 700; }
    .status-rejected { color: var(--danger); font-weight: 700; }
    .status-needs_input { color: var(--warning); font-weight: 700; }
    pre { background: #0b1120; padding: 12px; border-radius: 6px; font-size: 0.8rem; overflow-x: auto; color: #38bdf8; border: 1px solid var(--border); }
  </style>
</head>
<body>
  <header>
    <h1>NexaOps <span class="badge">Autonomous Employee</span> <span class="badge" style="background:#475569;">FastAPI + SSE Stream</span></h1>
    <span style="font-size: 0.85rem; color: var(--text-muted);">CentrAlign AI Founding Engineer Take-Home</span>
  </header>

  <div class="grid">
    <!-- Left Column: Task Execution -->
    <div class="card">
      <h2>
        <span>1. Live Agent Controller</span>
        <span id="liveIndicator" style="display:none;" class="badge badge-live">● LIVE STREAMING</span>
      </h2>
      <div class="presets">
        <button class="preset-btn" onclick="setGoal('Process the latest invoice from ABC Technologies')">Happy Path (ABC)</button>
        <button class="preset-btn" onclick="setGoal('Process the latest invoice from Delta Systems')">Approval &gt; $10k (Delta)</button>
        <button class="preset-btn" onclick="setGoal('Process the latest invoice from XYZ Solutions')">Duplicate (XYZ)</button>
        <button class="preset-btn" onclick="setGoal('Process the latest invoice from Acme Corp')">Missing Due Date (Acme)</button>
        <button class="preset-btn" onclick="setGoal('List all invoices from ABC Technologies')">Generalization (List)</button>
      </div>

      <div class="input-group">
        <input type="text" id="goalInput" value="Process the latest invoice from ABC Technologies">
        <button class="primary-btn" id="runBtn" onclick="runStreamTask()">Dispatch Agent (Stream)</button>
      </div>

      <div style="margin-bottom: 16px; font-size: 0.8rem; color: var(--text-muted); display: flex; gap: 16px;">
        <label><input type="checkbox" id="failTimeout"> Simulate Timeout (504)</label>
        <label><input type="checkbox" id="supervisorApproval" checked> Grant Supervisor Approval</label>
      </div>

      <div id="statusBanner" style="display:none; padding: 12px; border-radius: 6px; margin-bottom: 14px; font-size: 0.85rem;"></div>

      <h3 style="font-size: 0.95rem; margin-bottom: 8px; color: var(--text-muted);">Real-Time Execution Timeline</h3>
      <div class="timeline" id="timeline">
        <div style="color: var(--text-muted); font-size: 0.85rem; padding: 24px; text-align: center;">
          Ready to dispatch. Select a preset or type a goal above to watch the agent stream live.
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

    function runStreamTask() {
      const goal = document.getElementById('goalInput').value;
      const failTimeout = document.getElementById('failTimeout').checked;
      const approvalGranted = document.getElementById('supervisorApproval').checked;
      const runBtn = document.getElementById('runBtn');
      const timeline = document.getElementById('timeline');
      const banner = document.getElementById('statusBanner');
      const evidenceBox = document.getElementById('evidenceBox');
      const liveIndicator = document.getElementById('liveIndicator');

      runBtn.disabled = true;
      runBtn.innerText = 'Streaming Agent...';
      liveIndicator.style.display = 'inline-block';
      timeline.innerHTML = '';
      banner.style.display = 'none';
      evidenceBox.innerHTML = '<div style="color:var(--text-muted); font-size:0.85rem;">Awaiting final evidence package...</div>';

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
            timeline.innerHTML += `
              <div style="font-size: 0.8rem; color: var(--text-muted); margin-bottom: 6px; border-bottom: 1px dashed var(--border); padding-bottom: 4px;">
                <strong>Task Initiated:</strong> ${data.task_id}
              </div>
            `;
          } else if (evt === 'step_planned') {
            const stepId = 'step-' + data.step;
            timeline.innerHTML += `
              <div class="step-item" id="${stepId}">
                <div class="step-header">
                  <span>Step ${data.step}: <span class="step-action">${data.action}</span></span>
                  <span class="badge" style="background:#1e293b; border:1px solid #475569;">EXECUTING</span>
                </div>
                ${data.thought_summary ? `<div class="step-thought">"${data.thought_summary}"</div>` : ''}
                <div style="font-size:0.75rem; color:var(--text-muted);">Args: ${JSON.stringify(data.args)}</div>
                <div class="obs-container" id="obs-${data.step}" style="margin-top:6px; color:var(--text-muted); font-size:0.8rem;">Executing tool...</div>
              </div>
            `;
            timeline.scrollTop = timeline.scrollHeight;
          } else if (evt === 'observation') {
            const obsContainer = document.getElementById('obs-' + data.step);
            if (obsContainer) {
              const ok = data.observation.ok;
              obsContainer.className = 'step-obs ' + (ok ? '' : 'obs-fail');
              obsContainer.innerHTML = `<strong>Observation:</strong> [${ok ? 'SUCCESS' : 'OBSERVED'}] ${data.observation.message}`;
            }
            const stepCard = document.getElementById('step-' + data.step);
            if (stepCard) {
              const badge = stepCard.querySelector('.step-header .badge');
              if (badge) {
                badge.innerText = data.observation.ok ? 'COMPLETED' : 'OBSERVED';
                badge.style.background = data.observation.ok ? '#065f46' : '#78350f';
              }
            }
            timeline.scrollTop = timeline.scrollHeight;
          } else if (evt === 'policy_rejection') {
            timeline.innerHTML += `
              <div class="step-item" style="border-left-color: var(--danger); background: rgba(248,113,113,0.05);">
                <div class="step-header">
                  <span style="color:var(--danger); font-weight:700;">[POLICY REJECTION] ${data.action}</span>
                </div>
                <div style="font-size:0.85rem; color:#fca5a5;">${data.rejection.message}</div>
              </div>
            `;
            timeline.scrollTop = timeline.scrollHeight;
          } else if (evt === 'task_finish') {
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

            if (data.evidence) {
              evidenceBox.innerHTML = `<pre>${JSON.stringify(data.evidence, null, 2)}</pre>`;
            } else {
              evidenceBox.innerHTML = `<div style="color: var(--text-muted); font-size: 0.85rem;">${data.summary}</div>`;
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
        runBtn.innerText = 'Dispatch Agent (Stream)';
        liveIndicator.style.display = 'none';
        loadRecords();
      });

      eventSource.onerror = function(err) {
        eventSource.close();
        runBtn.disabled = false;
        runBtn.innerText = 'Dispatch Agent (Stream)';
        liveIndicator.style.display = 'none';
        loadRecords();
      };
    }

    loadRecords();
  </script>
</body>
</html>
"""


if __name__ == "__main__":
    import uvicorn
    print("Starting NexaOps Web Console (with Live SSE Streaming) on http://localhost:8000 ...")
    uvicorn.run("web.app:app", host="127.0.0.1", port=8000, reload=False)
