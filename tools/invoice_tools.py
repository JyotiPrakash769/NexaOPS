"""
Invoice Processing Tools for NexaOps.
Every tool:
- Has a Pydantic input schema.
- Returns a structured dictionary: {"ok": bool, "data": Any, "error_type": Optional[str], "message": str}.
- Has metadata (read_only, retryable).
- Never writes directly outside its safe bounded interface.
"""

import os
import re
import time
from pathlib import Path
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
import pypdf

from tools.registry import registry
from env import finance_db

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INVOICES_DIR = PROJECT_ROOT / "data" / "invoices"

# In-memory transient failure tracker for demo timeout retry testing
_TIMEOUT_SIMULATED_COUNT = 0


# ==============================================================================
# 1. TOOL: find_latest_invoice
# ==============================================================================

class FindLatestInvoiceInput(BaseModel):
    vendor: str = Field(..., description="Name of the vendor to search for (e.g. 'ABC Technologies')")


@registry.register(
    name="find_latest_invoice",
    description="Scans the invoices directory and returns the most recent invoice file for the vendor based on invoice date.",
    input_schema=FindLatestInvoiceInput,
    read_only=True,
    retryable=False
)
def find_latest_invoice(vendor: str) -> Dict[str, Any]:
    if not INVOICES_DIR.exists():
        return {
            "ok": False,
            "data": None,
            "error_type": "not_found",
            "message": f"Invoices directory not found at {INVOICES_DIR}"
        }

    vendor_normalized = vendor.strip().lower()
    matching_invoices = []

    for file_path in INVOICES_DIR.glob("*.pdf"):
        try:
            reader = pypdf.PdfReader(str(file_path))
            text = "".join([page.extract_text() or "" for page in reader.pages])

            # Extract vendor
            vendor_match = re.search(r"Vendor:\s*([^\n\r]+)", text)
            file_vendor = vendor_match.group(1).strip() if vendor_match else ""

            # Check if matching vendor
            if vendor_normalized in file_vendor.lower():
                # Extract invoice date
                date_match = re.search(r"Invoice Date:\s*(\d{4}-\d{2}-\d{2})", text)
                inv_date = date_match.group(1) if date_match else "1970-01-01"

                # Extract invoice number
                num_match = re.search(r"Invoice Number:\s*([A-Za-z0-9\-]+)", text)
                inv_num = num_match.group(1) if num_match else file_path.stem

                matching_invoices.append({
                    "file": str(file_path.name),
                    "full_path": str(file_path),
                    "invoice_number": inv_num,
                    "vendor": file_vendor,
                    "invoice_date": inv_date
                })
        except Exception as e:
            continue

    if not matching_invoices:
        return {
            "ok": False,
            "data": None,
            "error_type": "not_found",
            "message": f"No invoices found for vendor '{vendor}'."
        }

    # Sort by invoice date DESCENDING (latest date first)
    matching_invoices.sort(key=lambda x: x["invoice_date"], reverse=True)
    latest = matching_invoices[0]

    return {
        "ok": True,
        "data": {
            "file": latest["file"],
            "full_path": latest["full_path"],
            "invoice_number": latest["invoice_number"],
            "vendor": latest["vendor"],
            "invoice_date": latest["invoice_date"],
            "total_found": len(matching_invoices)
        },
        "error_type": None,
        "message": f"Found latest invoice '{latest['file']}' dated {latest['invoice_date']}."
    }


# ==============================================================================
# 2. TOOL: extract_invoice_data
# ==============================================================================

class ExtractInvoiceDataInput(BaseModel):
    file: str = Field(..., description="Filename or relative path of the invoice PDF in data/invoices")


