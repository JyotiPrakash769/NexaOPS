"""
NexaOps CLI Entry Point.
Usage:
  python main.py "Process the latest invoice from ABC Technologies"
  python main.py "Process the latest invoice from Delta Systems"
  python main.py --fail-mode timeout "Process the latest invoice from ABC Technologies"
  python main.py --fail-mode verification_mismatch "Process the latest invoice from ABC Technologies"
  python main.py "List all unpaid invoices from ABC Technologies"
"""

import sys
import os
import argparse
from pathlib import Path
from dotenv import load_dotenv

# Ensure nexaops root directory is on Python search path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv()

from agent.controller import run_task
from env.seed import seed_database, seed_invoices


def main():
    parser = argparse.ArgumentParser(
        description="NexaOps - Autonomous AI Operations Employee for Invoice Processing",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "goal",
        nargs="?",
        default="Process the latest invoice from ABC Technologies",
        help="Natural language business objective for the agent (e.g. 'Process the latest invoice from ABC Technologies')"
    )
    parser.add_argument(
        "--fail-mode",
        choices=["timeout", "duplicate", "verification_mismatch", "none"],
        default=None,
        help="Simulate specific failure scenarios (timeout, verification_mismatch)"
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=None,
        help="Custom approval threshold (default $10,000)"
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=15,
        help="Maximum allowed steps before termination (default 15)"
    )
    parser.add_argument(
        "--provider",
        choices=["fake", "gemini", "openai"],
        default=None,
        help="Override LLM provider (fake, gemini, openai)"
    )
    parser.add_argument(
        "--seed",
        action="store_true",
        help="Re-initialize database and sample invoices before running"
    )

    args = parser.parse_args()

    # Re-seed if requested or if invoices don't exist
    invoices_dir = PROJECT_ROOT / "data" / "invoices"
    if args.seed or not invoices_dir.exists() or not any(invoices_dir.glob("*.pdf")):
        print("Ensuring database and sample invoices are seeded...")
        seed_database()
        seed_invoices()

    if args.threshold is not None:
        os.environ["INVOICE_APPROVAL_THRESHOLD"] = str(args.threshold)

    if args.provider is not None:
        os.environ["LLM_PROVIDER"] = args.provider

    # Execute agent task
    state = run_task(
        goal=args.goal,
        max_steps=args.max_steps,
        fail_mode=args.fail_mode,
        interactive_approval=True,
        verbose=True
    )

    # Exit code based on task outcome
    if state.status == "COMPLETED":
        sys.exit(0)
    elif state.status in ["REJECTED", "NEEDS_INPUT"]:
        sys.exit(1)
    else:
        sys.exit(2)


if __name__ == "__main__":
    main()
