"""
Event Logging & Audit Trail for NexaOps.
Prints live structured events to the CLI and persists each event into SQLite.
"""

from typing import Dict, Any, Optional
from datetime import datetime
from env import finance_db


class EventLogger:
    """Handles real-time terminal output and persistent audit logging."""

    def __init__(self, task_id: str, verbose: bool = True):
        self.task_id = task_id
        self.verbose = verbose

    def log_task_start(self, goal: str):
        if self.verbose:
            print("\n" + "="*70)
            print(f" [NEXAOPS AGENT] Initializing Task: {self.task_id}")
            print(f" [GOAL] {goal}")
            print("="*70)

    def log_step(
        self,
        step: int,
        thought_summary: str,
        action: str,
        args: Dict[str, Any]
    ):
        if self.verbose:
            print(f"\n--- [STEP {step}] ---")
            if thought_summary:
                print(f" Thought:     {thought_summary}")
            print(f" Action:      {action}")
            print(f" Arguments:   {args}")

    def log_observation(
        self,
        step: int,
        tool: str,
        observation: Dict[str, Any],
        status: str = "COMPLETED"
    ):
        ok = observation.get("ok", False)
        status_tag = "[SUCCESS]" if ok else "[FAILURE/RETRY]"
        msg = observation.get("message", "No message")

        if self.verbose:
            print(f" Observation: {status_tag} {msg}")

        # Persist to database audit log
        try:
            finance_db.log_audit_event(
                task_id=self.task_id,
                step=step,
                tool=tool,
                args={},
                result=observation,
                status=status
            )
        except Exception as e:
            if self.verbose:
                print(f" [WARNING] Could not persist audit event to DB: {e}")

    def log_policy_rejection(self, step: int, action: str, reason: str):
        if self.verbose:
            print(f" [POLICY REJECTION] Action '{action}' was blocked by policy:")
            print(f"   -> {reason}")

    def log_task_finish(self, status: str, summary: str, evidence: Optional[Dict[str, Any]] = None):
        if self.verbose:
            print("\n" + "="*70)
            print(f" [TASK {status}] {self.task_id}")
            print(f" Summary: {summary}")
            if evidence:
                print("\n [EVIDENCE PACKAGE]")
                for k, v in evidence.items():
                    print(f"   - {k}: {v}")
            print("="*70 + "\n")
