INSERT INTO indexing_profiles (
    profile_id,
    ingestion_origin,
    chunking_version,
    embedding_provider,
    embedding_model,
    embedding_dimension,
    distance_metric,
    vector_table,
    metadata_schema_version,
    config_hash,
    active
) VALUES
    (
        'llama-first-local-v1',
        'local',
        'structure-aware-v1',
        'mock',
        'deterministic',
        384,
        'cosine',
        'idx_vec_llama_first_local_v1',
        '2.0',
        '298f95d57748303abdd04422e6df8e3577334c207db56cbf3d4bb0eaaeb64e84',
        true
    ),
    (
        'local-bge-m3-v1',
        'local',
        'structure-aware-v1',
        'bge',
        'BAAI/bge-m3',
        1024,
        'cosine',
        'idx_vec_local_bge_m3_v1',
        '2.0',
        '2dfa20977fe0e9e56fbc7d537b1c51f2f22c9e2ef9462ed283282a2f11537c97',
        true
    ),
    (
        'llama-bge-m3-v1',
        'llama_cloud',
        'structure-aware-v1',
        'bge',
        'BAAI/bge-m3',
        1024,
        'cosine',
        'idx_vec_llama_bge_m3_v1',
        '2.0',
        '074fce8109b3f2ac90aebfe973a89ddd6e8c328f2c4738207f35f07e1091cd6a',
        true
    ),
    (
        'local-voyage-4-v1',
        'local',
        'structure-aware-v1',
        'voyage',
        'voyage-4',
        1024,
        'cosine',
        'idx_vec_local_voyage_4_v1',
        '2.0',
        '82c96c50491562136ff57e2d1c91139483ab7dc7c8e79bff25d4f90b6a941e87',
        true
    ),
    (
        'llama-voyage-4-v1',
        'llama_cloud',
        'structure-aware-v1',
        'voyage',
        'voyage-4',
        1024,
        'cosine',
        'idx_vec_llama_voyage_4_v1',
        '2.0',
        'e60435283fca55cbf94a55ecbca624779edf8bb31c38ab951beec13eebee843d',
        true
    ),
    (
        'local-cohere-embed-v4-v1',
        'local',
        'structure-aware-v1',
        'cohere',
        'embed-v4.0',
        1536,
        'cosine',
        'idx_vec_local_cohere_embed_v4_v1',
        '2.0',
        '94d13788b59495b6d56adf36b83236fbee0b469502ba1cedeba8a21d592a384e',
        true
    ),
    (
        'llama-cohere-embed-v4-v1',
        'llama_cloud',
        'structure-aware-v1',
        'cohere',
        'embed-v4.0',
        1536,
        'cosine',
        'idx_vec_llama_cohere_embed_v4_v1',
        '2.0',
        '667c082dabb54aa2d82bd47946fe2dc7c3dc33afc776f63d6834f71879d63510',
        true
    )
ON CONFLICT (profile_id) DO UPDATE SET
    active = EXCLUDED.active;

