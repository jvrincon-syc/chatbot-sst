ALTER TABLE indexing_runs
    ADD COLUMN IF NOT EXISTS embedding_bundle_id TEXT,
    ADD COLUMN IF NOT EXISTS embedding_profile_id TEXT,
    ADD COLUMN IF NOT EXISTS indexing_target_id TEXT,
    ADD COLUMN IF NOT EXISTS corpus_version TEXT,
    ADD COLUMN IF NOT EXISTS request_fingerprint TEXT,
    ADD COLUMN IF NOT EXISTS idempotency_key TEXT,
    ADD COLUMN IF NOT EXISTS validation_status TEXT NOT NULL DEFAULT 'pending',
    ADD COLUMN IF NOT EXISTS activation_status TEXT NOT NULL DEFAULT 'pending',
    ADD COLUMN IF NOT EXISTS owner_id TEXT,
    ADD COLUMN IF NOT EXISTS lease_expires_at TIMESTAMPTZ;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'indexing_runs_embedding_bundle_fk'
    ) THEN
        ALTER TABLE indexing_runs
            ADD CONSTRAINT indexing_runs_embedding_bundle_fk
            FOREIGN KEY (embedding_bundle_id)
            REFERENCES embedding_bundles(embedding_bundle_id);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'indexing_runs_embedding_profile_fk'
    ) THEN
        ALTER TABLE indexing_runs
            ADD CONSTRAINT indexing_runs_embedding_profile_fk
            FOREIGN KEY (embedding_profile_id)
            REFERENCES indexing_profiles(profile_id);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'indexing_runs_target_fk'
    ) THEN
        ALTER TABLE indexing_runs
            ADD CONSTRAINT indexing_runs_target_fk
            FOREIGN KEY (indexing_target_id)
            REFERENCES indexing_targets(indexing_target_id);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'indexing_runs_validation_status_valid'
    ) THEN
        ALTER TABLE indexing_runs
            ADD CONSTRAINT indexing_runs_validation_status_valid
            CHECK (validation_status IN ('pending', 'passed', 'failed', 'legacy_unverified', 'compatibility_not_proven'));
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'indexing_runs_activation_status_valid'
    ) THEN
        ALTER TABLE indexing_runs
            ADD CONSTRAINT indexing_runs_activation_status_valid
            CHECK (activation_status IN ('pending', 'active', 'inactive', 'rolled_back', 'blocked', 'legacy_unverified'));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_indexing_runs_embedding_bundle
    ON indexing_runs (embedding_bundle_id);

CREATE INDEX IF NOT EXISTS idx_indexing_runs_target_corpus
    ON indexing_runs (indexing_target_id, corpus_version);

CREATE UNIQUE INDEX IF NOT EXISTS idx_indexing_runs_idempotency_request
    ON indexing_runs (idempotency_key, request_fingerprint)
    WHERE idempotency_key IS NOT NULL AND request_fingerprint IS NOT NULL;

