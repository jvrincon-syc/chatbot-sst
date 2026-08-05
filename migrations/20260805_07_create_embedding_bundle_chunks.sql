CREATE TABLE IF NOT EXISTS embedding_bundle_chunks (
    embedding_bundle_id TEXT NOT NULL REFERENCES embedding_bundles(embedding_bundle_id) ON DELETE CASCADE,
    child_chunk_id TEXT NOT NULL,
    parent_chunk_id TEXT NOT NULL,
    document_id TEXT NOT NULL REFERENCES indexing_normalized_documents(document_id),
    vector_offset INTEGER NOT NULL CHECK (vector_offset >= 0),
    vector_length INTEGER NOT NULL CHECK (vector_length > 0),
    vector_checksum TEXT,
    content_hash TEXT NOT NULL,
    chunk_ordinal INTEGER NOT NULL CHECK (chunk_ordinal >= 0),
    PRIMARY KEY (embedding_bundle_id, child_chunk_id),
    UNIQUE (embedding_bundle_id, chunk_ordinal),
    UNIQUE (embedding_bundle_id, vector_offset)
);

CREATE INDEX IF NOT EXISTS idx_embedding_bundle_chunks_document
    ON embedding_bundle_chunks (document_id);

CREATE INDEX IF NOT EXISTS idx_embedding_bundle_chunks_parent
    ON embedding_bundle_chunks (parent_chunk_id);

