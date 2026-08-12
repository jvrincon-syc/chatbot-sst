-- Keep normalized physical catalog rows scoped to the same project as their
-- processing profile and optional RAG variant. The base migration already
-- indexes the child key prefixes; these parent UNIQUE constraints supply the
-- required composite FK targets without adding speculative indexes.

-- Guard por pg_class (nombre de relación) para no colisionar con un índice único
-- del mismo nombre ya creado por 20260810_07: un índice único es destino de FK
-- válido, así que si existe se reutiliza en vez de re-crear una constraint homónima.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_class
        WHERE relname = 'uq_document_processing_profiles_project_profile'
    ) THEN
        ALTER TABLE document_processing_profiles
            ADD CONSTRAINT uq_document_processing_profiles_project_profile
            UNIQUE (project_id, processing_profile_id);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_class
        WHERE relname = 'uq_rag_variants_project_variant'
    ) THEN
        ALTER TABLE rag_variants
            ADD CONSTRAINT uq_rag_variants_project_variant
            UNIQUE (project_id, rag_variant_id);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'project_normalized_artifacts_project_profile_fk'
    ) THEN
        ALTER TABLE project_normalized_document_artifacts
            ADD CONSTRAINT project_normalized_artifacts_project_profile_fk
            FOREIGN KEY (project_id, processing_profile_id)
            REFERENCES document_processing_profiles (project_id, processing_profile_id);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'project_normalized_artifacts_project_variant_fk'
    ) THEN
        ALTER TABLE project_normalized_document_artifacts
            ADD CONSTRAINT project_normalized_artifacts_project_variant_fk
            FOREIGN KEY (project_id, rag_variant_id)
            REFERENCES rag_variants (project_id, rag_variant_id);
    END IF;
END $$;
