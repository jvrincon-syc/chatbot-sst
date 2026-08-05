DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'embedding_bundle_status_complete'
    ) THEN
        ALTER TABLE embedding_bundles
            ADD CONSTRAINT embedding_bundle_status_complete
            CHECK (
                status <> 'sealed'
                OR (
                    sealed_at IS NOT NULL
                    AND vector_count > 0
                    AND vector_dtype IS NOT NULL
                    AND vector_shape IS NOT NULL
                    AND vector_artifact_relpath IS NOT NULL
                    AND chunk_map_relpath IS NOT NULL
                    AND validation_status = 'passed'
                )
            );
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'embedding_bundle_chunks_checksum_when_sealed'
    ) THEN
        ALTER TABLE embedding_bundle_chunks
            ADD CONSTRAINT embedding_bundle_chunks_checksum_when_sealed
            CHECK (vector_checksum IS NULL OR length(trim(vector_checksum)) > 0);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'embedding_bundles_legacy_status_explicit'
    ) THEN
        ALTER TABLE embedding_bundles
            ADD CONSTRAINT embedding_bundles_legacy_status_explicit
            CHECK (
                validation_status NOT IN ('legacy_unverified', 'compatibility_not_proven')
                OR status = 'legacy_unverified'
            );
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS idx_retrieval_profiles_verified_active_scope_corpus
    ON retrieval_profiles (consumer_scope_type, consumer_scope_id, corpus_version)
    WHERE active = true AND validation_status = 'passed';

CREATE UNIQUE INDEX IF NOT EXISTS idx_embedding_bundle_chunks_no_duplicate_child
    ON embedding_bundle_chunks (embedding_bundle_id, child_chunk_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_embedding_bundles_one_ready_snapshot
    ON embedding_bundles (
        source_chunk_bundle_id,
        embedding_profile_id,
        configuration_fingerprint,
        corpus_version,
        source_content_fingerprint,
        bundle_schema_version
    )
    WHERE validation_status = 'passed';

