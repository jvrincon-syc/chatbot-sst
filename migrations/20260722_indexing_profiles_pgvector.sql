CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS indexing_profiles (
    profile_id TEXT PRIMARY KEY,
    ingestion_origin TEXT NOT NULL CHECK (ingestion_origin IN ('local', 'llama_cloud')),
    chunking_version TEXT NOT NULL,
    embedding_provider TEXT NOT NULL CHECK (embedding_provider IN ('mock', 'bge', 'voyage', 'cohere')),
    embedding_model TEXT NOT NULL,
    embedding_dimension INTEGER NOT NULL CHECK (embedding_dimension > 0),
    distance_metric TEXT NOT NULL CHECK (distance_metric IN ('cosine', 'l2', 'inner_product')),
    vector_table TEXT NOT NULL UNIQUE CHECK (vector_table ~ '^idx_vec_[a-z0-9_]+$'),
    metadata_schema_version TEXT NOT NULL,
    config_hash TEXT NOT NULL CHECK (config_hash ~ '^[0-9a-f]{64}$'),
    active BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (ingestion_origin, embedding_provider, embedding_model, embedding_dimension, distance_metric, chunking_version)
);

CREATE TABLE IF NOT EXISTS indexing_normalized_documents (
    document_id TEXT PRIMARY KEY,
    source_relpath TEXT NOT NULL,
    source_hash TEXT NOT NULL CHECK (source_hash ~ '^[0-9a-f]{64}$'),
    ingestion_origin TEXT NOT NULL CHECK (ingestion_origin IN ('local', 'llama_cloud')),
    corpus_version TEXT NOT NULL,
    processing_status TEXT NOT NULL CHECK (processing_status IN ('processed', 'needs_review')),
    review_status TEXT NOT NULL DEFAULT 'approved',
    markdown_relpath TEXT NOT NULL,
    metadata_relpath TEXT NOT NULL,
    pages_relpath TEXT NOT NULL,
    tables_relpath TEXT NOT NULL,
    forms_relpath TEXT NOT NULL,
    artifact_fingerprint TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (document_id, source_hash, corpus_version)
);

CREATE TABLE IF NOT EXISTS indexing_runs (
    run_id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL REFERENCES indexing_profiles(profile_id),
    status TEXT NOT NULL CHECK (status IN ('pending', 'running', 'completed', 'failed', 'cancelled', 'blocked')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    config_hash TEXT NOT NULL CHECK (config_hash ~ '^[0-9a-f]{64}$'),
    summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    warnings JSONB NOT NULL DEFAULT '[]'::jsonb
);

CREATE TABLE IF NOT EXISTS indexing_run_documents (
    run_id TEXT NOT NULL REFERENCES indexing_runs(run_id) ON DELETE CASCADE,
    document_id TEXT NOT NULL REFERENCES indexing_normalized_documents(document_id),
    source_relpath TEXT NOT NULL,
    source_hash TEXT NOT NULL CHECK (source_hash ~ '^[0-9a-f]{64}$'),
    ingestion_origin TEXT NOT NULL CHECK (ingestion_origin IN ('local', 'llama_cloud')),
    eligibility_status TEXT NOT NULL CHECK (eligibility_status IN ('included', 'excluded', 'blocked')),
    eligibility_reason TEXT NOT NULL,
    indexed_parent_nodes INTEGER NOT NULL DEFAULT 0 CHECK (indexed_parent_nodes >= 0),
    indexed_child_nodes INTEGER NOT NULL DEFAULT 0 CHECK (indexed_child_nodes >= 0),
    error_code TEXT,
    PRIMARY KEY (run_id, document_id)
);

CREATE TABLE IF NOT EXISTS indexing_nodes (
    node_id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES indexing_normalized_documents(document_id),
    source_relpath TEXT NOT NULL,
    source_hash TEXT NOT NULL CHECK (source_hash ~ '^[0-9a-f]{64}$'),
    ingestion_origin TEXT NOT NULL CHECK (ingestion_origin IN ('local', 'llama_cloud')),
    node_role TEXT NOT NULL CHECK (node_role IN ('parent', 'child')),
    parent_node_id TEXT,
    chunk_index INTEGER,
    page_start INTEGER,
    page_end INTEGER,
    section_title TEXT,
    section_path TEXT,
    text TEXT NOT NULL,
    metadata JSONB NOT NULL,
    chunking_version TEXT NOT NULL,
    processing_fingerprint TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (node_role = 'parent' OR parent_node_id IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_indexing_nodes_document
    ON indexing_nodes (document_id);

CREATE INDEX IF NOT EXISTS idx_indexing_nodes_parent
    ON indexing_nodes (parent_node_id);

CREATE INDEX IF NOT EXISTS idx_indexing_nodes_metadata
    ON indexing_nodes USING gin (metadata);

-- profile vector tables are created through controlled migrations such as:
-- CREATE TABLE idx_vec_llama_bge_m3_v1 (
--     node_id TEXT PRIMARY KEY REFERENCES indexing_nodes(node_id) ON DELETE CASCADE,
--     document_id TEXT NOT NULL,
--     embedding vector(1024) NOT NULL,
--     metadata JSONB NOT NULL,
--     updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
-- );
-- CREATE INDEX idx_vec_llama_bge_m3_v1_hnsw
--     ON idx_vec_llama_bge_m3_v1 USING hnsw (embedding vector_cosine_ops);
