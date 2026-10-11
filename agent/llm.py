"""
LLM Provider Adapter for NexaOps.
Supports:
- Gemini (via google-genai or direct API)
- OpenAI (via openai client)
- Fake / Mock LLM (deterministic scripted planner for testing and offline execution)
Extracts and validates structured JSON output: {"thought_summary": ..., "action": ..., "args": ...}.
"""

import os
import re
import json
from typing import Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()


class LLMActionError(Exception):
    """Raised when LLM response cannot be parsed as valid JSON action."""
    pass


def parse_json_action(text: str) -> Dict[str, Any]:
    """Extracts and validates JSON action object from model response text."""
    clean_text = text.strip()

    # Strip markdown code blocks ```json ... ```
    if "```" in clean_text:
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", clean_text)
        if match:
            clean_text = match.group(1).strip()

    try:
        data = json.loads(clean_text)
    except json.JSONDecodeError as e:
        # Try finding the first '{' and last '}'
        start = clean_text.find("{")
        end = clean_text.rfind("}")
        if start != -1 and end != -1:
            try:
                data = json.loads(clean_text[start:end+1])
            except json.JSONDecodeError:
                raise LLMActionError(f"Failed to decode JSON from model response: {e}")
        else:
            raise LLMActionError(f"Failed to find JSON object in model response: {e}")

    if not isinstance(data, dict):
        raise LLMActionError("Model response JSON must be a dictionary object.")

    if "action" not in data:
        raise LLMActionError("Model response JSON missing mandatory 'action' field.")

    data.setdefault("thought_summary", "")
    data.setdefault("args", {})
    return data


class FakeLLMAdapter:
    """
    Deterministic scripted planner that produces the correct actions based on state.
    Enables 100% offline testing, CI verification, and predictable demo execution.
    """

    def generate_action(self, system_prompt: str, user_prompt: str, state_summary: Dict[str, Any]) -> Dict[str, Any]:
        goal = state_summary.get("goal", "").lower()
        extracted = state_summary.get("extracted_data", {})
        recent = state_summary.get("recent_history", [])
        verified_records = state_summary.get("verified_records", [])
        approval_status = state_summary.get("approval_status", {})

        # Task Generalization: "list all unpaid invoices" or "list invoices"
        if "list" in goal and "invoice" in goal:
            # Check if list_invoices was executed
            last_action = recent[-1]["action"] if recent else ""
            if last_action != "list_invoices":
                vendor = "ABC Technologies" if "abc" in goal else None
                return {
                    "thought_summary": "User wants a listing of invoices. Executing list_invoices tool.",
                    "action": "list_invoices",
                    "args": {"vendor": vendor}
                }
            return {
                "thought_summary": "Invoice records retrieved. Completing task.",
                "action": "finish",
                "args": {"summary": "Listed all recorded invoices for the requested vendor."}
            }

        # Standard Invoice Processing Workflow:
        # Step A: Find invoice file if not done yet
        if not extracted or not extracted.get("file"):
            # Check if find_latest_invoice was already run
            found_file_in_recent = None
            for item in recent:
                if item.get("action") == "find_latest_invoice" and item.get("ok"):
                    # Extract file name from previous result
                    res = item.get("result", "")
                    m = re.search(r"'([^']+)'", res)
                    if m:
                        found_file_in_recent = m.group(1)

            if not found_file_in_recent:
                # Check if a specific PDF file was directly referenced in the goal
                direct_file_match = re.search(r"\b([A-Za-z0-9_\-]+\.pdf)\b", goal, re.IGNORECASE)
                if direct_file_match:
                    target_file = direct_file_match.group(1)
                    return {
                        "thought_summary": f"Direct invoice PDF '{target_file}' specified in goal. Extracting invoice data.",
                        "action": "extract_invoice_data",
                        "args": {"file": target_file}
                    }

                # Infer vendor from goal (known presets or arbitrary custom vendor)
                goal_lower = goal.lower()
                if "delta" in goal_lower:
                    vendor = "Delta Systems"
                elif "xyz" in goal_lower:
                    vendor = "XYZ Solutions"
                elif "acme" in goal_lower:
                    vendor = "Acme Corp"
                elif "innotech" in goal_lower:
                    vendor = "InnoTech Security"
                elif "abc" in goal_lower:
                    vendor = "ABC Technologies"
                else:
                    m = re.search(r"(?:from|for|vendor)\s+([A-Za-z0-9_\-\s]+?)(?:\s+invoice|\.pdf|\s+receipt|$)", state_summary.get("goal", ""), re.IGNORECASE)
                    vendor = m.group(1).strip() if m else "ABC Technologies"

                return {
                    "thought_summary": f"Starting task by searching for the latest invoice from {vendor}.",
                    "action": "find_latest_invoice",
                    "args": {"vendor": vendor}
                }
            else:
                return {
                    "thought_summary": f"Extracting invoice fields from PDF file {found_file_in_recent}.",
                    "action": "extract_invoice_data",
                    "args": {"file": found_file_in_recent}
                }

        # Step B: Inspect extracted invoice data
        inv_num = extracted.get("invoice_number")
        vendor_name = extracted.get("vendor_name")
        total_amount = extracted.get("total_amount", 0.0)
        due_date = extracted.get("due_date")

        # Edge case: Missing required fields (e.g. Acme Corp missing due_date)
        if not due_date or str(due_date).lower() in ["none", "null", "not specified"]:
            return {
                "thought_summary": "Invoice is missing required due_date. Refusing to invent data; asking user for clarification.",
                "action": "ask_user",
                "args": {
                    "question": f"Invoice {inv_num} for {vendor_name} is missing a due date. Please provide payment due date."
                }
            }

        # Step C: Check duplicate
        duplicate_checked = any(h.get("action") == "check_duplicate" for h in recent)
        is_duplicate = False
        for h in recent:
            if h.get("action") == "check_duplicate" and h.get("ok"):
                if "already exists" in (h.get("result") or ""):
                    is_duplicate = True

        if not duplicate_checked:
            return {
                "thought_summary": f"Checking if invoice {inv_num} already exists in the finance database.",
                "action": "check_duplicate",
                "args": {"vendor": vendor_name, "invoice_number": inv_num}
            }

        # Step D1: If it's a duplicate, do not insert! Directly verify and finish.
        if is_duplicate:
            if inv_num not in verified_records:
                return {
                    "thought_summary": f"Invoice {inv_num} is a duplicate. Independently verifying existing record before finishing.",
                    "action": "verify_finance_record",
                    "args": {
                        "invoice_number": inv_num,
                        "expected_vendor": vendor_name,
                        "expected_amount": total_amount,
                        "expected_due_date": due_date
                    }
                }
            return {
                "thought_summary": f"Existing duplicate invoice {inv_num} verified in database. Task complete.",
                "action": "finish",
                "args": {"summary": f"Existing record for {inv_num} was found and verified. No duplicate created."}
            }

        # Step D2: Not a duplicate. Check approval threshold dynamically
        from agent.policy import get_approval_threshold
        threshold = get_approval_threshold()
        needs_approval = (total_amount >= threshold) or any(
            "approval" in (h.get("result") or "").lower() for h in recent
        )
        if needs_approval and not approval_status.get(inv_num, False):
            return {
                "thought_summary": f"Invoice amount ₹{total_amount:,.2f} meets or exceeds ₹{threshold:,.2f} threshold. Requesting supervisor approval.",
                "action": "request_approval",
                "args": {
                    "invoice_number": inv_num,
                    "amount": total_amount,
                    "reason": f"Amount meets or exceeds ₹{threshold:,.2f} threshold (Total: ₹{total_amount:,.2f})"
                }
            }

        # Step E: Create finance record
        record_created = any(h.get("action") == "create_finance_record" and h.get("ok") for h in recent)
        if not record_created:
            return {
                "thought_summary": f"Creating official finance record for invoice {inv_num}.",
                "action": "create_finance_record",
                "args": {
                    "invoice_number": inv_num,
                    "vendor_name": vendor_name,
                    "amount": total_amount,
                    "due_date": due_date,
                    "currency": extracted.get("currency", "INR"),
                    "invoice_date": extracted.get("invoice_date")
                }
            }

        # Step F: Independently verify finance record
        if inv_num not in verified_records:
            return {
                "thought_summary": f"Independently verifying finance record for invoice {inv_num}.",
                "action": "verify_finance_record",
                "args": {
                    "invoice_number": inv_num,
                    "expected_vendor": vendor_name,
                    "expected_amount": total_amount,
                    "expected_due_date": due_date
                }
            }

        # Step G: Finish!
        return {
            "thought_summary": f"Invoice {inv_num} successfully processed, recorded, and verified. Finishing task.",
            "action": "finish",
            "args": {"summary": f"Processed and verified invoice {inv_num} for {vendor_name} (₹{total_amount:,.2f})."}
        }


