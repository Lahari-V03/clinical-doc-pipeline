import hashlib
import json
import os
import re
from datetime import datetime

import pdfplumber
import psycopg2
from dotenv import load_dotenv

load_dotenv()

SAMPLES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "samples", "policy"
)

DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 5432,
    "dbname": "docsync",
    "user": "admin",
    "password": "secret",
}

# Keywords that indicate a line is a section heading
SECTION_KEYWORDS = [
    "coverage criteria", "billing guidelines", "billing instructions",
    "exclusions", "limitations", "coding guidelines", "documentation requirements",
    "indications", "contraindications", "policy", "definitions",
    "reimbursement", "prior authorization", "clinical criteria",
]

# Keywords that indicate a sentence is a policy rule
RULE_KEYWORDS = [
    "must", "shall", "required", "not covered", "eligible", "ineligible",
    "only when", "not medically necessary", "medically necessary",
    "limit", "maximum", "minimum", "prohibited", "allowed", "denied",
    "covered", "excluded", "billed", "reported", "submitted",
]


def is_section_heading(line):
    """Detect if a line looks like a section heading."""
    line_lower = line.lower().strip()
    # Short lines that match known section keywords
    if len(line.strip()) < 80 and any(kw in line_lower for kw in SECTION_KEYWORDS):
        return True
    # All-caps short lines
    if line.strip().isupper() and 5 < len(line.strip()) < 80:
        return True
    return False


def is_rule(sentence):
    """Detect if a sentence contains policy rule language."""
    sentence_lower = sentence.lower()
    return any(kw in sentence_lower for kw in RULE_KEYWORDS)


def extract_sections_and_rules(text):
    """
    Parse policy document text into structured sections and rules.
    Returns:
        sections: dict of {section_name: [list of paragraphs]}
        rules: list of {section, rule_text}
    """
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

    # Extract rules from each section
    rules = []
    for section_name, paragraphs in sections.items():
        full_section_text = " ".join(paragraphs)
        # Split into sentences
        sentences = re.split(r'(?<=[.!?])\s+', full_section_text)
        for sentence in sentences:
            if len(sentence.strip()) > 20 and is_rule(sentence):
                rules.append({
                    "section": section_name,
                    "rule_text": sentence.strip(),
                })

    return sections, rules


def extract_text_and_structure(pdf_path):
    """Extract raw text and structured content from a policy PDF."""
    text_parts = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text_parts.append(page.extract_text() or "")
        page_count = len(pdf.pages)

    full_text = "\n".join(text_parts)
    sections, rules = extract_sections_and_rules(full_text)

    return full_text, page_count, sections, rules


def run(document_type="billing_policy"):
    """
    Run the clinical policy document ingestion pipeline.

    Args:
        document_type: Type of policy document being ingested.
                       Options: billing_policy, coding_guideline, clinical_practice_guideline
    """
    print(f"Starting clinical policy ingestion pipeline | Type: {document_type}")

    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    # Create samples/policy directory if it doesn't exist
    os.makedirs(SAMPLES_DIR, exist_ok=True)

    files = [f for f in os.listdir(SAMPLES_DIR) if f.lower().endswith(".pdf")]
    if not files:
        print(f"No PDF files found in {SAMPLES_DIR}")
        print("Add billing/coding policy PDFs to docsync/samples/policy/ and rerun.")
        cur.close()
        conn.close()
        return

    for filename in files:
        pdf_path = os.path.join(SAMPLES_DIR, filename)
        print(f"\nProcessing: {filename}")

        full_text, page_count, sections, rules = extract_text_and_structure(pdf_path)

        section_names = list(sections.keys())
        rules_count = len(rules)

        print(f"  Sections found : {len(section_names)}")
        print(f"  Rules extracted: {rules_count}")
        for section in section_names:
            print(f"    → {section}")

        content_hash = hashlib.md5(full_text.encode("utf-8")).hexdigest()
        metadata = json.dumps({
            "filename": filename,
            "page_count": page_count,
            "document_type": document_type,
            "sections_found": section_names,
            "rules_extracted": rules_count,
            "rules": rules,
            "extraction_date": datetime.now().isoformat(),
        })
        now = datetime.now()

        cur.execute(
            """
            INSERT INTO documents (
                source_type, source_id, raw_text, metadata,
                content_hash, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (source_type, source_id) DO UPDATE SET
            raw_text     = EXCLUDED.raw_text,
            metadata     = EXCLUDED.metadata,
            content_hash = EXCLUDED.content_hash,
            updated_at   = EXCLUDED.updated_at
            """,
            ("policy_doc", filename, full_text, metadata, content_hash, now, now),
        )

        print(f"  ✅ Saved to DB as policy_doc | {rules_count} rules extracted")

    conn.commit()
    print("\nDone. All policy documents processed.")

    cur.close()
    conn.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Clinical policy document ingestion pipeline")
    parser.add_argument(
        "--type",
        type=str,
        default="billing_policy",
        choices=["billing_policy", "coding_guideline", "clinical_practice_guideline"],
        help=(
            "Type of policy document:\n"
            "  billing_policy                → payer billing policies\n"
            "  coding_guideline              → AMA CPT or ICD-10 coding rules\n"
            "  clinical_practice_guideline   → clinical decision guidelines\n"
        ),
    )
    args = parser.parse_args()
    run(document_type=args.type)