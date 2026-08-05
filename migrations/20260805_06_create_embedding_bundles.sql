CREATE TABLE IF NOT EXISTS embedding_bundles (
    embedding_bundle_id TEXT PRIMARY KEY,
    source_chunk_bundle_id TEXT NOT NULL REFERENCES chunk_bundles(chunk_bundle_id),
    embedding_profile_id TEXT NOT NULL REFERENCES indexing_profiles(profile_id),
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    model_revision TEXT NOT NULL DEFAULT 'unknown_revision',
    dimension INTEGER NOT NULL CHECK (dimension > 0),
    normalization TEXT NOT NULL DEFAULT 'unknown_normalization',
    distance_metric TEXT NOT NULL CHECK (distance_metric IN ('cosine', 'l2', 'inner_product')),
    configuration_fingerprint TEXT NOT NULL CHECK (configuration_fingerprint ~ '^[0-9a-f]{64}$'),
    corpus_version TEXT NOT NULL,
    semantic_config_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    bundle_schema_version TEXT NOT NULL DEFAULT 'embedding-bundle-v1',
    source_content_fingerprint TEXT NOT NULL,
    vector_artifact_relpath TEXT,
    chunk_map_relpath TEXT,
    vector_dtype TEXT,
    vector_shape TEXT,
    vector_count INTEGER NOT NULL DEFAULT 0 CHECK (vector_count >= 0),
    checksums_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL CHECK (
        status IN ('pending', 'sealed', 'failed', 'legacy_unverified')
    ),
    validation_status TEXT NOT NULL DEFAULT 'compatibility_not_proven' CHECK (
        validation_status IN ('pending', 'passed', 'failed', 'legacy_unverified', 'compatibility_not_proven')
    ),
    readiness_status TEXT NOT NULL DEFAULT 'pending' CHECK (
        readiness_status IN ('pending', 'ready', 'blocked', 'legacy_unverified', 'compatibility_not_proven')
    ),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    sealed_at TIMESTAMPTZ,
    UNIQUE (
        source_chunk_bundle_id,
        embedding_profile_id,
        configuration_fingerprint,
        corpus_version,
        source_content_fingerprint,
        bundle_schema_version
    )
);

CREATE INDEX IF NOT EXISTS idx_embedding_bundles_source_chunk_bundle
    ON embedding_bundles (source_chunk_bundle_id);

CREATE INDEX IF NOT EXISTS idx_embedding_bundles_profile_corpus
    ON embedding_bundles (embedding_profile_id, corpus_version);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conname = 'embedding_runs_produced_bundle_fk'
    ) THEN
        ALTER TABLE embedding_runs
            ADD CONSTRAINT embedding_runs_produced_bundle_fk
            FOREIGN KEY (produced_embedding_bundle_id)
            REFERENCES embedding_bundles(embedding_bundle_id);
    END IF;
END $$;

