"""
Task State Model for NexaOps.
Maintains full operational context: goal, step counter, history, observations,
human approvals, verification status, and final evidence package.
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
import uuid


class StepRecord(BaseModel):
    """Record of a single execution step taken by the agent."""
    step: int
    thought_summary: str
    action: str
    args: Dict[str, Any] = Field(default_factory=dict)
    observation: Optional[Dict[str, Any]] = None
    status: str = "COMPLETED"


class TaskState(BaseModel):
    """Complete in-flight state of an autonomous task."""
    task_id: str = Field(default_factory=lambda: f"task-{uuid.uuid4().hex[:8]}")
    goal: str
    status: str = "PLANNING"  # PLANNING, RUNNING, WAITING_FOR_APPROVAL, COMPLETED, FAILED, NEEDS_INPUT, REJECTED
    current_step: int = 0
    max_steps: int = 15

    # History of steps taken
    history: List[StepRecord] = Field(default_factory=list)

    # Deterministic guardrail states
    # Key: invoice_number, Value: True (approved) / False (rejected)
    approval_status: Dict[str, bool] = Field(default_factory=dict)

    # List of invoice numbers that have passed independent verification
    verified_records: List[str] = Field(default_factory=list)

    # In-memory working data extracted during the task
    extracted_data: Dict[str, Any] = Field(default_factory=dict)

    # Retry count tracker per tool (for transient timeouts)
    retries: Dict[str, int] = Field(default_factory=dict)

    # Final result summary and audit evidence
    summary: Optional[str] = None
    evidence: Optional[Dict[str, Any]] = None

    def add_step(
        self,
        thought_summary: str,
        action: str,
        args: Dict[str, Any],
        observation: Optional[Dict[str, Any]] = None,
        status: str = "COMPLETED"
    ) -> StepRecord:
        """Appends a new step record to the state."""
        self.current_step += 1
        record = StepRecord(
            step=self.current_step,
            thought_summary=thought_summary,
            action=action,
            args=args,
            observation=observation,
            status=status
        )
        self.history.append(record)
        return record

    def get_recent_history_summary(self, max_items: int = 5) -> List[Dict[str, Any]]:
        """Returns the most recent steps formatted for LLM context."""
        recent = self.history[-max_items:] if self.history else []
        return [
            {
                "step": s.step,
                "action": s.action,
                "args": s.args,
                "result": s.observation.get("message") if s.observation else None,
                "ok": s.observation.get("ok") if s.observation else False
            }
            for s in recent
        ]
