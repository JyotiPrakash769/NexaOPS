"""
Autonomous Agent Controller for NexaOps.
Deterministic Python loop that:
1. Builds prompt context (goal, tools, state, history).
2. Calls LLM adapter to propose the next JSON action.
3. Enforces policy validation (allowlist, schemas, approval rules, verification gates).
4. Executes bounded tools and captures structured observations.
5. Handles transient retries (e.g. timeout backoff).
6. Compiles final audit evidence.
"""

import os
import time
from typing import Dict, Any, Optional, Callable
from datetime import datetime, timezone

from agent.state import TaskState
from agent.prompts import SYSTEM_PROMPT, build_user_prompt
from agent.policy import PolicyEngine
from agent.events import EventLogger
from agent.llm import get_llm_adapter
from tools.registry import registry
# Import tools to ensure they are registered
import tools.invoice_tools as invoice_tools

MAX_TOOL_RETRIES = 2


def run_task(
    goal: str,
    max_steps: int = 15,
    fail_mode: Optional[str] = None,
    interactive_approval: bool = True,
    approval_callback: Optional[Callable[[str, float, str], bool]] = None,
    llm_adapter_override: Optional[Any] = None,
    event_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    verbose: bool = True
) -> TaskState:
    """
    Executes an autonomous task loop against the goal.
    Returns the completed TaskState.
    """
    if fail_mode:
        os.environ["FAIL_MODE"] = fail_mode

    # Set interactive approval callback if provided
    if approval_callback is not None:
        invoice_tools.approval_interactive_callback = approval_callback

    state = TaskState(goal=goal, max_steps=max_steps, status="PLANNING")
    logger = EventLogger(task_id=state.task_id, verbose=verbose)
    logger.log_task_start(goal)

    if event_callback:
        event_callback("task_start", {"task_id": state.task_id, "goal": goal})

    llm = llm_adapter_override or get_llm_adapter()
    tool_catalog = registry.get_catalog_for_prompt()

    state.status = "RUNNING"

    while state.current_step < state.max_steps:
        step_number = state.current_step + 1

        # 1. Build prompt context
        state_summary = {
            "current_step": state.current_step,
            "max_steps": state.max_steps,
            "goal": state.goal,
            "approval_status": state.approval_status,
            "verified_records": state.verified_records,
            "extracted_data": state.extracted_data,
            "recent_history": state.get_recent_history_summary()
        }

        user_prompt = build_user_prompt(
            goal=state.goal,
            tool_catalog=tool_catalog,
            state_summary=state_summary,
            recent_history=state.get_recent_history_summary()
        )

        # 2. Get next proposed action from LLM
        try:
            proposed = llm.generate_action(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=user_prompt,
                state_summary=state_summary
            )
        except Exception as e:
            # LLM adapter error / malformed response
            obs = {
                "ok": False,
                "data": None,
                "error_type": "llm_generation_error",
                "message": f"LLM generation failed: {str(e)}"
            }
            state.add_step(
                thought_summary="LLM failed to return structured action.",
                action="none",
                args={},
                observation=obs,
                status="FAILED"
            )
            logger.log_observation(step_number, "none", obs, status="FAILED")
            continue

        thought_summary = proposed.get("thought_summary", "")
        action = proposed.get("action", "")
        args = proposed.get("args", {})

        logger.log_step(step_number, thought_summary, action, args)

        if event_callback:
            event_callback("step_planned", {
                "step": step_number,
                "thought_summary": thought_summary,
                "action": action,
                "args": args
            })

        # 3. Policy Engine Validation
        is_valid, policy_rejection = PolicyEngine.validate_action(state, action, args)
        if not is_valid:
            logger.log_policy_rejection(step_number, action, policy_rejection["message"])
            state.add_step(
                thought_summary=thought_summary,
                action=action,
                args=args,
                observation=policy_rejection,
                status="REJECTED_BY_POLICY"
            )
            if event_callback:
                event_callback("policy_rejection", {
                    "step": step_number,
                    "action": action,
                    "rejection": policy_rejection
                })
            # Rejection is fed back as an observation so the agent adapts on next loop
            continue

        # 4. Handle System Actions: finish or ask_user
        if action == "finish":
            summary = args.get("summary", "Task completed successfully.")
            state.summary = summary
            state.status = "COMPLETED"

            # Assemble evidence package
            inv_data = state.extracted_data or {}
            inv_num = inv_data.get("invoice_number", "N/A")
            state.evidence = {
                "invoice_number": inv_num,
                "file": inv_data.get("file", "N/A"),
                "vendor": inv_data.get("vendor_name", "N/A"),
                "amount": inv_data.get("total_amount", "N/A"),
                "currency": inv_data.get("currency", "USD"),
                "approved_by_supervisor": state.approval_status.get(inv_num, False),
                "verified": inv_num in state.verified_records,
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "total_steps": state.current_step
            }

            logger.log_task_finish(state.status, summary, state.evidence)
            if event_callback:
                event_callback("task_finish", {
                    "task_id": state.task_id,
                    "status": state.status,
                    "summary": summary,
                    "evidence": state.evidence
                })
            return state

        if action == "ask_user":
            question = args.get("question", "Clarification requested.")
            state.summary = f"Agent paused for user clarification: {question}"
            state.status = "NEEDS_INPUT"
            state.add_step(
                thought_summary=thought_summary,
                action=action,
                args=args,
                observation={"ok": True, "data": question, "message": "User clarification requested."},
                status="NEEDS_INPUT"
            )
            logger.log_task_finish(state.status, state.summary)
            if event_callback:
                event_callback("task_finish", {
                    "task_id": state.task_id,
                    "status": state.status,
                    "summary": state.summary,
                    "evidence": None
                })
            return state

        # 5. Execute Registered Tool
        tool_def = registry.get(action)
        if not tool_def:
            obs = {"ok": False, "data": None, "error_type": "tool_not_found", "message": f"Tool '{action}' not found."}
            state.add_step(thought_summary, action, args, obs, "FAILED")
            continue

        # Execute with transient retry support
        observation = tool_def.func(**args)

        # Retry transient timeouts
        if observation.get("error_type") == "timeout" and tool_def.retryable:
            retries_done = state.retries.get(action, 0)
            if retries_done < MAX_TOOL_RETRIES:
                state.retries[action] = retries_done + 1
                if verbose:
                    print(f" [TRANSIENT RETRY] '{action}' timed out. Retrying (attempt {state.retries[action]}/{MAX_TOOL_RETRIES}) after backoff...")
                time.sleep(0.3)
                observation = tool_def.func(**args)

        logger.log_observation(step_number, action, observation)
        if event_callback:
            event_callback("observation", {
                "step": step_number,
                "action": action,
                "observation": observation
            })

        # 6. Update State Invariants based on Tool Results
        if action == "extract_invoice_data" and observation.get("ok"):
            state.extracted_data = observation.get("data", {})

        elif action == "request_approval":
            inv_num = args.get("invoice_number", "")
            if observation.get("ok"):
                state.approval_status[inv_num] = True
            else:
                state.approval_status[inv_num] = False
                state.status = "REJECTED"
                state.summary = f"Task aborted: Human supervisor rejected approval for invoice {inv_num}."
                state.add_step(thought_summary, action, args, observation, status="REJECTED")
                logger.log_task_finish(state.status, state.summary)
                if event_callback:
                    event_callback("task_finish", {
                        "task_id": state.task_id,
                        "status": state.status,
                        "summary": state.summary,
                        "evidence": None
                    })
                return state

        elif action == "verify_finance_record":
            inv_num = args.get("invoice_number", "")
            if observation.get("ok"):
                if inv_num not in state.verified_records:
                    state.verified_records.append(inv_num)
            else:
                # Verification mismatch detected
                if observation.get("error_type") == "verification_mismatch":
                    state.status = "FAILED"
                    state.summary = f"Verification Mismatch: {observation.get('message')}"
                    state.add_step(thought_summary, action, args, observation, status="VERIFICATION_FAILED")
                    logger.log_task_finish(state.status, state.summary)
                    if event_callback:
                        event_callback("task_finish", {
                            "task_id": state.task_id,
                            "status": state.status,
                            "summary": state.summary,
                            "evidence": None
                        })
                    return state

        # Add step record
        state.add_step(thought_summary, action, args, observation, status="COMPLETED" if observation.get("ok") else "FAILED")

    # If loop exited because step cap was reached:
    state.status = "FAILED"
    state.summary = f"Task exceeded maximum step limit ({state.max_steps}) without completion."
    logger.log_task_finish(state.status, state.summary)
    if event_callback:
        event_callback("task_finish", {
            "task_id": state.task_id,
            "status": state.status,
            "summary": state.summary,
            "evidence": None
        })
    return state
