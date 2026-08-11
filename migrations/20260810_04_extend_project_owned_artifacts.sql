-- RAG platform physical artifacts + chunking ledger (Fase 3). Additive over
-- legacy: only adds nullable columns, one partial unique index and two ledger
-- tables. Every statement is idempotent (IF NOT EXISTS / guarded), ordered after
-- 20260810_03. The legacy global uniqueness on bundle_fingerprint stays intact;
-- its retirement and the migration to physical identity belong to Fase 4.

-- Project ownership + sealing on chunk_bundles (nullable, so legacy rows are
-- untouched and validate unchanged). corpus_version remains a legacy column and
-- is NOT part of the new physical identity (§4.3/§4.4).
ALTER TABLE chunk_bundles ADD COLUMN IF NOT EXISTS project_id TEXT;
ALTER TABLE chunk_bundles ADD COLUMN IF NOT EXISTS normalized_document_id TEXT;
ALTER TABLE chunk_bundles
    ADD COLUMN IF NOT EXISTS chunking_profile_fingerprint TEXT;
ALTER TABLE chunk_bundles ADD COLUMN IF NOT EXISTS bundle_schema_version TEXT;
ALTER TABLE chunk_bundles ADD COLUMN IF NOT EXISTS sealing_status TEXT;

-- Optional CHECK on sealing_status. ADD CONSTRAINT has no IF NOT EXISTS, so guard
-- it to stay idempotent across re-runs.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chunk_bundles_sealing_status_check'
    ) THEN
        ALTER TABLE chunk_bundles
            ADD CONSTRAINT chunk_bundles_sealing_status_check
            CHECK (sealing_status IS NULL OR sealing_status IN ('staged', 'sealed'));
    END IF;
END
$$;

-- Legacy uniqueness chunk_bundles_bundle_fingerprint_key is intentionally kept
-- here; retiring it (so two projects with identical bytes get their own bundle)
-- is Fase 4.

-- Physical identity (§4.4) for platform-owned rows only. Partial index so legacy
-- rows (project_id IS NULL) are excluded and never conflict.
CREATE UNIQUE INDEX IF NOT EXISTS uq_chunk_bundles_physical_identity
    ON chunk_bundles (
        project_id,
        normalized_document_id,
        chunking_profile_fingerprint,
        bundle_schema_version
    )
    WHERE project_id IS NOT NULL;

-- Build ledger: durable audit of every stage and reuse. The run points at the
-- release; the physical bundle does not.
CREATE TABLE IF NOT EXISTS rag_build_runs (
    rag_build_run_id TEXT PRIMARY KEY,
    -- FK a rag_releases se añade en Fase 5 (la tabla no existe todavía).
    rag_release_id TEXT NOT NULL,
    project_id TEXT NOT NULL REFERENCES rag_projects(project_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS rag_build_steps (
    rag_build_step_id TEXT PRIMARY KEY,
    rag_build_run_id TEXT NOT NULL REFERENCES rag_build_runs(rag_build_run_id),
    stage TEXT NOT NULL CHECK (
        stage IN ('normalize', 'chunk', 'embed', 'index')
    ),
    outcome TEXT CHECK (
        outcome IS NULL OR outcome IN ('built', 'reused', 'failed')
    ),
    reuse_kind TEXT CHECK (
        reuse_kind IS NULL OR reuse_kind IN (
            'exact_identity', 'revalidated_compatibility', 'operator_approved'
        )
    ),
    source_artifact_id TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_rag_build_runs_release
    ON rag_build_runs (rag_release_id);

CREATE INDEX IF NOT EXISTS idx_rag_build_steps_run
    ON rag_build_steps (rag_build_run_id);