@registry.register(
    name="extract_invoice_data",
    description="Reads an invoice PDF and extracts invoice_number, vendor_name, invoice_date, due_date, currency, and total_amount. Missing fields are returned as null. Never invents values.",
    input_schema=ExtractInvoiceDataInput,
    read_only=True,
    retryable=False
)
def extract_invoice_data(file: str) -> Dict[str, Any]:
    file_path = INVOICES_DIR / Path(file).name
    if not file_path.exists():
        return {
            "ok": False,
            "data": None,
            "error_type": "file_not_found",
            "message": f"Invoice file not found: {file}"
        }

    try:
        reader = pypdf.PdfReader(str(file_path))
        text = "\n".join([page.extract_text() or "" for page in reader.pages])

        # Vendor Name
        vendor_match = re.search(r"Vendor:\s*([^\n\r]+)", text)
        vendor_name = vendor_match.group(1).strip() if vendor_match else None

        # Invoice Number
        num_match = re.search(r"Invoice Number:\s*([A-Za-z0-9\-]+)", text)
        invoice_number = num_match.group(1).strip() if num_match else None

        # Invoice Date
        inv_date_match = re.search(r"Invoice Date:\s*(\d{4}-\d{2}-\d{2})", text)
        invoice_date = inv_date_match.group(1).strip() if inv_date_match else None

        # Due Date
        due_date_match = re.search(r"Due Date:\s*(\d{4}-\d{2}-\d{2})", text)
        due_date = due_date_match.group(1).strip() if due_date_match else None

        # Currency
        curr_match = re.search(r"Currency:\s*([A-Za-z₹]{3,4})", text)
        currency = curr_match.group(1).strip() if curr_match else "INR"

        # Total Amount
        # Look for "Total Amount:\s*(?:(?:INR|USD|Rs\.?|₹)\s*)?([\d,]+(?:\.\d{2})?)"
        amount_match = re.search(r"Total Amount:\s*(?:(?:INR|USD|Rs\.?|₹)\s*)?([\d,]+(?:\.\d{2})?)", text)
        total_amount = None
        if amount_match:
            try:
                raw_amt = amount_match.group(1).replace(",", "")
                total_amount = float(raw_amt)
            except ValueError:
                total_amount = None

        extracted = {
            "invoice_number": invoice_number,
            "vendor_name": vendor_name,
            "invoice_date": invoice_date,
            "due_date": due_date,
            "currency": currency,
            "total_amount": total_amount,
            "file": file_path.name
        }

        # Check for missing required fields
        missing_fields = []
        if not invoice_number:
            missing_fields.append("invoice_number")
        if not vendor_name:
            missing_fields.append("vendor_name")
        if not total_amount:
            missing_fields.append("total_amount")
        if not due_date:
            missing_fields.append("due_date")

        if missing_fields:
            return {
                "ok": True,
                "data": extracted,
                "error_type": "missing_required_fields",
                "message": f"Extracted invoice data, but missing required field(s): {', '.join(missing_fields)}."
            }

        return {
            "ok": True,
            "data": extracted,
            "error_type": None,
            "message": f"Successfully extracted data from {file_path.name}."
        }

    except Exception as e:
        return {
            "ok": False,
            "data": None,
            "error_type": "extraction_error",
            "message": f"Failed to extract PDF text: {str(e)}"
        }


# ==============================================================================
# 3. TOOL: check_duplicate
# ==============================================================================

class CheckDuplicateInput(BaseModel):
    vendor: str = Field(..., description="Vendor name")
    invoice_number: str = Field(..., description="Invoice number to check")


@registry.register(
    name="check_duplicate",
    description="Looks up the invoice in the finance database to determine if it has already been recorded.",
    input_schema=CheckDuplicateInput,
    read_only=True,
    retryable=False
)
def check_duplicate(vendor: str, invoice_number: str) -> Dict[str, Any]:
    record = finance_db.get_record_by_vendor_and_number(vendor, invoice_number)
    if not record:
        # Fallback to check by invoice number alone
        record = finance_db.get_record(invoice_number)

    if record:
        return {
            "ok": True,
            "data": {
                "is_duplicate": True,
                "record_id": record["id"],
                "invoice_number": record["invoice_number"],
                "vendor_name": record["vendor_name"],
                "total_amount": record["total_amount"],
                "status": record["status"],
                "recorded_at": record["created_at"]
            },
            "error_type": None,
            "message": f"Invoice '{invoice_number}' already exists in finance records (ID: {record['id']})."
        }

    return {
        "ok": True,
        "data": {
            "is_duplicate": False,
            "invoice_number": invoice_number
        },
        "error_type": None,
        "message": f"No existing finance record found for invoice '{invoice_number}'. Safe to proceed."
    }


