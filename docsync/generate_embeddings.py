import psycopg2
from sentence_transformers import SentenceTransformer


def run():
    conn = psycopg2.connect(
        host="127.0.0.1",
        port=5432,
        dbname="docsync",
        user="admin",
        password="secret",
    )

    try:
        with conn.cursor() as cur:
            cur.execute("SELECT row_id, raw_text FROM documents WHERE embedding IS NULL")
            rows = cur.fetchall()

            if not rows:
                print("No rows found with NULL embeddings.")
                return

            model = SentenceTransformer("all-MiniLM-L6-v2")
            embedded_count = 0

            for row_id, raw_text in rows:
                embedding = model.encode(raw_text)
                embedding_list = embedding.tolist() if hasattr(embedding, "tolist") else list(embedding)

                cur.execute(
                    "UPDATE documents SET embedding = %s WHERE row_id = %s",
                    (str(embedding_list), row_id),
                )
                embedded_count += 1
                print(f"Updated embedding for row_id={row_id}")

        conn.commit()
        print(f"Embedded {embedded_count} row(s).")
    finally:
        conn.close()


if __name__ == "__main__":
    run()
