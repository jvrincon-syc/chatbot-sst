-- Project-owned raw and normalized artifact catalogs (platform-only).
--
-- Additive migration: it does not alter legacy or platform tables already in
-- use. The existing logical catalogs remain the source of truth for identity:
--   - project_documents
--   - source_document_revisions
--   - project_normalized_documents
--
-- These new tables persist the filesystem artifact catalogs under:
--   data/projects/{project_id}/raw
--   data/projects/{project_id}/normalized
--
-- Goals:
--   1) Raw artifacts become queryable in PostgreSQL per project.
--   2) Normalized artifacts persist project ownership and the processing recipe
--      snapshot used to produce them (local vs llama_cloud, provider, engine,
--      observed revision, sanitized config).
--   3) When a normalized artifact is produced inside a platform build context,
--      the row may also pin rag_variant_id + semantic_recipe_fingerprint for
--      auditability without making the physical artifact owned by the release.

CREATE TABLE IF NOT EXISTS project_raw_document_artifacts (
    source_document_revision_id TEXT PRIMARY KEY
        REFERENCES source_document_revisions(source_document_revision_id),
    project_id TEXT NOT NULL REFERENCES rag_projects(project_id),
    logical_document_id TEXT NOT NULL
        REFERENCES project_documents(logical_document_id),
    artifact_relpath TEXT NOT NULL,
    source_relpath TEXT NOT NULL,
    raw_content_hash TEXT NOT NULL
        CHECK (raw_content_hash ~ '^[0-9a-f]{64}$'),
    file_size BIGINT NOT NULL CHECK (file_size >= 0),
    uploaded_by TEXT NOT NULL,
    uploaded_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (project_id, artifact_relpath)
);

CREATE INDEX IF NOT EXISTS idx_project_raw_document_artifacts_project
    ON project_raw_document_artifacts (project_id);

CREATE INDEX IF NOT EXISTS idx_project_raw_document_artifacts_logical
    ON project_raw_document_artifacts (logical_document_id);


CREATE TABLE IF NOT EXISTS project_normalized_document_artifacts (
    normalized_document_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES rag_projects(project_id),
    source_document_revision_id TEXT NOT NULL
        REFERENCES source_document_revisions(source_document_revision_id),
    logical_document_id TEXT NOT NULL
        REFERENCES project_documents(logical_document_id),
    rag_variant_id TEXT REFERENCES rag_variants(rag_variant_id),
    semantic_recipe_fingerprint TEXT
        CHECK (
            semantic_recipe_fingerprint IS NULL
            OR semantic_recipe_fingerprint ~ '^[0-9a-f]{64}$'
        ),
    processing_profile_id TEXT NOT NULL
        REFERENCES document_processing_profiles(processing_profile_id),
    processing_profile_fingerprint TEXT NOT NULL
        CHECK (processing_profile_fingerprint ~ '^[0-9a-f]{64}$'),
    processing_origin TEXT NOT NULL
        CHECK (processing_origin IN ('local', 'llama_cloud')),
    parser_provider TEXT NOT NULL,
    parser_engine TEXT NOT NULL,
    observed_revision TEXT NOT NULL,
    sanitized_config_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    schema_version TEXT NOT NULL,
    markdown_relpath TEXT NOT NULL,
    metadata_relpath TEXT NOT NULL,
    pages_relpath TEXT NOT NULL,
    tables_relpath TEXT NOT NULL,
    forms_relpath TEXT NOT NULL,
    source_hash TEXT NOT NULL CHECK (source_hash ~ '^[0-9a-f]{64}$'),
    processing_status TEXT NOT NULL
        CHECK (processing_status IN ('processed', 'needs_review')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (
        project_id,
        source_document_revision_id,
        processing_profile_fingerprint
    ),
    UNIQUE (project_id, markdown_relpath),
    UNIQUE (project_id, metadata_relpath),
    FOREIGN KEY (
        project_id,
        source_document_revision_id,
        processing_profile_fingerprint
    ) REFERENCES project_normalized_documents (
        project_id,
        source_document_revision_id,
        processing_profile_fingerprint
    ),
    CHECK (
        (rag_variant_id IS NULL AND semantic_recipe_fingerprint IS NULL)
        OR (rag_variant_id IS NOT NULL AND semantic_recipe_fingerprint IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_project_normalized_document_artifacts_project
    ON project_normalized_document_artifacts (project_id);

CREATE INDEX IF NOT EXISTS idx_project_normalized_document_artifacts_variant
    ON project_normalized_document_artifacts (project_id, rag_variant_id);

CREATE INDEX IF NOT EXISTS idx_project_normalized_document_artifacts_processing
    ON project_normalized_document_artifacts (
        project_id,
        processing_profile_id,
        processing_profile_fingerprint
    );