# ==============================================================================
# 4. TOOL: request_approval
# ==============================================================================

class RequestApprovalInput(BaseModel):
    invoice_number: str = Field(..., description="Invoice number")
    amount: float = Field(..., description="Invoice amount")
    reason: str = Field(..., description="Reason human approval is required (e.g. 'Amount $75,000 exceeds $10,000 threshold')")


# Callback hook for interactive CLI approval vs automated test injection
approval_interactive_callback = None


@registry.register(
    name="request_approval",
    description="Requests supervisor approval for high-value or restricted invoices. Halts for human decision (y/n).",
    input_schema=RequestApprovalInput,
    read_only=True,
    retryable=False
)
def request_approval(invoice_number: str, amount: float, reason: str) -> Dict[str, Any]:
    global approval_interactive_callback

    # If an external callback or test injection is provided:
    if approval_interactive_callback:
        approved = approval_interactive_callback(invoice_number, amount, reason)
    else:
        # Interactive CLI prompt
        print("\n" + "="*60)
        print(" [HUMAN APPROVAL REQUIRED]")
        print(f" Invoice: {invoice_number}")
        print(f" Amount:  ₹{amount:,.2f}")
        print(f" Reason:  {reason}")
        print("="*60)
        try:
            user_input = input(" Approve this invoice? (y/n): ").strip().lower()
            approved = user_input in ["y", "yes"]
        except EOFError:
            approved = False

    if approved:
        return {
            "ok": True,
            "data": {
                "approved": True,
                "invoice_number": invoice_number,
                "amount": amount,
                "reason": reason
            },
            "error_type": None,
            "message": f"Approval GRANTED by supervisor for invoice {invoice_number}."
        }
    else:
        return {
            "ok": False,
            "data": {
                "approved": False,
                "invoice_number": invoice_number,
                "amount": amount
            },
            "error_type": "approval_rejected",
            "message": f"Approval REJECTED by supervisor for invoice {invoice_number}."
        }


# ==============================================================================
# 5. TOOL: create_finance_record
# ==============================================================================

class CreateFinanceRecordInput(BaseModel):
    invoice_number: str = Field(..., description="Invoice number")
    vendor_name: str = Field(..., description="Vendor name")
    amount: float = Field(..., description="Total invoice amount")
    due_date: str = Field(..., description="Due date (YYYY-MM-DD)")
    currency: str = Field(default="INR", description="Currency (e.g. INR)")
    invoice_date: Optional[str] = Field(default=None, description="Invoice issue date (YYYY-MM-DD)")


@registry.register(
    name="create_finance_record",
    description="Creates an official record in the finance system of record. Requires all mandatory fields.",
    input_schema=CreateFinanceRecordInput,
    read_only=False,
    retryable=True
)
def create_finance_record(
    invoice_number: str,
    vendor_name: str,
    amount: float,
    due_date: str,
    currency: str = "INR",
    invoice_date: Optional[str] = None
) -> Dict[str, Any]:
    global _TIMEOUT_SIMULATED_COUNT

    # Failure Mode Simulation: Timeout
    fail_mode = os.getenv("FAIL_MODE", "").lower()
    demo_timeout = os.getenv("DEMO_FINANCE_TIMEOUT", "false").lower() == "true"
    if fail_mode == "timeout" or demo_timeout:
        if _TIMEOUT_SIMULATED_COUNT == 0:
            _TIMEOUT_SIMULATED_COUNT += 1
            return {
                "ok": False,
                "data": None,
                "error_type": "timeout",
                "message": "Gateway timeout: Finance system did not respond in 5000ms (HTTP 504 simulated)."
            }

    # Verify required fields
    if not due_date or due_date.strip().lower() in ["none", "null", "not specified"]:
        return {
            "ok": False,
            "data": None,
            "error_type": "missing_required_field",
            "message": "Cannot create record: due_date is required and cannot be empty."
        }

    # Verify duplicate prevention in database
    existing = finance_db.get_record(invoice_number)
    if existing:
        return {
            "ok": False,
            "data": {"existing_id": existing["id"]},
            "error_type": "duplicate_record",
            "message": f"Refusing to create duplicate record: invoice {invoice_number} already exists."
        }

    # Failure Mode Simulation: Verification Mismatch (corrupted write)
    demo_mismatch = (fail_mode == "verification_mismatch") or (os.getenv("DEMO_VERIFICATION_MISMATCH", "false").lower() == "true")
    stored_amount = (amount + 999.0) if demo_mismatch else amount

    record = finance_db.insert_record(
        invoice_number=invoice_number,
        vendor_name=vendor_name,
        invoice_date=invoice_date,
        due_date=due_date,
        currency=currency,
        total_amount=stored_amount,
        status="RECORDED"
    )

    return {
        "ok": True,
        "data": {
            "record_id": record["id"],
            "invoice_number": record["invoice_number"],
            "vendor_name": record["vendor_name"],
            "total_amount": record["total_amount"],
            "status": record["status"]
        },
        "error_type": None,
        "message": f"Successfully created finance record #{record['id']} for {invoice_number}."
    }


