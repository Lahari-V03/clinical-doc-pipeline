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

# --- Model selector ---
# prebuilt-read     : plain text extraction (scanned notes, discharge summaries)
# prebuilt-layout   : preserves tables, checkboxes, form structure (prior auth, EOBs)
# prebuilt-document : key-value pairs from general forms (claims attachments)
SUPPORTED_MODELS = ["prebuilt-read", "prebuilt-layout", "prebuilt-document"]

# Confidence threshold below which a document is flagged for human review
CONFIDENCE_THRESHOLD = 0.80

# Where low-confidence documents get routed for human review
QA_REVIEW_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "qa", "review", "pending"
)


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


def analyze_chunk(client, chunk, model):
    """
    Analyze a single chunk using the specified Azure DI model.
    Returns extracted text and a confidence score.

    - prebuilt-read     : averages word-level confidence scores
    - prebuilt-layout   : averages cell confidence scores from tables
    - prebuilt-document : averages key-value pair confidence scores
    """
    if model not in SUPPORTED_MODELS:
        raise ValueError(f"Unsupported model '{model}'. Choose from: {SUPPORTED_MODELS}")

    poller = client.begin_analyze_document(model, document=chunk)
    result = poller.result()

    text = result.content
    confidence = _extract_confidence(result, model)

    return text, confidence


def _extract_confidence(result, model):
    """
    Extract a representative confidence score from the Azure DI result
    depending on which model was used.
    """
    scores = []

    if model == "prebuilt-read":
        for page in result.pages:
            for word in page.words:
                if word.confidence is not None:
                    scores.append(word.confidence)

    elif model == "prebuilt-layout":
        # Note: Azure SDK 3.3.x does not expose confidence scores on DocumentTableCell.
        # Table cell confidence is a known limitation of this SDK version.
        # Falling back to word-level confidence as a reliable proxy.
        # To-Do: Upgrade to azure-ai-documentintelligence SDK for cell-level confidence.
        for page in result.pages:
            for word in page.words:
                if word.confidence is not None:
                    scores.append(word.confidence)

    elif model == "prebuilt-document":
        if hasattr(result, "key_value_pairs"):
            for kv in result.key_value_pairs:
                if kv.confidence is not None:
                    scores.append(kv.confidence)
        # Fall back to word confidence if no key-value pairs found
        if not scores:
            for page in result.pages:
                for word in page.words:
                    if word.confidence is not None:
                        scores.append(word.confidence)

    return round(sum(scores) / len(scores), 4) if scores else 1.0


def flag_for_review(filename, full_text, confidence, model, reason):
    """
    Route low-confidence documents to the QA review queue.
    Writes a JSON file to qa/review/pending/ for human inspection.
    """
    os.makedirs(QA_REVIEW_DIR, exist_ok=True)

    review_record = {
        "filename": filename,
        "model_used": model,
        "confidence_score": confidence,
        "flag_reason": reason,
        "flagged_at": datetime.now().isoformat(),
        "extracted_text_preview": full_text[:500],  # first 500 chars for quick review
    }

    review_path = os.path.join(QA_REVIEW_DIR, f"review_{filename}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(review_path, "w") as f:
        json.dump(review_record, f, indent=2)

    print(f"  ⚠️  Flagged for human review → {review_path}")
    return review_path


def run(model="prebuilt-read"):
    """
    Run the scanned document ingestion pipeline.

    Args:
        model: Azure DI model to use for extraction.
               - 'prebuilt-read'     for plain scanned text
               - 'prebuilt-layout'   for forms with tables/checkboxes (prior auth, EOBs)
               - 'prebuilt-document' for key-value structured forms (claims attachments)
    """
    if model not in SUPPORTED_MODELS:
        raise ValueError(f"Unsupported model '{model}'. Choose from: {SUPPORTED_MODELS}")

    print(f"Starting scanned document pipeline | Model: {model}")

    client = DocumentAnalysisClient(endpoint=AZURE_DI_ENDPOINT, credential=AzureKeyCredential(AZURE_DI_KEY))
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    for filename in os.listdir(SAMPLES_DIR):
        if not filename.lower().endswith((".pdf", ".jpg", ".jpeg", ".png")):
            continue

        file_path = os.path.join(SAMPLES_DIR, filename)
        print(f"\nProcessing: {filename}")

        chunks, page_count = split_into_chunks(file_path)
        chunk_texts = []
        chunk_confidences = []

        for i, chunk in enumerate(chunks, start=1):
            print(f"  Sending chunk {i}/{len(chunks)} to Azure DI [{model}]...")
            chunk_text, chunk_confidence = analyze_chunk(client, chunk, model)
            chunk_texts.append(chunk_text)
            chunk_confidences.append(chunk_confidence)
            print(f"  Chunk {i}/{len(chunks)} done | Confidence: {chunk_confidence}")

        full_text = "\n".join(chunk_texts)
        avg_confidence = round(sum(chunk_confidences) / len(chunk_confidences), 4)
        needs_review = avg_confidence < CONFIDENCE_THRESHOLD

        print(f"  Overall confidence: {avg_confidence} | Needs review: {needs_review}")

        # Route to QA review queue if confidence is below threshold
        review_path = None
        if needs_review:
            reason = f"Average confidence {avg_confidence} below threshold {CONFIDENCE_THRESHOLD}"
            review_path = flag_for_review(filename, full_text, avg_confidence, model, reason)

        content_hash = hashlib.md5(full_text.encode("utf-8")).hexdigest()
        metadata = json.dumps({
            "filename": filename,
            "page_count": page_count,
            "chunks_processed": len(chunks),
            "model_used": model,
            "confidence_score": avg_confidence,
            "needs_review": needs_review,
            "review_file": review_path,
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

        status = "⚠️  flagged for review" if needs_review else "✅ passed QA"
        print(f"  Saved to DB | {status}")

    conn.commit()
    print("\nDone. All scanned documents processed.")

    cur.close()
    conn.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Clinical scanned document ingestion pipeline")
    parser.add_argument(
        "--model",
        type=str,
        default="prebuilt-read",
        choices=SUPPORTED_MODELS,
        help=(
            "Azure Document Intelligence model to use:\n"
            "  prebuilt-read     → plain text (scanned notes, discharge summaries)\n"
            "  prebuilt-layout   → tables + forms (prior auth, EOBs)\n"
            "  prebuilt-document → key-value pairs (claims attachments)\n"
        ),
    )
    args = parser.parse_args()
    run(model=args.model)
