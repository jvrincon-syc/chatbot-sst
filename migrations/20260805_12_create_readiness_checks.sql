CREATE TABLE IF NOT EXISTS readiness_checks (
    check_id TEXT PRIMARY KEY,
    check_kind TEXT NOT NULL CHECK (
        check_kind IN (
            'embedding_bundle_validation',
            'indexing_readiness',
            'retrieval_readiness'
        )
    ),
    subject_id TEXT NOT NULL,
    embedding_profile_id TEXT REFERENCES indexing_profiles(profile_id),
    indexing_target_id TEXT REFERENCES indexing_targets(indexing_target_id),
    status TEXT NOT NULL CHECK (
        status IN ('pending', 'passed', 'failed', 'blocked', 'legacy_unverified')
    ),
    validator_version TEXT NOT NULL,
    report_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_readiness_checks_subject
    ON readiness_checks (check_kind, subject_id);

CREATE INDEX IF NOT EXISTS idx_readiness_checks_profile_target_status
    ON readiness_checks (embedding_profile_id, indexing_target_id, status);

