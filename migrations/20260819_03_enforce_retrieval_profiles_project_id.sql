-- ADR-009: aislamiento por proyecto (tenant) en el runtime de retrieval.
-- Paso 2/2 (enforcement): `retrieval_profiles.project_id` NOT NULL + FK a
-- `rag_projects`. Se aplica **junto al código runtime** que ya escribe
-- `project_id` al crear perfiles y lo exige en toda consulta de retrieval/
-- activación (fail-closed). Aplicar esto antes de ese código rompería la creación
-- de perfiles (NOT NULL violation), por eso va en una migración separada.
--
-- Precondición: 20260819_02 ya backfilleó las filas existentes (determinista).
-- Idempotente: SET NOT NULL es no-op si ya lo está; la FK se guarda por catálogo.

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
          FROM retrieval_profiles
         WHERE project_id IS NULL
    ) THEN
        RAISE EXCEPTION
            'retrieval_profiles tiene filas con project_id NULL; correr primero '
            '20260819_02 (backfill determinista) o resolver los huérfanos';
    END IF;
END
$$;

ALTER TABLE retrieval_profiles ALTER COLUMN project_id SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conname = 'retrieval_profiles_project_id_fkey'
    ) THEN
        ALTER TABLE retrieval_profiles
            ADD CONSTRAINT retrieval_profiles_project_id_fkey
            FOREIGN KEY (project_id) REFERENCES rag_projects(project_id);
    END IF;
END
$$;

-- Índice de apoyo para la frontera de tenant en lecturas de perfiles por proyecto.
CREATE INDEX IF NOT EXISTS idx_retrieval_profiles_project
    ON retrieval_profiles (project_id);
