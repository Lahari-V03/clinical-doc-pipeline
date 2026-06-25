import hashlib
import json
import os
from datetime import datetime

import psycopg2

JSON_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "samples", "json", "sample_data.json"
)

DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 5432,
    "dbname": "docsync",
    "user": "admin",
    "password": "secret",
}


def run():
    with open(JSON_PATH, "r", encoding="utf-8") as f:
        records = json.load(f)

    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    for record in records:
        raw_text = record["content"]
        content_hash = hashlib.md5(raw_text.encode("utf-8")).hexdigest()
        metadata = json.dumps({
            "title": record["title"],
            "author": record["author"],
            "category": record["category"],
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
            ("json_export", record["id"], raw_text, metadata, content_hash, now, now),
        )

        print(f"Inserted: {record['id']}")

    conn.commit()
    print("Done. All JSON records processed.")

    cur.close()
    conn.close()


if __name__ == "__main__":
    run()
