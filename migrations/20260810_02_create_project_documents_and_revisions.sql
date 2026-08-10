-- RAG platform documents and revisions (Fase 2). Additive over legacy; touches
-- no legacy table. Every statement is CREATE ... IF NOT EXISTS, ordered after
-- 20260810_01. The new identity is project + logical document + revision hash;
-- source_relpath is only a versioned locator (ADR-006 §2.2).

-- Logical document within a project. Identity is (project_id, logical_document_id);
-- source_relpath may change without colliding across projects.
CREATE TABLE IF NOT EXISTS project_documents (
    logical_document_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES rag_projects(project_id),
    source_relpath TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (project_id, source_relpath)
);

-- Immutable document revision. A changed raw stream (distinct raw_content_hash)
-- yields a new revision; the previous one is never overwritten.
CREATE TABLE IF NOT EXISTS source_document_revisions (
    source_document_revision_id TEXT PRIMARY KEY,
    logical_document_id TEXT NOT NULL REFERENCES project_documents(logical_document_id),
    project_id TEXT NOT NULL REFERENCES rag_projects(project_id),
    source_relpath TEXT NOT NULL,
    raw_content_hash TEXT NOT NULL,
    file_size BIGINT NOT NULL CHECK (file_size >= 0),
    uploaded_by TEXT NOT NULL,
    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    review_state TEXT NOT NULL DEFAULT 'processed'
        CHECK (review_state IN ('processed', 'needs_review')),
    -- One revision per (project, logical document, raw bytes): re-uploading the
    -- exact same bytes is idempotent, different bytes create a new revision.
    UNIQUE (project_id, logical_document_id, raw_content_hash)
);

CREATE INDEX IF NOT EXISTS idx_source_document_revisions_document
    ON source_document_revisions (logical_document_id);

-- Normalized artifact per revision and processing recipe. Identity is
-- (project_id, source_document_revision_id, processing_profile_fingerprint);
-- plan §4.4. Reuse is exact-identity only.
CREATE TABLE IF NOT EXISTS project_normalized_documents (
    project_id TEXT NOT NULL REFERENCES rag_projects(project_id),
    source_document_revision_id TEXT NOT NULL
        REFERENCES source_document_revisions(source_document_revision_id),
    processing_profile_fingerprint TEXT NOT NULL
        CHECK (processing_profile_fingerprint ~ '^[0-9a-f]{64}$'),
    schema_version TEXT NOT NULL,
    artifact_relpath TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (
        project_id, source_document_revision_id, processing_profile_fingerprint
    )
);
