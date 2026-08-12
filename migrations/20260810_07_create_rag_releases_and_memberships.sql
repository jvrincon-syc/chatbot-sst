-- Fase 5 (plan §Fase 5): releases, membresías y lifecycle.
-- Aditiva sobre el catálogo de plataforma. `rag_variants` ya existe (20260810_01);
-- aquí solo se crean `rag_releases` y `rag_release_memberships`, y se cierra la FK
-- que 20260810_04 dejó pendiente en `rag_build_runs.rag_release_id`.
-- Idempotente (IF NOT EXISTS / constraint guardado por pg_constraint), ordenada
-- tras 20260810_06.

-- ---------------------------------------------------------------------------
-- Unicidades compuestas (project_id, id) en variante y snapshot: son el destino
-- de los FKs compuestos de rag_releases. Sin ellas, la BD aceptaría una release
-- que combine una variante de un proyecto con un snapshot de otro (project_id solo
-- no basta; mismo criterio de aislamiento que Fase 4). Redundantes con la PK pero
-- necesarias como destino de FK; idempotentes.
-- ---------------------------------------------------------------------------
CREATE UNIQUE INDEX IF NOT EXISTS uq_rag_variants_project_variant
    ON rag_variants (project_id, rag_variant_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_corpus_snapshots_project_snapshot
    ON corpus_snapshots (project_id, corpus_snapshot_id);

-- ---------------------------------------------------------------------------
-- rag_releases: una release inmutable de una variante sobre un corpus snapshot.
-- release_number es único DENTRO de la variante (nunca global del proyecto): lo
-- impone el índice único de abajo. release_manifest_hash es NULL en DRAFT y se
-- congela al validar. FKs compuestas por (project_id, id) para que variante y
-- snapshot pertenezcan al MISMO proyecto que la release (aislamiento en la BD, no
-- solo en Python).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS rag_releases (
    rag_release_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES rag_projects(project_id),
    rag_variant_id TEXT NOT NULL,
    corpus_snapshot_id TEXT NOT NULL,
    target_binding_key TEXT NOT NULL,
    release_number INTEGER NOT NULL CHECK (release_number >= 1),
    state TEXT NOT NULL DEFAULT 'draft'
        CHECK (state IN ('draft', 'validated', 'published', 'retired', 'failed')),
    release_manifest_hash TEXT
        CHECK (release_manifest_hash IS NULL OR release_manifest_hash ~ '^[0-9a-f]{64}$'),
    created_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    validated_at TIMESTAMPTZ,
    reason TEXT,
    -- Unicidad compuesta (destino de FK desde memberships): la release pertenece a
    -- su proyecto.
    UNIQUE (project_id, rag_release_id),
    -- Aislamiento cross-proyecto impuesto por la BD: variante y snapshot del mismo
    -- proyecto que la release.
    FOREIGN KEY (project_id, rag_variant_id)
        REFERENCES rag_variants (project_id, rag_variant_id),
    FOREIGN KEY (project_id, corpus_snapshot_id)
        REFERENCES corpus_snapshots (project_id, corpus_snapshot_id)
);

-- release_number único por variante (no global). Índice único NO parcial: aplica a
-- toda release de la variante.
CREATE UNIQUE INDEX IF NOT EXISTS uq_rag_releases_variant_number
    ON rag_releases (rag_variant_id, release_number);

CREATE INDEX IF NOT EXISTS idx_rag_releases_project
    ON rag_releases (project_id);
CREATE INDEX IF NOT EXISTS idx_rag_releases_variant
    ON rag_releases (rag_variant_id);

-- ---------------------------------------------------------------------------
-- rag_release_memberships: revisión ↔ artefactos concretos de una release. La
-- release nunca es válida si falta una revisión. FK compuesto a rag_releases por
-- (project_id, rag_release_id) para blindar la pertenencia al proyecto.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS rag_release_memberships (
    rag_release_id TEXT NOT NULL REFERENCES rag_releases(rag_release_id),
    project_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
    source_document_revision_id TEXT NOT NULL,
    normalized_document_id TEXT NOT NULL,
    chunk_bundle_id TEXT NOT NULL,
    embedding_bundle_id TEXT NOT NULL,
    materialization_id TEXT NOT NULL,
    PRIMARY KEY (rag_release_id, ordinal),
    UNIQUE (rag_release_id, source_document_revision_id)
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'rag_release_memberships_project_release_fk'
    ) THEN
        ALTER TABLE rag_release_memberships
            ADD CONSTRAINT rag_release_memberships_project_release_fk
            FOREIGN KEY (project_id, rag_release_id)
            REFERENCES rag_releases (project_id, rag_release_id);
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_rag_release_memberships_release
    ON rag_release_memberships (rag_release_id);

-- ---------------------------------------------------------------------------
-- Cierre de la FK pendiente de 20260810_04: rag_build_runs.rag_release_id ahora
-- referencia rag_releases. NOT VALID: no revalida filas de build previas (el
-- comentario de 04 dejó esta FK explícitamente para Fase 5).
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'rag_build_runs_release_fk'
    ) THEN
        ALTER TABLE rag_build_runs
            ADD CONSTRAINT rag_build_runs_release_fk
            FOREIGN KEY (rag_release_id)
            REFERENCES rag_releases (rag_release_id)
            NOT VALID;
    END IF;
END
$$;
