CREATE TABLE IF NOT EXISTS embedding_runs (
    embedding_run_id TEXT PRIMARY KEY,
    idempotency_key TEXT NOT NULL,
    request_fingerprint TEXT NOT NULL CHECK (request_fingerprint ~ '^[0-9a-f]{64}$'),
    source_chunk_bundle_id TEXT NOT NULL REFERENCES chunk_bundles(chunk_bundle_id),
    embedding_profile_id TEXT NOT NULL REFERENCES indexing_profiles(profile_id),
    configuration_fingerprint TEXT CHECK (configuration_fingerprint ~ '^[0-9a-f]{64}$'),
    runtime_engine TEXT NOT NULL,
    runtime_mode TEXT NOT NULL CHECK (
        runtime_mode IN ('local', 'cloud', 'dry_run', 'legacy')
    ),
    engine_revision_observed TEXT NOT NULL DEFAULT 'unknown_revision',
    status TEXT NOT NULL CHECK (
        status IN ('pending', 'running', 'completed', 'failed', 'cancelled', 'blocked')
    ),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    warnings_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    error_summary TEXT,
    produced_embedding_bundle_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (idempotency_key, request_fingerprint)
);

CREATE INDEX IF NOT EXISTS idx_embedding_runs_idempotency_key
    ON embedding_runs (idempotency_key);

CREATE INDEX IF NOT EXISTS idx_embedding_runs_source_chunk_bundle
    ON embedding_runs (source_chunk_bundle_id);

CREATE INDEX IF NOT EXISTS idx_embedding_runs_profile_status
    ON embedding_runs (embedding_profile_id, status);

