"""
Finance Database & Audit Store for NexaOps.
Uses stdlib sqlite3.
Only tools and the event logger interact directly with this database.
"""

import sqlite3
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "finance.db"


def get_db_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """Returns a SQLite connection with row factory enabled."""
    target_path = Path(db_path or DEFAULT_DB_PATH)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(target_path))
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Optional[Path] = None) -> None:
    """Initializes the finance records and audit events tables."""
    conn = get_db_connection(db_path)
    with conn:
        # Finance records table (system of record)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS finance_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                invoice_number TEXT UNIQUE NOT NULL,
                vendor_name TEXT NOT NULL,
                invoice_date TEXT,
                due_date TEXT,
                currency TEXT NOT NULL,
                total_amount REAL NOT NULL,
                status TEXT DEFAULT 'RECORDED',
                created_at TEXT NOT NULL
            )
        """)

        # Audit events table (persisted timeline of all agent tool executions)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                step INTEGER NOT NULL,
                tool TEXT NOT NULL,
                args TEXT,
                result TEXT,
                status TEXT,
                timestamp TEXT NOT NULL
            )
        """)
    conn.close()


def get_record(invoice_number: str, db_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Retrieves a finance record by invoice number."""
    conn = get_db_connection(db_path)
    cur = conn.cursor()
    cur.execute("SELECT * FROM finance_records WHERE invoice_number = ?", (invoice_number,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def get_record_by_vendor_and_number(vendor_name: str, invoice_number: str, db_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Finds a record matching vendor name (case-insensitive) and invoice number."""
    conn = get_db_connection(db_path)
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM finance_records WHERE LOWER(vendor_name) = LOWER(?) AND invoice_number = ?",
        (vendor_name.strip(), invoice_number.strip())
    )
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def insert_record(
    invoice_number: str,
    vendor_name: str,
    invoice_date: Optional[str],
    due_date: Optional[str],
    currency: str,
    total_amount: float,
    status: str = "RECORDED",
    db_path: Optional[Path] = None
) -> Dict[str, Any]:
    """Inserts a new finance record and returns the created record."""
    conn = get_db_connection(db_path)
    created_at = datetime.now(timezone.utc).isoformat()
    with conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO finance_records (
                invoice_number, vendor_name, invoice_date, due_date, currency, total_amount, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (invoice_number, vendor_name, invoice_date, due_date, currency, total_amount, status, created_at))
        record_id = cur.lastrowid
    conn.close()
    return {
        "id": record_id,
        "invoice_number": invoice_number,
        "vendor_name": vendor_name,
        "invoice_date": invoice_date,
        "due_date": due_date,
        "currency": currency,
        "total_amount": total_amount,
        "status": status,
        "created_at": created_at
    }


def list_records(vendor_name: Optional[str] = None, db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Lists finance records, optionally filtered by vendor."""
    conn = get_db_connection(db_path)
    cur = conn.cursor()
    if vendor_name:
        cur.execute(
            "SELECT * FROM finance_records WHERE LOWER(vendor_name) LIKE LOWER(?) ORDER BY id DESC",
            (f"%{vendor_name.strip()}%",)
        )
    else:
        cur.execute("SELECT * FROM finance_records ORDER BY id DESC")
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def log_audit_event(
    task_id: str,
    step: int,
    tool: str,
    args: Any,
    result: Any,
    status: str,
    db_path: Optional[Path] = None
) -> int:
    """Logs an agent step event to SQLite audit table."""
    conn = get_db_connection(db_path)
    timestamp = datetime.now(timezone.utc).isoformat()
    args_json = json.dumps(args, default=str)
    result_json = json.dumps(result, default=str)
    with conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO audit_events (task_id, step, tool, args, result, status, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (task_id, step, tool, args_json, result_json, status, timestamp))
        event_id = cur.lastrowid
    conn.close()
    return event_id


def get_audit_events(task_id: str, db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Retrieves all audit events recorded for a task."""
    conn = get_db_connection(db_path)
    cur = conn.cursor()
    cur.execute("SELECT * FROM audit_events WHERE task_id = ? ORDER BY step ASC", (task_id,))
    rows = cur.fetchall()
    conn.close()
    events = []
    for r in rows:
        d = dict(r)
        try:
            d["args"] = json.loads(d["args"])
        except Exception:
            pass
        try:
            d["result"] = json.loads(d["result"])
        except Exception:
            pass
        events.append(d)
    return events
