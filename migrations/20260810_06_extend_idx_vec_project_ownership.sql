-- Fase 4 (ADR-007): propiedad de proyecto en las tablas vectoriales idx_vec_*.
-- Aditivo sobre 20260810_05: añade project_id nullable y dos FKs compuestos por
-- tabla (a embedding_bundles y a indexing_nodes, ambos scoped por project_id) y
-- mantiene UNIQUE(embedding_bundle_id, node_id). rag_release_id NO vive en la fila
-- vectorial (la release referencia la materialización, no un estado activo global).
-- Idempotente (ADD COLUMN IF NOT EXISTS / constraint guardado por pg_constraint).
-- Con project_id NULL (legacy) los FKs compuestos MATCH SIMPLE no se aplican: las
-- 18 filas vivas de idx_vec_local_bge_m3_v1 bypassean y solo plataforma queda blindada.

DO $$
DECLARE
    table_name TEXT;
    constraint_name TEXT;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
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
            'ALTER TABLE %I ADD COLUMN IF NOT EXISTS project_id TEXT',
            table_name
        );

        EXECUTE format(
            'CREATE INDEX IF NOT EXISTS idx_%s_project ON %I (project_id)',
            table_name, table_name
        );

        -- UNIQUE(embedding_bundle_id, node_id) ya existe (20260805_11); no se toca.

        -- FK compuesto a embedding_bundles(project_id, embedding_bundle_id).
        constraint_name := table_name || '_project_embedding_bundle_fk';
        IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = constraint_name) THEN
            EXECUTE format(
                'ALTER TABLE %I ADD CONSTRAINT %I FOREIGN KEY (project_id, embedding_bundle_id) '
                'REFERENCES embedding_bundles (project_id, embedding_bundle_id) NOT VALID',
                table_name, constraint_name
            );
        END IF;

        -- FK compuesto a indexing_nodes(project_id, node_id).
        constraint_name := table_name || '_project_node_fk';
        IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = constraint_name) THEN
            EXECUTE format(
                'ALTER TABLE %I ADD CONSTRAINT %I FOREIGN KEY (project_id, node_id) '
                'REFERENCES indexing_nodes (project_id, node_id) NOT VALID',
                table_name, constraint_name
            );
        END IF;
    END LOOP;
END $$;
