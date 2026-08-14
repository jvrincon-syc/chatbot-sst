-- Refactor pure-platform (esta rama) retira project_id del codigo (modelos y SQL de
-- repos en embedding/indexing) y elimina las migraciones 20260810_04..08 que lo
-- habian creado y puesto NOT NULL. En una BD ya migrada con aquellas, la columna
-- project_id sobrevive como NOT NULL sin default; el INSERT refactorizado la omite,
-- viola la restriccion, envenena la conexion compartida y toda lectura posterior
-- cae con InFailedSqlTransaction (las 58 pruebas de indexing y los endpoints de
-- embedding/indexing/retrieval fallando a la vez).
--
-- Realineacion definitiva: se elimina la columna project_id de la cadena derivada.
-- DROP COLUMN arrastra en cascada el indice uq_chunk_bundles_project_fingerprint y
-- los FK compuestos (project_id, ...) que dejaron 20260810_05/06. Idempotente y
-- guardada por existencia de columna:
--   * BD ya migrada (columna presente): la dropea -> el codigo sin project_id inserta OK.
--   * BD fresca desde este set de migraciones (sin columna): no-op.
--   * Re-aplicacion: no-op.

DO $$
DECLARE
    target_table TEXT;
BEGIN
    FOREACH target_table IN ARRAY ARRAY[
        'chunk_bundles',
        'embedding_bundles',
        'embedding_runs',
        'indexing_nodes',
        'indexing_runs',
        'indexing_materializations',
        'idx_vec_llama_first_local_v1',
        'idx_vec_local_bge_m3_v1',
        'idx_vec_llama_bge_m3_v1',
        'idx_vec_local_voyage_4_v1',
        'idx_vec_llama_voyage_4_v1',
        'idx_vec_local_cohere_embed_v4_v1',
        'idx_vec_llama_cohere_embed_v4_v1'
    ]
    LOOP
        IF EXISTS (
            SELECT 1
              FROM information_schema.columns
             WHERE table_schema = 'public'
               AND table_name = target_table
               AND column_name = 'project_id'
        ) THEN
            EXECUTE format('ALTER TABLE %I DROP COLUMN project_id CASCADE', target_table);
        END IF;
    END LOOP;
END $$;
