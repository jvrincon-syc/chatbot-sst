-- Fase 4 (ADR-007): propiedad física por proyecto vía FKs compuestas + node_id
-- namespaced + runs release-aware + tabla de materializaciones. Aditivo sobre
-- legacy: solo añade columnas nullable, unicidades compuestas (destino de FK),
-- índices parciales y una tabla nueva. Cada sentencia es idempotente
-- (IF NOT EXISTS / guarded por pg_constraint), ordenada tras 20260810_04. No se
-- retira ninguna unicidad global ni se hace DROP CONSTRAINT; corpus_version se
-- mantiene NOT NULL (marcador legacy, fuera de la identidad física).

-- ---------------------------------------------------------------------------
-- chunk_bundles: unicidad compuesta (project_id, chunk_bundle_id) como destino
-- de los FKs compuestos. chunk_bundle_id ya es PK (único global); esta unicidad
-- redundante es la única forma de que Postgres acepte el FK compuesto.
-- ---------------------------------------------------------------------------
CREATE UNIQUE INDEX IF NOT EXISTS uq_chunk_bundles_project_bundle
    ON chunk_bundles (project_id, chunk_bundle_id);

-- ---------------------------------------------------------------------------
-- embedding_bundles: propiedad de proyecto + identidad física parcial + FK
-- compuesto a chunk_bundles.
-- ---------------------------------------------------------------------------
ALTER TABLE embedding_bundles ADD COLUMN IF NOT EXISTS project_id TEXT;

-- Unicidad compuesta (destino de FK desde idx_vec_* y indexing_materializations).
CREATE UNIQUE INDEX IF NOT EXISTS uq_embedding_bundles_project_bundle
    ON embedding_bundles (project_id, embedding_bundle_id);

-- Identidad física (§4) SOLO para filas de plataforma. Índice parcial: las filas
-- legacy (project_id IS NULL) quedan excluidas y nunca chocan. corpus_version NO
-- forma parte de la identidad (se mantiene NOT NULL como marcador legacy).
CREATE UNIQUE INDEX IF NOT EXISTS uq_embedding_bundles_physical_identity
    ON embedding_bundles (
        project_id,
        source_chunk_bundle_id,
        embedding_profile_id,
        configuration_fingerprint,
        source_content_fingerprint,
        bundle_schema_version
    )
    WHERE project_id IS NOT NULL;

-- FK compuesto: un embedding bundle de plataforma solo puede apuntar a un chunk
-- bundle del MISMO proyecto. MATCH SIMPLE => con project_id NULL (legacy) el FK
-- no se aplica y la fila bypassea por su FK legacy. NOT VALID: no revalida filas
-- legacy existentes.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'embedding_bundles_project_chunk_bundle_fk'
    ) THEN
        ALTER TABLE embedding_bundles
            ADD CONSTRAINT embedding_bundles_project_chunk_bundle_fk
            FOREIGN KEY (project_id, source_chunk_bundle_id)
            REFERENCES chunk_bundles (project_id, chunk_bundle_id)
            NOT VALID;
    END IF;
END
$$;

-- ---------------------------------------------------------------------------
-- indexing_nodes: node_id físico separado de source_chunk_id, y parent_node_id
-- físico separado de source_parent_chunk_id. Unicidad (project_id, node_id) +
-- FK compuesto a chunk_bundles.
-- ---------------------------------------------------------------------------
ALTER TABLE indexing_nodes ADD COLUMN IF NOT EXISTS project_id TEXT;
ALTER TABLE indexing_nodes ADD COLUMN IF NOT EXISTS source_chunk_id TEXT;
ALTER TABLE indexing_nodes ADD COLUMN IF NOT EXISTS source_parent_chunk_id TEXT;

-- Índice NO parcial: node_id ya es PK (único global), así que (project_id, node_id)
-- es trivialmente único incluso con project_id NULL. Debe ser no parcial para poder
-- ser destino de un FK compuesto desde idx_vec_* (Postgres no acepta índices
-- parciales como destino de FK).
CREATE UNIQUE INDEX IF NOT EXISTS uq_indexing_nodes_project_node
    ON indexing_nodes (project_id, node_id);

CREATE INDEX IF NOT EXISTS idx_indexing_nodes_project_bundle
    ON indexing_nodes (project_id, source_chunk_bundle_id);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'indexing_nodes_project_chunk_bundle_fk'
    ) THEN
        ALTER TABLE indexing_nodes
            ADD CONSTRAINT indexing_nodes_project_chunk_bundle_fk
            FOREIGN KEY (project_id, source_chunk_bundle_id)
            REFERENCES chunk_bundles (project_id, chunk_bundle_id)
            NOT VALID;
    END IF;
END
$$;

-- ---------------------------------------------------------------------------
-- embedding_runs / indexing_runs: contexto de release como columnas NULLABLE SIN
-- FK (la tabla rag_releases es de Fase 5). Derivadas por el servidor desde un
-- build context validado; nunca del payload del cliente.
-- ---------------------------------------------------------------------------
ALTER TABLE embedding_runs ADD COLUMN IF NOT EXISTS project_id TEXT;
ALTER TABLE embedding_runs ADD COLUMN IF NOT EXISTS rag_variant_id TEXT;
ALTER TABLE embedding_runs ADD COLUMN IF NOT EXISTS rag_release_id TEXT;

ALTER TABLE indexing_runs ADD COLUMN IF NOT EXISTS project_id TEXT;
ALTER TABLE indexing_runs ADD COLUMN IF NOT EXISTS rag_variant_id TEXT;
ALTER TABLE indexing_runs ADD COLUMN IF NOT EXISTS rag_release_id TEXT;

-- ---------------------------------------------------------------------------
-- indexing_materializations: lifecycle inmutable WRITING → SEALED | FAILED
-- (ADR-007 §3). Identidad (project_id, embedding_bundle_id, indexing_target_id,
-- storage_schema_version). FK compuesto a embedding_bundles + FK simple a
-- indexing_targets (target es global, sin project_id).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS indexing_materializations (
    materialization_id TEXT PRIMARY KEY,
    project_id TEXT,
    embedding_bundle_id TEXT NOT NULL,
    indexing_target_id TEXT NOT NULL REFERENCES indexing_targets(indexing_target_id),
    storage_schema_version TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('writing', 'sealed', 'failed')),
    canonical_checksum TEXT CHECK (
        canonical_checksum IS NULL OR canonical_checksum ~ '^[0-9a-f]{64}$'
    ),
    parent_node_count INTEGER NOT NULL DEFAULT 0 CHECK (parent_node_count >= 0),
    child_node_count INTEGER NOT NULL DEFAULT 0 CHECK (child_node_count >= 0),
    vector_count INTEGER NOT NULL DEFAULT 0 CHECK (vector_count >= 0),
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    sealed_at TIMESTAMPTZ,
    failed_at TIMESTAMPTZ,
    failure_code TEXT,
    UNIQUE (
        project_id, embedding_bundle_id, indexing_target_id, storage_schema_version
    )
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'indexing_materializations_project_bundle_fk'
    ) THEN
        ALTER TABLE indexing_materializations
            ADD CONSTRAINT indexing_materializations_project_bundle_fk
            FOREIGN KEY (project_id, embedding_bundle_id)
            REFERENCES embedding_bundles (project_id, embedding_bundle_id)
            NOT VALID;
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_indexing_materializations_project_bundle
    ON indexing_materializations (project_id, embedding_bundle_id);
