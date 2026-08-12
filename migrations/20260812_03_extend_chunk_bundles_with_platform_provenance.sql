-- Task 6: provenance de variante auditable en chunk_bundles (ADR-006/ADR-008).
-- rag_variant_id y semantic_recipe_fingerprint son PROVENANCE nullable: registran
-- en qué contexto de variante nació el chunk, NO son identidad física ni dueño del
-- artefacto (esa es project_id + fingerprint, ya existente). Aditivo e idempotente.

ALTER TABLE chunk_bundles
    ADD COLUMN IF NOT EXISTS rag_variant_id TEXT;

ALTER TABLE chunk_bundles
    ADD COLUMN IF NOT EXISTS semantic_recipe_fingerprint TEXT;

-- El fingerprint, si viaja, es un SHA-256 (64 hex). La variante y su receta son un
-- par atómico: o ambos presentes o ambos ausentes (espeja el catálogo normalized).
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chunk_bundles_semantic_recipe_hex'
    ) THEN
        ALTER TABLE chunk_bundles
            ADD CONSTRAINT chunk_bundles_semantic_recipe_hex
            CHECK (
                semantic_recipe_fingerprint IS NULL
                OR semantic_recipe_fingerprint ~ '^[0-9a-f]{64}$'
            );
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chunk_bundles_variant_provenance_atomic'
    ) THEN
        ALTER TABLE chunk_bundles
            ADD CONSTRAINT chunk_bundles_variant_provenance_atomic
            CHECK (
                (rag_variant_id IS NULL AND semantic_recipe_fingerprint IS NULL)
                OR (rag_variant_id IS NOT NULL AND semantic_recipe_fingerprint IS NOT NULL)
            );
    END IF;
END $$;
