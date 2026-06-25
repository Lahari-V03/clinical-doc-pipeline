import hashlib
import json
import os
from datetime import datetime

import pdfplumber
import psycopg2

SAMPLES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "samples", "digital")

DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 5432,
    "dbname": "docsync",
    "user": "admin",
    "password": "secret",
}


def extract_text(pdf_path):
    text_parts = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text_parts.append(page.extract_text() or "")
        page_count = len(pdf.pages)
    return "\n".join(text_parts), page_count


def run():
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    for filename in os.listdir(SAMPLES_DIR):
        if not filename.lower().endswith(".pdf"):
            continue

        pdf_path = os.path.join(SAMPLES_DIR, filename)
        raw_text, page_count = extract_text(pdf_path)
        content_hash = hashlib.md5(raw_text.encode("utf-8")).hexdigest()
        metadata = json.dumps({"filename": filename, "page_count": page_count})
        now = datetime.now()

        print(f"Processing: {filename} ({page_count} pages)")
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
            ("digital_pdf", filename, raw_text, metadata, content_hash, now, now),
        )

    conn.commit()
    print("Done. All PDFs processed.")
    
    cur.close()
    conn.close()


if __name__ == "__main__":
    run()
