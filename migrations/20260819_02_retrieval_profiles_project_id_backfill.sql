-- ADR-009: aislamiento por proyecto (tenant) en el runtime de retrieval.
-- Paso 1/2 (aditivo y seguro): añade `project_id` a `retrieval_profiles` como
-- NULLABLE y hace un backfill **determinista fail-closed** derivando el dueño de
-- los vectores del perfil. NO impone NOT NULL todavía (eso es 20260819_03, que se
-- aplica junto al código runtime que ya escribe `project_id`), así que aplicar
-- este paso no rompe la creación de perfiles.
--
-- Idempotente y reaplicable por `prepare_postgres_indexing.py`:
--   - ADD COLUMN IF NOT EXISTS;
--   - el backfill solo toca filas con project_id IS NULL.

ALTER TABLE retrieval_profiles ADD COLUMN IF NOT EXISTS project_id TEXT;

-- Backfill determinista + hard-gate (ADR-009 §3). El `vector_table` de cada perfil
-- se resuelve desde el catálogo de confianza `indexing_targets` (columna con CHECK
-- `^idx_vec_[a-z0-9_]+$`), así que `format('%I', ...)` es seguro. Se cuenta el
-- conjunto de `project_id` distintos en esa tabla física para la combinación
-- (embedding_profile_id, indexing_target_id, corpus_version) del perfil:
--   * exactamente 1 propietario -> backfill;
--   * 0 filas (perfil huérfano) -> ABORTA (decisión de operador);
--   * >1 propietarios (lane compartida) -> ABORTA: es la fuga que ADR-009 cierra,
--     nunca se adivina el proyecto.
DO $$
DECLARE
    rp        RECORD;
    v_table   TEXT;
    owners    TEXT[];
BEGIN
    FOR rp IN
        SELECT retrieval_profile_id,
               embedding_profile_id,
               indexing_target_id,
               corpus_version
          FROM retrieval_profiles
         WHERE project_id IS NULL
    LOOP
        SELECT vector_table
          INTO v_table
          FROM indexing_targets
         WHERE indexing_target_id = rp.indexing_target_id;

        IF v_table IS NULL THEN
            RAISE EXCEPTION
                'retrieval_profile % referencia un indexing_target inexistente (%)',
                rp.retrieval_profile_id, rp.indexing_target_id;
        END IF;

        EXECUTE format(
            'SELECT array_agg(DISTINCT project_id) FROM %I'
            ' WHERE embedding_profile_id = $1'
            '   AND indexing_target_id = $2'
            '   AND corpus_version = $3',
            v_table
        )
        INTO owners
        USING rp.embedding_profile_id, rp.indexing_target_id, rp.corpus_version;

        IF owners IS NULL OR array_length(owners, 1) IS NULL THEN
            RAISE EXCEPTION
                'retrieval_profile % no tiene vectores para derivar dueño de '
                'proyecto (huérfano); resolver por decisión de operador (ADR-009)',
                rp.retrieval_profile_id;
        ELSIF array_length(owners, 1) <> 1 THEN
            RAISE EXCEPTION
                'retrieval_profile % mapea a % proyectos distintos (%): lane '
                'compartida, resolver fail-closed (ADR-009 §3), no se adivina',
                rp.retrieval_profile_id, array_length(owners, 1), owners;
        END IF;

        UPDATE retrieval_profiles
           SET project_id = owners[1]
         WHERE retrieval_profile_id = rp.retrieval_profile_id;
    END LOOP;
END
$$;
