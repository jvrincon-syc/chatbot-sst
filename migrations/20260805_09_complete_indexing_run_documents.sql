ALTER TABLE indexing_run_documents
    ADD COLUMN IF NOT EXISTS source_chunk_bundle_id TEXT,
    ADD COLUMN IF NOT EXISTS embedding_bundle_id TEXT,
    ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'legacy_unverified',
    ADD COLUMN IF NOT EXISTS parent_count INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS child_count INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS vector_count INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS committed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS internal_error_id TEXT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'indexing_run_documents_chunk_bundle_fk'
    ) THEN
        ALTER TABLE indexing_run_documents
            ADD CONSTRAINT indexing_run_documents_chunk_bundle_fk
            FOREIGN KEY (source_chunk_bundle_id)
            REFERENCES chunk_bundles(chunk_bundle_id);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'indexing_run_documents_embedding_bundle_fk'
    ) THEN
        ALTER TABLE indexing_run_documents
            ADD CONSTRAINT indexing_run_documents_embedding_bundle_fk
            FOREIGN KEY (embedding_bundle_id)
            REFERENCES embedding_bundles(embedding_bundle_id);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'indexing_run_documents_status_valid'
    ) THEN
        ALTER TABLE indexing_run_documents
            ADD CONSTRAINT indexing_run_documents_status_valid
            CHECK (status IN ('pending', 'running', 'committed', 'failed', 'skipped', 'legacy_unverified'));
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'indexing_run_documents_counts_non_negative'
    ) THEN
        ALTER TABLE indexing_run_documents
            ADD CONSTRAINT indexing_run_documents_counts_non_negative
            CHECK (parent_count >= 0 AND child_count >= 0 AND vector_count >= 0);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_indexing_run_documents_embedding_bundle
    ON indexing_run_documents (embedding_bundle_id);

CREATE INDEX IF NOT EXISTS idx_indexing_run_documents_status
    ON indexing_run_documents (status);