class RealLLMAdapter:
    """Adapter for live LLM providers (Gemini, OpenAI)."""

    def __init__(self, provider: str, api_key: str, model_name: Optional[str] = None):
        self.provider = provider.lower()
        self.api_key = api_key
        self.model_name = model_name or ("gemini-2.5-flash" if self.provider == "gemini" else "gpt-4o-mini")

    def generate_action(self, system_prompt: str, user_prompt: str, state_summary: Dict[str, Any]) -> Dict[str, Any]:
        if self.provider == "gemini":
            try:
                from google import genai
                client = genai.Client(api_key=self.api_key)
                response = client.models.generate_content(
                    model=self.model_name,
                    contents=f"{system_prompt}\n\n{user_prompt}"
                )
                text = response.text
                return parse_json_action(text)
            except Exception as e:
                # Fallback to direct HTTP request if SDK fails
                import requests
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent?key={self.api_key}"
                payload = {
                    "contents": [{"parts": [{"text": f"{system_prompt}\n\n{user_prompt}"}]}]
                }
                res = requests.post(url, json=payload, timeout=30)
                res.raise_for_status()
                candidate_text = res.json()["candidates"][0]["content"]["parts"][0]["text"]
                return parse_json_action(candidate_text)

        elif self.provider == "openai":
            import openai
            client = openai.OpenAI(api_key=self.api_key)
            completion = client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={"type": "json_object"}
            )
            text = completion.choices[0].message.content
            return parse_json_action(text)

        else:
            raise ValueError(f"Unsupported LLM provider: {self.provider}")


def get_llm_adapter():
    """Factory creating the appropriate LLM adapter based on environment variables."""
    provider = os.getenv("LLM_PROVIDER", "gemini").lower()
    api_key = os.getenv("LLM_API_KEY", "")

    # If provider is explicitly fake or no API key is configured, use deterministic FakeLLMAdapter
    if provider == "fake" or not api_key:
        return FakeLLMAdapter()

    return RealLLMAdapter(
        provider=provider,
        api_key=api_key,
        model_name=os.getenv("LLM_MODEL")
    )
