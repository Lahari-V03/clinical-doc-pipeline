"""
clinical_policy_connector.py — Clinical policy document ingestion pipeline.

Saves PDF to raw/, extracts text to processed/v{n}.txt,
and registers the version in versions.json.

Usage:
    python connectors/clinical_policy_connector.py \
        --file path/to/2024-report-congress.pdf \
        --policy cms_ncd \
        --label v1 \
        --date 2024-08-01
"""

import argparse
import os
import re
import shutil
from datetime import datetime

import pdfplumber
from dotenv import load_dotenv

load_dotenv()

SAMPLES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "samples", "policy"
)

SECTION_KEYWORDS = [
    "coverage criteria", "billing guidelines", "billing instructions",
    "exclusions", "limitations", "coding guidelines", "documentation requirements",
    "indications", "contraindications", "policy", "definitions",
    "reimbursement", "prior authorization", "clinical criteria",
    "national coverage", "coverage determinations", "statutory", "factors", "table",
]

RULE_KEYWORDS = [
    "must", "shall", "required", "not covered", "eligible", "ineligible",
    "only when", "not medically necessary", "medically necessary",
    "limit", "maximum", "minimum", "prohibited", "allowed", "denied",
    "covered", "excluded", "billed", "reported", "submitted",
    "payment", "determination", "contractor", "beneficiar",
]


def is_section_heading(line):
    line_lower = line.lower().strip()
    if len(line.strip()) < 80 and any(kw in line_lower for kw in SECTION_KEYWORDS):
        return True
    if line.strip().isupper() and 5 < len(line.strip()) < 80:
        return True
    return False


def is_rule(sentence):
    return any(kw in sentence.lower() for kw in RULE_KEYWORDS)


def extract_sections_and_rules(text):
    lines = text.split("\n")
    sections = {}
    current_section = "General"
    sections[current_section] = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if is_section_heading(stripped):
            current_section = stripped.title()
            if current_section not in sections:
                sections[current_section] = []
        else:
            sections[current_section].append(stripped)

    rules = []
    for section_name, paragraphs in sections.items():
        full_section_text = " ".join(paragraphs)
        sentences = re.split(r'(?<=[.!?])\s+', full_section_text)
        for sentence in sentences:
            if len(sentence.strip()) > 20 and is_rule(sentence):
                rules.append({"section": section_name, "rule_text": sentence.strip()})

    return sections, rules


def extract_text(pdf_path):
    text_parts = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text_parts.append(page.extract_text() or "")
        page_count = len(pdf.pages)
    return "\n".join(text_parts), page_count


def run(pdf_path, policy_name, label=None, date=None, document_type="billing_policy"):
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from analysis.version_store import VersionStore

    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    filename = os.path.basename(pdf_path)
    policy_dir  = os.path.join(SAMPLES_DIR, policy_name)
    raw_dir     = os.path.join(policy_dir, "raw")
    processed_dir = os.path.join(policy_dir, "processed")

    os.makedirs(raw_dir, exist_ok=True)
    os.makedirs(processed_dir, exist_ok=True)

    print(f"\nProcessing: {filename}")
    print(f"  Policy group : {policy_name}")
    print(f"  Document type: {document_type}")

    # Step 1 — Copy PDF to raw/
    raw_path = os.path.join(raw_dir, filename)
    if not os.path.exists(raw_path):
        shutil.copy2(pdf_path, raw_path)
        print(f"  PDF saved → raw/{filename}")
    else:
        print(f"  PDF already in raw/ → skipping copy")

    # Step 2 — Extract text
    full_text, page_count = extract_text(pdf_path)
    print(f"  Pages        : {page_count}")
    print(f"  Characters   : {len(full_text)}")

    # Step 3 — Extract sections and rules
    sections, rules = extract_sections_and_rules(full_text)
    print(f"  Sections     : {len(sections)}")
    print(f"  Rules        : {len(rules)}")

    # Step 4 — Determine version label and save to processed/
    store = VersionStore(policy_dir)
    if label is None:
        import json
        manifest = json.load(open(store.manifest_path))
        label = f"v{len(manifest['versions']) + 1}"

    txt_filename = f"{label}_{filename.replace('.pdf', '.txt')}"
    txt_path = os.path.join(processed_dir, txt_filename)
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(full_text)
    print(f"  Text saved   → processed/{txt_filename}")

    # Step 5 — Register in versions.json
    store.register(
        filename=txt_filename,
        label=label,
        date=date,
        notes=f"Source: {filename} | {page_count} pages | {len(rules)} rules"
    )

    print(f"\n  ✅ Done: {filename} → {label}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Clinical policy document ingestion pipeline")
    parser.add_argument("--file",   type=str, required=True, help="Path to the policy PDF")
    parser.add_argument("--policy", type=str, required=True, help="Policy group name e.g. cms_ncd")
    parser.add_argument("--label",  type=str, default=None,  help="Version label e.g. v1")
    parser.add_argument("--date",   type=str, default=None,  help="Policy date e.g. 2024-08-01")
    parser.add_argument(
        "--type", type=str, default="billing_policy",
        choices=["billing_policy", "coding_guideline", "clinical_practice_guideline"],
    )
    args = parser.parse_args()
    run(pdf_path=args.file, policy_name=args.policy, label=args.label, date=args.date, document_type=args.type)