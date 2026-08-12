-- Fase 4 cierre (ADR-008): pure-platform sobre BD vacía. project_id pasa a NOT NULL
-- en toda la cadena derivada (raw→indexing), se retira la unicidad global de
-- chunk_bundles.bundle_fingerprint (dedup pasa a scoped por proyecto) y se validan
-- los FKs compuestos que 20260810_05/06 dejaron NOT VALID. Idempotente:
-- SET NOT NULL / DROP CONSTRAINT IF EXISTS / CREATE INDEX IF NOT EXISTS / VALIDATE
-- son no-op al re-aplicar. Supersede ADR-007 §1 (nullable), §2 (dual-mode) y §9/D1
-- (unicidad global). Requiere BD sin filas legacy (hard reset previo).

-- ---------------------------------------------------------------------------
-- 1) Purga defensiva FK-safe: elimina cualquier fila legacy (project_id IS NULL)
--    antes del tightening. En la BD vacía actual es no-op; neutraliza también las
--    filas que fabrica el backfill legacy 20260805_14 si corriera con normalized
--    docs presentes. Orden hijos→padres.
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    vec_table TEXT;
BEGIN
    FOREACH vec_table IN ARRAY ARRAY[
        'idx_vec_llama_first_local_v1',
        'idx_vec_local_bge_m3_v1',
        'idx_vec_llama_bge_m3_v1',
        'idx_vec_local_voyage_4_v1',
        'idx_vec_llama_voyage_4_v1',
        'idx_vec_local_cohere_embed_v4_v1',
        'idx_vec_llama_cohere_embed_v4_v1'
    ]
    LOOP
        EXECUTE format('DELETE FROM %I WHERE project_id IS NULL', vec_table);
    END LOOP;
END $$;

DELETE FROM indexing_materializations WHERE project_id IS NULL;
-- indexing_run_documents.run_id tiene ON DELETE CASCADE: borrar el run arrastra sus documentos.
DELETE FROM indexing_runs WHERE project_id IS NULL;
DELETE FROM indexing_nodes WHERE project_id IS NULL;
DELETE FROM embedding_bundle_chunks
 WHERE embedding_bundle_id IN (SELECT embedding_bundle_id FROM embedding_bundles WHERE project_id IS NULL);
DELETE FROM embedding_bundles WHERE project_id IS NULL;
DELETE FROM embedding_runs WHERE project_id IS NULL;
DELETE FROM chunk_bundles WHERE project_id IS NULL;

-- ---------------------------------------------------------------------------
-- 2) Retiro de la unicidad global (ADR-008 §2). La dedup pasa a scoped por
--    proyecto. bundle_fingerprint sigue NOT NULL, pero ya no es único global.
-- ---------------------------------------------------------------------------
ALTER TABLE chunk_bundles DROP CONSTRAINT IF EXISTS chunk_bundles_bundle_fingerprint_key;

CREATE UNIQUE INDEX IF NOT EXISTS uq_chunk_bundles_project_fingerprint
    ON chunk_bundles (project_id, bundle_fingerprint);

-- ---------------------------------------------------------------------------
-- 3) project_id NOT NULL en toda la cadena derivada (ADR-008 §1).
--    rag_variant_id/rag_release_id siguen nullable (release es Fase 5).
-- ---------------------------------------------------------------------------
ALTER TABLE chunk_bundles            ALTER COLUMN project_id SET NOT NULL;
ALTER TABLE embedding_bundles        ALTER COLUMN project_id SET NOT NULL;
ALTER TABLE indexing_nodes           ALTER COLUMN project_id SET NOT NULL;
ALTER TABLE embedding_runs           ALTER COLUMN project_id SET NOT NULL;
ALTER TABLE indexing_runs            ALTER COLUMN project_id SET NOT NULL;
ALTER TABLE indexing_materializations ALTER COLUMN project_id SET NOT NULL;

DO $$
DECLARE
    vec_table TEXT;
BEGIN
    FOREACH vec_table IN ARRAY ARRAY[
        'idx_vec_llama_first_local_v1',
        'idx_vec_local_bge_m3_v1',
        'idx_vec_llama_bge_m3_v1',
        'idx_vec_local_voyage_4_v1',
        'idx_vec_llama_voyage_4_v1',
        'idx_vec_local_cohere_embed_v4_v1',
        'idx_vec_llama_cohere_embed_v4_v1'
    ]
    LOOP
        EXECUTE format('ALTER TABLE %I ALTER COLUMN project_id SET NOT NULL', vec_table);
    END LOOP;
END $$;

-- ---------------------------------------------------------------------------
-- 4) Validar los FKs compuestos que 05/06 dejaron NOT VALID. Con project_id NOT
--    NULL todas las filas quedan bajo el FK (ya no hay bypass MATCH SIMPLE).
--    VALIDATE es no-op sobre tablas vacías / FKs ya validados.
-- ---------------------------------------------------------------------------
ALTER TABLE embedding_bundles
    VALIDATE CONSTRAINT embedding_bundles_project_chunk_bundle_fk;
ALTER TABLE indexing_nodes
    VALIDATE CONSTRAINT indexing_nodes_project_chunk_bundle_fk;
ALTER TABLE indexing_materializations
    VALIDATE CONSTRAINT indexing_materializations_project_bundle_fk;

DO $$
DECLARE
    vec_table TEXT;
BEGIN
    FOREACH vec_table IN ARRAY ARRAY[
        'idx_vec_llama_first_local_v1',
        'idx_vec_local_bge_m3_v1',
        'idx_vec_llama_bge_m3_v1',
        'idx_vec_local_voyage_4_v1',
        'idx_vec_llama_voyage_4_v1',
        'idx_vec_local_cohere_embed_v4_v1',
        'idx_vec_llama_cohere_embed_v4_v1'
    ]
    LOOP
        EXECUTE format(
            'ALTER TABLE %I VALIDATE CONSTRAINT %I',
            vec_table, vec_table || '_project_embedding_bundle_fk'
        );
        EXECUTE format(
            'ALTER TABLE %I VALIDATE CONSTRAINT %I',
            vec_table, vec_table || '_project_node_fk'
        );
    END LOOP;
END $$;
