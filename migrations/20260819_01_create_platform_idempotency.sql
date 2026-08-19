-- Fase 7 (plan §Idempotency): deduplicación durable de mutaciones de release.
-- PostgreSQL es la autoridad de idempotencia para build/validate/publish/retire.
-- Tabla independiente y aditiva: NO altera `rag_releases` ni ninguna tabla de
-- release (separación de responsabilidades; la idempotencia HTTP no es estado de
-- negocio de la release). Idempotente (IF NOT EXISTS), reaplicable por el
-- aplicador `prepare_postgres_indexing.py`.

-- ---------------------------------------------------------------------------
-- platform_idempotency_records: un registro por `Idempotency-Key` server-side.
-- `key_hash` es sha256 del header crudo (nunca se persiste el valor crudo). La
-- reserva atómica se apoya en la PK: `INSERT ... ON CONFLICT (key_hash) DO
-- NOTHING RETURNING` deja que exactamente un llamador concurrente inserte.
-- `request_fingerprint` fija la petición lógica (acción + recurso): la misma
-- clave con distinto fingerprint es conflicto. `result_json` solo guarda el
-- resultado terminal no sensible (ids/hashes/estado); jamás texto de documento,
-- vectores, secretos ni rutas absolutas.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS platform_idempotency_records (
    key_hash TEXT PRIMARY KEY
        CHECK (key_hash ~ '^[0-9a-f]{64}$'),
    action TEXT NOT NULL
        CHECK (action IN ('build', 'validate', 'publish', 'retire')),
    resource_id TEXT NOT NULL,
    request_fingerprint TEXT NOT NULL
        CHECK (request_fingerprint ~ '^[0-9a-f]{64}$'),
    actor_id TEXT NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('reserved', 'completed', 'failed')),
    response_status INTEGER,
    result_json JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ
);

-- Consulta operativa por recurso (auditoría/limpieza de reservas huérfanas).
CREATE INDEX IF NOT EXISTS idx_platform_idempotency_resource
    ON platform_idempotency_records (resource_id, action);
