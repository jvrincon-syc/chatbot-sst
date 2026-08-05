CREATE TABLE IF NOT EXISTS chunk_bundles (
    chunk_bundle_id TEXT PRIMARY KEY,
    bundle_fingerprint TEXT NOT NULL UNIQUE,
    profile_id TEXT NOT NULL,
    profile_fingerprint TEXT NOT NULL,
    corpus_version TEXT NOT NULL,
    source_document_id TEXT NOT NULL REFERENCES indexing_normalized_documents(document_id),
    artifact_relpath TEXT NOT NULL,
    parent_count INTEGER NOT NULL CHECK (parent_count >= 0),
    child_count INTEGER NOT NULL CHECK (child_count >= 0),
    status TEXT NOT NULL DEFAULT 'legacy_unverified' CHECK (
        status IN ('verified', 'legacy_unverified', 'compatibility_not_proven')
    ),
    created_at TIMESTAMPTZ,
    registered_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_chunk_bundles_source_document
    ON chunk_bundles (source_document_id);

CREATE INDEX IF NOT EXISTS idx_chunk_bundles_corpus_profile
    ON chunk_bundles (corpus_version, profile_id);

