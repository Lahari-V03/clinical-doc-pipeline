import hashlib
import json
import os
from datetime import datetime
from io import BytesIO

import psycopg2
from azure.ai.formrecognizer import DocumentAnalysisClient
from azure.core.credentials import AzureKeyCredential
from dotenv import load_dotenv
from PyPDF2 import PdfReader, PdfWriter

load_dotenv()

AZURE_DI_KEY = os.getenv("AZURE_DI_KEY")
AZURE_DI_ENDPOINT = os.getenv("AZURE_DI_ENDPOINT")

SAMPLES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "samples", "scanned")

DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 5432,
    "dbname": "docsync",
    "user": "admin",
    "password": "secret",
}

CHUNK_SIZE = 2


def split_into_chunks(file_path):
    if not file_path.lower().endswith(".pdf"):
        with open(file_path, "rb") as f:
            buffer = BytesIO(f.read())
        return [buffer], 1

    reader = PdfReader(file_path)
    page_count = len(reader.pages)
    chunks = []

    for start in range(0, page_count, CHUNK_SIZE):
        writer = PdfWriter()
        for page in reader.pages[start:start + CHUNK_SIZE]:
            writer.add_page(page)
        buffer = BytesIO()
        writer.write(buffer)
        buffer.seek(0)
        chunks.append(buffer)

    return chunks, page_count


def analyze_chunk(client, chunk):
    poller = client.begin_analyze_document("prebuilt-read", document=chunk)
    result = poller.result()
    return result.content


def run():
    client = DocumentAnalysisClient(endpoint=AZURE_DI_ENDPOINT, credential=AzureKeyCredential(AZURE_DI_KEY))
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    for filename in os.listdir(SAMPLES_DIR):
        if not filename.lower().endswith((".pdf", ".jpg", ".jpeg", ".png")):
            continue

        file_path = os.path.join(SAMPLES_DIR, filename)
        print(f"Processing: {filename}")

        chunks, page_count = split_into_chunks(file_path)
        chunk_texts = []

        for i, chunk in enumerate(chunks, start=1):
            print(f"  Sending chunk {i}/{len(chunks)} to Azure Document Intelligence...")
            chunk_text = analyze_chunk(client, chunk)
            chunk_texts.append(chunk_text)
            print(f"  Chunk {i}/{len(chunks)} done.")

        full_text = "\n".join(chunk_texts)
        content_hash = hashlib.md5(full_text.encode("utf-8")).hexdigest()
        metadata = json.dumps({
            "filename": filename,
            "page_count": page_count,
            "chunks_processed": len(chunks),
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
            ("scanned_pdf", filename, full_text, metadata, content_hash, now, now),
        )

        print(f"Finished: {filename}")

    conn.commit()
    print("Done. All scanned PDFs processed.")

    cur.close()
    conn.close()


if __name__ == "__main__":
    run()
