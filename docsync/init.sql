CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS documents (
  row_id        UUID      PRIMARY KEY DEFAULT gen_random_uuid(),
  source_type   TEXT,
  source_id     TEXT,
  raw_text      TEXT,
  metadata      JSONB,
  content_hash  TEXT      UNIQUE,
  embedding     vector(384),
  created_at    TIMESTAMP,
  updated_at    TIMESTAMP,
  CONSTRAINT unique_source UNIQUE (source_type, source_id)
);