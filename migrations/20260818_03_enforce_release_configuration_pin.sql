-- Task 4: impone el pin de configuration_version en rag_releases.
--
-- Corre SOLO después de que Gate 0 resolvió las filas históricas (aquí:
-- rag_releases VACÍA tras el reset ADR-007, así que VALIDATE es trivial). Valida
-- las restricciones creadas NOT VALID en 20260818_02 y fija la columna NOT NULL.
--
-- Si quedaran filas legacy con configuration_version no demostrable, estas
-- sentencias DEBEN fallar deliberadamente: PROHIBIDO fabricar un valor solo para
-- que la migración pase.
--
-- IDEMPOTENTE: guarda cada VALIDATE con la existencia de la constraint;
-- re-VALIDAR una constraint ya validada y re-fijar NOT NULL ya fijado son no-op.

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'rag_releases_configuration_version_required'
    ) THEN
        ALTER TABLE rag_releases
            VALIDATE CONSTRAINT rag_releases_configuration_version_required;
    END IF;

    IF EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'rag_releases_versioned_binding_fkey'
    ) THEN
        ALTER TABLE rag_releases
            VALIDATE CONSTRAINT rag_releases_versioned_binding_fkey;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'rag_releases'
          AND column_name = 'configuration_version'
          AND is_nullable = 'YES'
    ) THEN
        ALTER TABLE rag_releases
            ALTER COLUMN configuration_version SET NOT NULL;
    END IF;
END
$$;
