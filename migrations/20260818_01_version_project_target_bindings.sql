-- Task 3: versiona project_indexing_target_bindings con configuration_version.
--
-- Hoy la tabla es legacy: PK(project_id, binding_key), sin configuration_version,
-- de modo que un binding no puede leerse por la versión de configuración exacta que
-- usó una release. Esta migración añade configuration_version y reancla la PK a
-- (project_id, configuration_version, binding_key) con FK a project_configuration_versions.
--
-- FAIL-CLOSED e IDEMPOTENTE:
--  * Todo el cuerpo va en un bloque DO que hace no-op si la columna ya existe, para
--    sobrevivir al re-apply-all de scripts/indexing/prepare_postgres_indexing.py.
--  * Hard-gate: solo migra el caso DEMOSTRABLE de EXACTAMENTE 1 configuration_version
--    por proyecto (camino (a), determinista). Si algún proyecto con bindings tiene ≠1
--    versión, ABORTA sin tocar nada: la historia real de ese binding no es demostrable
--    desde el esquema y debe resolverse en Gate 0 (reset/rebuild dev o migración de
--    datos con evidencia). PROHIBIDO max(version) o copiar el binding a todas las versiones.
--  * Backfill determinista EN SITIO (UPDATE): en el caso 1-versión el mapeo binding→versión
--    es 1:1, así que no hace falta delete+reinsert (más simple y sin temp-table en plpgsql).

DO $$
BEGIN
    -- Ya migrado: no-op idempotente.
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'project_indexing_target_bindings'
          AND column_name = 'configuration_version'
    ) THEN
        RETURN;
    END IF;

    -- Hard-gate fail-closed: bloquea si algún proyecto con bindings tiene ≠1 versión.
    IF EXISTS (
        SELECT 1
        FROM project_indexing_target_bindings b
        JOIN (
            SELECT project_id
            FROM project_configuration_versions
            GROUP BY project_id
            HAVING count(*) <> 1
        ) multi ON multi.project_id = b.project_id
    ) THEN
        RAISE EXCEPTION
            'historical target binding mapping required before versioning';
    END IF;

    ALTER TABLE project_indexing_target_bindings
        ADD COLUMN configuration_version INTEGER;

    -- Backfill determinista en sitio: la única versión del proyecto (camino (a)).
    -- (`only` es palabra reservada en PostgreSQL; el alias es `single_version`.)
    UPDATE project_indexing_target_bindings b
    SET configuration_version = single_version.version
    FROM (
        SELECT project_id, min(version) AS version
        FROM project_configuration_versions
        GROUP BY project_id
        HAVING count(*) = 1
    ) single_version
    WHERE single_version.project_id = b.project_id;

    ALTER TABLE project_indexing_target_bindings
        DROP CONSTRAINT project_indexing_target_bindings_pkey;

    ALTER TABLE project_indexing_target_bindings
        ALTER COLUMN configuration_version SET NOT NULL;

    ALTER TABLE project_indexing_target_bindings
        ADD CONSTRAINT project_indexing_target_bindings_pkey
        PRIMARY KEY (project_id, configuration_version, binding_key);

    ALTER TABLE project_indexing_target_bindings
        ADD CONSTRAINT project_indexing_target_bindings_version_fkey
        FOREIGN KEY (project_id, configuration_version)
        REFERENCES project_configuration_versions (project_id, version);
END
$$;
