CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS llama_index_documents (
    node_id TEXT PRIMARY KEY,
    ref_doc_id TEXT NOT NULL,
    node_role TEXT NOT NULL,
    page_number INTEGER,
    metadata JSONB NOT NULL,
    text TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_llama_index_documents_ref_doc_id
    ON llama_index_documents (ref_doc_id);

CREATE TABLE IF NOT EXISTS llama_index_vectors (
    node_id TEXT PRIMARY KEY REFERENCES llama_index_documents(node_id)
        ON DELETE CASCADE,
    ref_doc_id TEXT NOT NULL,
    embedding_profile TEXT NOT NULL,
    embedding_model TEXT NOT NULL,
    embedding_dimension INTEGER NOT NULL,
    embedding vector,
    metadata JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_llama_index_vectors_ref_doc_id
    ON llama_index_vectors (ref_doc_id);

CREATE INDEX IF NOT EXISTS idx_llama_index_vectors_profile
    ON llama_index_vectors (embedding_profile, embedding_model, embedding_dimension);
