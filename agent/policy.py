"""
Deterministic Policy Engine for NexaOps.
Enforces:
- Tool allowlist (no unauthorized or dangerous tools).
- Pydantic schema validation for arguments.
- Mandatory supervisor approval for invoices >= APPROVAL_THRESHOLD ($10,000).
- Mandatory independent verification before 'finish' is permitted.
- Prompt injection immunity: untrusted text never overrides deterministic policy.
"""

import os
from typing import Dict, Any, Tuple, Optional
from pydantic import ValidationError
from tools.registry import registry
from agent.state import TaskState

DEFAULT_APPROVAL_THRESHOLD = 50000.0


def get_approval_threshold() -> float:
    """Reads configurable approval threshold from environment or defaults to ₹50,000."""
    try:
        return float(os.getenv("INVOICE_APPROVAL_THRESHOLD", str(DEFAULT_APPROVAL_THRESHOLD)))
    except ValueError:
        return DEFAULT_APPROVAL_THRESHOLD


class PolicyEngine:
    """Validates proposed LLM actions against deterministic enterprise rules."""

    @classmethod
    def validate_action(
        cls,
        state: TaskState,
        action: str,
        args: Dict[str, Any]
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Validates proposed action.
        Returns:
            (True, None) if compliant.
            (False, observation_dict) if violated.
        """
        threshold = get_approval_threshold()

        # 1. ALLOWLIST CHECK
        system_actions = {"finish", "ask_user"}
        registered_tools = {t.name for t in registry.list_tools()}
        allowed_actions = system_actions.union(registered_tools)

        if action not in allowed_actions:
            return False, {
                "ok": False,
                "data": None,
                "error_type": "policy_forbidden_tool",
                "message": f"Policy rejection: Tool '{action}' is not in the approved tool allowlist. Allowed tools are: {', '.join(sorted(allowed_actions))}."
            }

        # 2. SCHEMA VALIDATION FOR REGISTERED TOOLS
        if action in registered_tools:
            tool_def = registry.get(action)
            if tool_def and tool_def.input_schema:
                try:
                    # Validate schema
                    tool_def.input_schema.model_validate(args)
                except ValidationError as e:
                    return False, {
                        "ok": False,
                        "data": None,
                        "error_type": "invalid_tool_arguments",
                        "message": f"Policy rejection: Invalid arguments for '{action}': {str(e.errors()[0].get('msg', 'Validation error'))}."
                    }

        # 3. GUARDRAIL: create_finance_record policy
        if action == "create_finance_record":
            invoice_num = args.get("invoice_number", "")
            amount = float(args.get("amount", 0.0))
            due_date = args.get("due_date")

            # Check for missing required due_date
            if not due_date or str(due_date).strip().lower() in ["none", "null", "not specified", "undefined"]:
                return False, {
                    "ok": False,
                    "data": None,
                    "error_type": "missing_required_data",
                    "message": "Policy rejection: 'due_date' is required for finance records and cannot be null or fabricated. Ask user for clarification or fail safely."
                }

            # Check approval threshold rule
            if amount >= threshold:
                is_approved = state.approval_status.get(invoice_num, False)
                if not is_approved:
                    return False, {
                        "ok": False,
                        "data": {"requires_approval": True, "threshold": threshold, "amount": amount},
                        "error_type": "approval_required",
                        "message": f"Policy rejection: Invoice {invoice_num} total (₹{amount:,.2f}) meets or exceeds the ₹{threshold:,.2f} approval threshold. You MUST call 'request_approval' first before creating a record."
                    }

        # 4. GUARDRAIL: 'finish' policy
        if action == "finish":
            # If the task was processing an invoice (extracted data exists),
            # verify that independent verification succeeded
            inv_num = state.extracted_data.get("invoice_number")
            if inv_num:
                if inv_num not in state.verified_records:
                    return False, {
                        "ok": False,
                        "data": None,
                        "error_type": "verification_required",
                        "message": f"Policy rejection: Cannot finish task for invoice '{inv_num}' until 'verify_finance_record' has been executed and passed."
                    }

        # Action satisfies all policy checks
        return True, None