CREATE TABLE IF NOT EXISTS idx_vec_llama_first_local_v1 (
    node_id TEXT PRIMARY KEY REFERENCES indexing_nodes(node_id) ON DELETE CASCADE,
    document_id TEXT NOT NULL,
    embedding vector(384) NOT NULL,
    metadata JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS idx_vec_local_bge_m3_v1 (
    node_id TEXT PRIMARY KEY REFERENCES indexing_nodes(node_id) ON DELETE CASCADE,
    document_id TEXT NOT NULL,
    embedding vector(1024) NOT NULL,
    metadata JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS idx_vec_llama_bge_m3_v1 (
    node_id TEXT PRIMARY KEY REFERENCES indexing_nodes(node_id) ON DELETE CASCADE,
    document_id TEXT NOT NULL,
    embedding vector(1024) NOT NULL,
    metadata JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS idx_vec_local_voyage_4_v1 (
    node_id TEXT PRIMARY KEY REFERENCES indexing_nodes(node_id) ON DELETE CASCADE,
    document_id TEXT NOT NULL,
    embedding vector(1024) NOT NULL,
    metadata JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS idx_vec_llama_voyage_4_v1 (
    node_id TEXT PRIMARY KEY REFERENCES indexing_nodes(node_id) ON DELETE CASCADE,
    document_id TEXT NOT NULL,
    embedding vector(1024) NOT NULL,
    metadata JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS idx_vec_local_cohere_embed_v4_v1 (
    node_id TEXT PRIMARY KEY REFERENCES indexing_nodes(node_id) ON DELETE CASCADE,
    document_id TEXT NOT NULL,
    embedding vector(1536) NOT NULL,
    metadata JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS idx_vec_llama_cohere_embed_v4_v1 (
    node_id TEXT PRIMARY KEY REFERENCES indexing_nodes(node_id) ON DELETE CASCADE,
    document_id TEXT NOT NULL,
    embedding vector(1536) NOT NULL,
    metadata JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_vec_llama_first_local_v1_document_id
    ON idx_vec_llama_first_local_v1 (document_id);
CREATE INDEX IF NOT EXISTS idx_vec_llama_first_local_v1_metadata
    ON idx_vec_llama_first_local_v1 USING gin (metadata);
CREATE INDEX IF NOT EXISTS idx_vec_llama_first_local_v1_hnsw
    ON idx_vec_llama_first_local_v1 USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS idx_vec_local_bge_m3_v1_document_id
    ON idx_vec_local_bge_m3_v1 (document_id);
CREATE INDEX IF NOT EXISTS idx_vec_local_bge_m3_v1_metadata
    ON idx_vec_local_bge_m3_v1 USING gin (metadata);
CREATE INDEX IF NOT EXISTS idx_vec_local_bge_m3_v1_hnsw
    ON idx_vec_local_bge_m3_v1 USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS idx_vec_llama_bge_m3_v1_document_id
    ON idx_vec_llama_bge_m3_v1 (document_id);
CREATE INDEX IF NOT EXISTS idx_vec_llama_bge_m3_v1_metadata
    ON idx_vec_llama_bge_m3_v1 USING gin (metadata);
CREATE INDEX IF NOT EXISTS idx_vec_llama_bge_m3_v1_hnsw
    ON idx_vec_llama_bge_m3_v1 USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS idx_vec_local_voyage_4_v1_document_id
    ON idx_vec_local_voyage_4_v1 (document_id);
CREATE INDEX IF NOT EXISTS idx_vec_local_voyage_4_v1_metadata
    ON idx_vec_local_voyage_4_v1 USING gin (metadata);
CREATE INDEX IF NOT EXISTS idx_vec_local_voyage_4_v1_hnsw
    ON idx_vec_local_voyage_4_v1 USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS idx_vec_llama_voyage_4_v1_document_id
    ON idx_vec_llama_voyage_4_v1 (document_id);
CREATE INDEX IF NOT EXISTS idx_vec_llama_voyage_4_v1_metadata
    ON idx_vec_llama_voyage_4_v1 USING gin (metadata);
CREATE INDEX IF NOT EXISTS idx_vec_llama_voyage_4_v1_hnsw
    ON idx_vec_llama_voyage_4_v1 USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS idx_vec_local_cohere_embed_v4_v1_document_id
    ON idx_vec_local_cohere_embed_v4_v1 (document_id);
CREATE INDEX IF NOT EXISTS idx_vec_local_cohere_embed_v4_v1_metadata
    ON idx_vec_local_cohere_embed_v4_v1 USING gin (metadata);
CREATE INDEX IF NOT EXISTS idx_vec_local_cohere_embed_v4_v1_hnsw
    ON idx_vec_local_cohere_embed_v4_v1 USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS idx_vec_llama_cohere_embed_v4_v1_document_id
    ON idx_vec_llama_cohere_embed_v4_v1 (document_id);
CREATE INDEX IF NOT EXISTS idx_vec_llama_cohere_embed_v4_v1_metadata
    ON idx_vec_llama_cohere_embed_v4_v1 USING gin (metadata);
CREATE INDEX IF NOT EXISTS idx_vec_llama_cohere_embed_v4_v1_hnsw
    ON idx_vec_llama_cohere_embed_v4_v1 USING hnsw (embedding vector_cosine_ops);