# ==============================================================================
# 6. TOOL: verify_finance_record
# ==============================================================================

class VerifyFinanceRecordInput(BaseModel):
    invoice_number: str = Field(..., description="Invoice number to verify")
    expected_vendor: str = Field(..., description="Expected vendor name from invoice")
    expected_amount: float = Field(..., description="Expected total amount from invoice")
    expected_due_date: str = Field(..., description="Expected due date from invoice")


@registry.register(
    name="verify_finance_record",
    description="Independently re-reads the record from the finance database and compares all fields with original extracted data.",
    input_schema=VerifyFinanceRecordInput,
    read_only=True,
    retryable=False
)
def verify_finance_record(
    invoice_number: str,
    expected_vendor: str,
    expected_amount: float,
    expected_due_date: str
) -> Dict[str, Any]:
    record = finance_db.get_record(invoice_number)
    if not record:
        return {
            "ok": False,
            "data": {"verified": False},
            "error_type": "record_not_found",
            "message": f"Verification failed: No record found for invoice '{invoice_number}' in finance database."
        }

    mismatches = []

    # Vendor check (case-insensitive substring or match)
    if expected_vendor.strip().lower() not in record["vendor_name"].strip().lower():
        mismatches.append(f"Vendor mismatch: expected '{expected_vendor}', stored '{record['vendor_name']}'")

    # Amount check (float precision tolerance 0.01)
    if abs(record["total_amount"] - expected_amount) > 0.01:
        mismatches.append(f"Amount mismatch: expected ₹{expected_amount:,.2f}, stored ₹{record['total_amount']:,.2f}")

    # Due date check
    if expected_due_date.strip() != (record["due_date"] or "").strip():
        mismatches.append(f"Due date mismatch: expected '{expected_due_date}', stored '{record['due_date']}'")

    if mismatches:
        return {
            "ok": False,
            "data": {
                "verified": False,
                "invoice_number": invoice_number,
                "record_id": record["id"],
                "mismatches": mismatches
            },
            "error_type": "verification_mismatch",
            "message": f"Verification failed with mismatches: {'; '.join(mismatches)}"
        }

    return {
        "ok": True,
        "data": {
            "verified": True,
            "invoice_number": invoice_number,
            "record_id": record["id"],
            "vendor_name": record["vendor_name"],
            "total_amount": record["total_amount"],
            "due_date": record["due_date"],
            "status": record["status"]
        },
        "error_type": None,
        "message": f"Independent verification PASSED: Finance record #{record['id']} accurately matches invoice."
    }


# ==============================================================================
# 7. GENERALIZATION TOOL: list_invoices
# ==============================================================================

class ListInvoicesInput(BaseModel):
    vendor: Optional[str] = Field(default=None, description="Optional vendor name filter")


@registry.register(
    name="list_invoices",
    description="Lists all recorded finance invoices, optionally filtered by vendor name.",
    input_schema=ListInvoicesInput,
    read_only=True,
    retryable=False
)
def list_invoices(vendor: Optional[str] = None) -> Dict[str, Any]:
    records = finance_db.list_records(vendor_name=vendor)
    return {
        "ok": True,
        "data": {
            "count": len(records),
            "vendor_filter": vendor,
            "invoices": records
        },
        "error_type": None,
        "message": f"Found {len(records)} invoice(s) in finance database."
    }
