CREATE TABLE IF NOT EXISTS indexing_targets (
    indexing_target_id TEXT PRIMARY KEY,
    postgres_schema TEXT NOT NULL DEFAULT 'public',
    vector_table TEXT NOT NULL CHECK (vector_table ~ '^idx_vec_[a-z0-9_]+$'),
    distance_ops TEXT NOT NULL CHECK (
        distance_ops IN ('vector_cosine_ops', 'vector_l2_ops', 'vector_ip_ops')
    ),
    storage_schema_version TEXT NOT NULL DEFAULT 'idx-vec-v1',
    active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deprecated_at TIMESTAMPTZ,
    UNIQUE (postgres_schema, vector_table)
);

CREATE INDEX IF NOT EXISTS idx_indexing_targets_active
    ON indexing_targets (active)
    WHERE active = true;

