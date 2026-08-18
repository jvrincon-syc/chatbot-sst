-- Task 4: pinnea configuration_version en rag_releases.
--
-- Hoy rag_releases no persiste QUÉ versión de configuración usó cada release, así
-- que el target se re-resolvía contra la configuración vigente (drift). Esta
-- migración añade configuration_version y las restricciones de integridad contra
-- el binding VERSIONADO ((project_id, configuration_version, target_binding_key)
-- -> project_indexing_target_bindings), dependiente de 20260818_01.
--
-- SIN BACKFILL FABRICADO: el sistema viejo nunca guardó la versión histórica de
-- cada release; max(version) inventaría procedencia y apuntaría a la última
-- versión — justo el drift que este pin evita. Gate 0 decide el destino de filas
-- históricas (reset/rebuild dev ADR-007 o migración con evidencia). rag_releases
-- está VACÍA tras el reset, así que no hay filas que rellenar.
--
-- FAIL-CLOSED e IDEMPOTENTE: cada paso se guarda con information_schema/pg_constraint
-- para sobrevivir al re-apply-all de prepare_postgres_indexing.py. Las restricciones
-- se crean NOT VALID: toleran filas históricas pero se imponen a toda escritura nueva;
-- 20260818_03 las VALIDA y fija NOT NULL una vez resueltas las filas históricas.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'rag_releases'
          AND column_name = 'configuration_version'
    ) THEN
        ALTER TABLE rag_releases
            ADD COLUMN configuration_version INTEGER;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'rag_releases_versioned_binding_fkey'
    ) THEN
        ALTER TABLE rag_releases
            ADD CONSTRAINT rag_releases_versioned_binding_fkey
            FOREIGN KEY (project_id, configuration_version, target_binding_key)
            REFERENCES project_indexing_target_bindings
                (project_id, configuration_version, binding_key)
            NOT VALID;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'rag_releases_configuration_version_required'
    ) THEN
        ALTER TABLE rag_releases
            ADD CONSTRAINT rag_releases_configuration_version_required
            CHECK (configuration_version IS NOT NULL)
            NOT VALID;
    END IF;
END
$$;
