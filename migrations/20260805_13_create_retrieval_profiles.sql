CREATE TABLE IF NOT EXISTS retrieval_profiles (
    retrieval_profile_id TEXT PRIMARY KEY,
    consumer_scope_type TEXT NOT NULL,
    consumer_scope_id TEXT NOT NULL,
    corpus_version TEXT NOT NULL,
    embedding_profile_id TEXT NOT NULL REFERENCES indexing_profiles(profile_id),
    indexing_target_id TEXT NOT NULL REFERENCES indexing_targets(indexing_target_id),
    lexical_fallback_policy TEXT NOT NULL DEFAULT 'allowed_when_vector_unavailable',
    active BOOLEAN NOT NULL DEFAULT false,
    validation_status TEXT NOT NULL DEFAULT 'pending' CHECK (
        validation_status IN ('pending', 'passed', 'failed', 'compatibility_not_proven')
    ),
    validated_at TIMESTAMPTZ,
    last_runtime_status TEXT NOT NULL DEFAULT 'never_run' CHECK (
        last_runtime_status IN ('never_run', 'ok', 'failed', 'blocked')
    ),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deprecated_at TIMESTAMPTZ
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_retrieval_profiles_one_active_scope_corpus
    ON retrieval_profiles (consumer_scope_type, consumer_scope_id, corpus_version)
    WHERE active = true;

CREATE INDEX IF NOT EXISTS idx_retrieval_profiles_profile_target
    ON retrieval_profiles (embedding_profile_id, indexing_target_id);

