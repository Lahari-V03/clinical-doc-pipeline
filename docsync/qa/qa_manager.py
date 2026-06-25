"""
QA Manager — Interactive review tool for flagged clinical documents.

Folder structure (all auto-created):
    docsync/qa/review/pending/   ← documents flagged by the pipeline
    docsync/qa/review/approved/  ← cleared by human reviewer
    docsync/qa/review/rejected/  ← needs reprocessing
"""

import json
import os
import shutil
from datetime import datetime

# --- Paths ---
QA_BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "review")
PENDING_DIR  = os.path.join(QA_BASE, "pending")
APPROVED_DIR = os.path.join(QA_BASE, "approved")
REJECTED_DIR = os.path.join(QA_BASE, "rejected")


def ensure_dirs():
    """Create QA folder structure if it doesn't exist."""
    for d in [PENDING_DIR, APPROVED_DIR, REJECTED_DIR]:
        os.makedirs(d, exist_ok=True)


def list_pending():
    """Return list of pending review files."""
    return [f for f in os.listdir(PENDING_DIR) if f.endswith(".json")]


def load_review(filename):
    """Load and return a review record."""
    path = os.path.join(PENDING_DIR, filename)
    with open(path, "r") as f:
        return json.load(f)


def move_review(filename, destination):
    """Move a review file to approved or rejected folder."""
    src = os.path.join(PENDING_DIR, filename)
    dst = os.path.join(destination, filename)
    shutil.move(src, dst)


def display_review(record, index, total):
    """Pretty print a review record for human inspection."""
    print("\n" + "═" * 60)
    print(f"  Review {index} of {total}")
    print("═" * 60)
    print(f"  📄 File            : {record.get('filename', 'N/A')}")
    print(f"  🤖 Model Used      : {record.get('model_used', 'N/A')}")
    print(f"  📊 Confidence Score: {record.get('confidence_score', 'N/A')}")
    print(f"  ⚠️  Flag Reason     : {record.get('flag_reason', 'N/A')}")
    print(f"  🕐 Flagged At      : {record.get('flagged_at', 'N/A')}")
    print("\n  --- Extracted Text Preview ---")
    print(f"  {record.get('extracted_text_preview', 'No preview available')[:400]}")
    print("─" * 60)


def log_decision(filename, decision):
    """Append decision to a simple audit log."""
    log_path = os.path.join(QA_BASE, "audit_log.jsonl")
    entry = {
        "filename": filename,
        "decision": decision,
        "reviewed_at": datetime.now().isoformat(),
    }
    with open(log_path, "a") as f:
        f.write(json.dumps(entry) + "\n")


def show_summary():
    """Show count of files in each folder."""
    pending  = len(list_pending())
    approved = len([f for f in os.listdir(APPROVED_DIR) if f.endswith(".json")])
    rejected = len([f for f in os.listdir(REJECTED_DIR) if f.endswith(".json")])
    print("\n  📋 QA Review Summary")
    print(f"     Pending  : {pending}")
    print(f"     Approved : {approved}")
    print(f"     Rejected : {rejected}")


def run_interactive():
    """Main interactive review loop."""
    ensure_dirs()

    print("\n" + "═" * 60)
    print("   Clinical Document QA Review Manager")
    print("   Cotiviti — Clinical NLT Pipeline POC")
    print("═" * 60)

    while True:
        show_summary()
        pending_files = list_pending()

        if not pending_files:
            print("\n  ✅ No pending reviews. All documents are cleared.")
            print("\n  Press Enter to exit...")
            input()
            break

        print(f"\n  {len(pending_files)} document(s) pending review.")
        print("\n  Options:")
        print("    [1] Review pending documents")
        print("    [2] View summary")
        print("    [3] Exit")
        print()

        choice = input("  Enter choice (1/2/3): ").strip()

        if choice == "1":
            _review_loop(pending_files)
        elif choice == "2":
            continue
        elif choice == "3":
            print("\n  Exiting QA Manager. Goodbye!\n")
            break
        else:
            print("\n  Invalid choice. Please enter 1, 2, or 3.")


def _review_loop(pending_files):
    """Loop through pending files one by one."""
    total = len(pending_files)

    for index, filename in enumerate(pending_files, start=1):
        record = load_review(filename)
        display_review(record, index, total)

        print("  Actions:")
        print("    [a] Approve — document looks acceptable, clear for pipeline")
        print("    [r] Reject  — document needs reprocessing or better scan")
        print("    [s] Skip    — review later")
        print("    [q] Quit review session")
        print()

        while True:
            action = input("  Enter action (a/r/s/q): ").strip().lower()

            if action == "a":
                move_review(filename, APPROVED_DIR)
                log_decision(filename, "approved")
                print(f"\n  ✅ Approved → {filename}")
                break

            elif action == "r":
                move_review(filename, REJECTED_DIR)
                log_decision(filename, "rejected")
                print(f"\n  ❌ Rejected → {filename}")
                break

            elif action == "s":
                print(f"\n  ⏭️  Skipped → {filename}")
                break

            elif action == "q":
                print("\n  Exiting review session.")
                return

            else:
                print("  Invalid input. Enter a, r, s, or q.")

    print("\n  Review session complete.")


if __name__ == "__main__":
    run_interactive()