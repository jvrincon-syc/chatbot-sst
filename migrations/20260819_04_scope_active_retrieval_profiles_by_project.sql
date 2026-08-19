-- ADR-009: la unicidad del perfil activo de retrieval debe ser por proyecto.
-- El índice original quedó global por (consumer_scope_type, consumer_scope_id,
-- corpus_version), lo que contradice el runtime ya project-scoped. Esta migración
-- reconstruye la restricción parcial con `project_id` sin tocar filas.

DROP INDEX IF EXISTS idx_retrieval_profiles_one_active_scope_corpus;

CREATE UNIQUE INDEX IF NOT EXISTS idx_retrieval_profiles_one_active_scope_corpus
ON retrieval_profiles (project_id, consumer_scope_type, consumer_scope_id, corpus_version)
WHERE active = true;
