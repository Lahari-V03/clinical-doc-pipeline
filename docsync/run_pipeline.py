"""
run_pipeline.py: Full clinical document pipeline demo.

Shows the complete Clinical NLT Pipeline POC for Cotiviti:
  1. Scanned document ingestion with OCR + confidence scoring + QA routing
  2. Digital PDF ingestion
  3. JSON ingestion
  4. Clinical policy ingestion + version registration
  5. LLM-powered policy comparison
  6. QA review summary

Usage:
    python run_pipeline.py
"""

import os
import sys

# ── Banner ──────────────────────────────────────────────────────────────────
def banner(title):
    print("\n" + "═" * 60)
    print(f"  {title}")
    print("═" * 60)


def section(title):
    print(f"\n  ── {title} ──")


# ── Main Pipeline ────────────────────────────────────────────────────────────
if __name__ == "__main__":

    banner("Clinical Document Intelligence Pipeline")
    print("  Cotiviti - Clinical NLT Pipeline POC")
    print("  Lahari Vuppalapati | June 2026")

    # ── Step 1: Scanned Document Ingestion ──────────────────────────────────
    banner("STEP 1 - Scanned Document Ingestion (OCR + QA Routing)")
    print("  Model     : prebuilt-layout")
    print("  Threshold : 0.80 confidence")
    print("  QA Queue  : qa/review/pending/\n")

    from connectors.scanned_pdf_connector import run as run_scanned
    run_scanned(model="prebuilt-layout")

    # ── Step 2: Digital PDF Ingestion ───────────────────────────────────────
    banner("STEP 2 - Digital PDF Ingestion")
    from connectors.pdf_connector import run as run_pdf
    run_pdf()

    # ── Step 3: JSON Ingestion ───────────────────────────────────────────────
    banner("STEP 3 - JSON / Structured Data Ingestion")
    from connectors.json_connector import run as run_json
    run_json()

    # ── Step 4: Clinical Policy Ingestion ───────────────────────────────────
    banner("STEP 4 - Clinical Policy Ingestion + Version Registration")

    from connectors.clinical_policy_connector import run as run_policy
    from analysis.version_store import VersionStore

    POLICY_NAME = "cms_ncd"
    POLICY_DIR  = os.path.join("samples", "policy", POLICY_NAME)
    RAW_DIR     = os.path.join(POLICY_DIR, "raw")

    # Register any PDFs in raw/ that haven't been ingested yet
    pdfs = sorted([f for f in os.listdir(RAW_DIR) if f.endswith(".pdf")])

    if not pdfs:
        print(f"  No PDFs found in {RAW_DIR}. Skipping policy ingestion.")
    else:
        store = VersionStore(POLICY_DIR)
        import json
        manifest = json.load(open(store.manifest_path))
        registered_files = [v["file"] for v in manifest["versions"]]

        for pdf in pdfs:
            txt_name = f"v{len(manifest['versions']) + 1}_{pdf.replace('.pdf', '.txt')}"
            if txt_name in registered_files:
                print(f"  Already registered: {pdf} → skipping")
                continue
            pdf_path = os.path.join(RAW_DIR, pdf)
            run_policy(pdf_path=pdf_path, policy_name=POLICY_NAME)
            # Reload manifest after each registration
            manifest = json.load(open(store.manifest_path))

    # Show registered versions
    section("Registered Policy Versions")
    store = VersionStore(POLICY_DIR)
    store.list_versions()

    # ── Step 5: LLM Policy Comparison ───────────────────────────────────────
    banner("STEP 5 - LLM-Powered Policy Comparison")

    from analysis.policy_compare import run as run_compare

    try:
        run_compare(policy_name=POLICY_NAME)
    except ValueError as e:
        print(f"  ⚠️  Skipping comparison: {e}")

    # ── Step 6: QA Review Summary ────────────────────────────────────────────
    banner("STEP 6 - QA Review Summary")

    pending_dir  = os.path.join("qa", "review", "pending")
    approved_dir = os.path.join("qa", "review", "approved")
    rejected_dir = os.path.join("qa", "review", "rejected")
    reports_dir  = os.path.join("qa", "reports")

    def count(folder):
        if not os.path.exists(folder):
            return 0
        return len([f for f in os.listdir(folder) if f.endswith(".json") or f.endswith(".txt")])

    print(f"\n   QA Status")
    print(f"     Pending review  : {count(pending_dir)} document(s)")
    print(f"     Approved        : {count(approved_dir)} document(s)")
    print(f"     Rejected        : {count(rejected_dir)} document(s)")
    print(f"     Policy reports  : {count(reports_dir)} report(s) generated")

    if count(pending_dir) > 0:
        print(f"\n  ⚠️  Run 'python qa/qa_manager.py' to review flagged documents.")

    banner("STEP 7 - Generate Embeddings for Semantic Search")
    from generate_embeddings import run as run_embeddings
    run_embeddings()

    # ── Done ─────────────────────────────────────────────────────────────────
    banner("PIPELINE COMPLETE")
    print("  Scanned documents ingested with OCR confidence scoring")
    print("  Digital PDFs and JSON data ingested")
    print("  Policy versions registered and tracked")
    print("  LLM policy comparison generated")
    print("  QA routing active - low-confidence docs flagged for review")
    print()
    print("  Cotiviti Clinical NLT Pipeline POC - Lahari Vuppalapati")
    print("═" * 60)