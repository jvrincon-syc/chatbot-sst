-- RAG platform corpus snapshots (Fase 2). Additive over legacy. A snapshot is an
-- ordered, immutable list of document revisions with a deterministic manifest
-- hash reconstructible from its rows alone (ADR-006 §2.4). Every statement is
-- CREATE ... IF NOT EXISTS, ordered after 20260810_02.

CREATE TABLE IF NOT EXISTS corpus_snapshots (
    corpus_snapshot_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES rag_projects(project_id),
    manifest_hash TEXT NOT NULL CHECK (manifest_hash ~ '^[0-9a-f]{64}$'),
    document_count INTEGER NOT NULL CHECK (document_count >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Same ordered selection + eligibility decisions => same manifest => one
    -- snapshot. A material change of selection yields a different hash.
    UNIQUE (project_id, manifest_hash)
);

CREATE TABLE IF NOT EXISTS corpus_snapshot_documents (
    corpus_snapshot_id TEXT NOT NULL
        REFERENCES corpus_snapshots(corpus_snapshot_id),
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
    source_document_revision_id TEXT NOT NULL
        REFERENCES source_document_revisions(source_document_revision_id),
    eligibility_decision TEXT NOT NULL CHECK (
        eligibility_decision IN (
            'not_required', 'approved_after_review', 'operator_waiver', 'blocked'
        )
    ),
    PRIMARY KEY (corpus_snapshot_id, ordinal),
    UNIQUE (corpus_snapshot_id, source_document_revision_id)
);

CREATE INDEX IF NOT EXISTS idx_corpus_snapshot_documents_revision
    ON corpus_snapshot_documents (source_document_revision_id);
