DO $$
DECLARE
    table_name TEXT;
    pkey_name TEXT;
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
        EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS embedding_bundle_id TEXT', table_name);
        EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS embedding_profile_id TEXT', table_name);
        EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS indexing_target_id TEXT', table_name);
        EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS corpus_version TEXT', table_name);
        EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS configuration_fingerprint TEXT', table_name);
        EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS vector_checksum TEXT', table_name);
        EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT false', table_name);
        EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS superseded_at TIMESTAMPTZ', table_name);

        SELECT conname
          INTO pkey_name
          FROM pg_constraint
         WHERE conrelid = table_name::regclass
           AND contype = 'p';

        IF pkey_name IS NOT NULL THEN
            EXECUTE format(
                'ALTER TABLE %I DROP CONSTRAINT %I',
                table_name,
                pkey_name
            );
        END IF;

        EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_embedding_bundle ON %I (embedding_bundle_id)', table_name, table_name);
        EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_document_active ON %I (document_id, is_active)', table_name, table_name);
        EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_profile_corpus_active ON %I (embedding_profile_id, corpus_version, is_active)', table_name, table_name);
        EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_target_corpus_active ON %I (indexing_target_id, corpus_version, is_active)', table_name, table_name);
        EXECUTE format('CREATE UNIQUE INDEX IF NOT EXISTS idx_%s_bundle_node_unique ON %I (embedding_bundle_id, node_id)', table_name, table_name);
        EXECUTE format('CREATE UNIQUE INDEX IF NOT EXISTS idx_%s_legacy_node_unique ON %I (node_id) WHERE embedding_bundle_id IS NULL', table_name, table_name);
    END LOOP;
END $$;

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
        constraint_name := table_name || '_embedding_bundle_fk';
        IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = constraint_name) THEN
            EXECUTE format(
                'ALTER TABLE %I ADD CONSTRAINT %I FOREIGN KEY (embedding_bundle_id) REFERENCES embedding_bundles(embedding_bundle_id) NOT VALID',
                table_name,
                constraint_name
            );
        END IF;

        constraint_name := table_name || '_embedding_profile_fk';
        IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = constraint_name) THEN
            EXECUTE format(
                'ALTER TABLE %I ADD CONSTRAINT %I FOREIGN KEY (embedding_profile_id) REFERENCES indexing_profiles(profile_id) NOT VALID',
                table_name,
                constraint_name
            );
        END IF;

        constraint_name := table_name || '_target_fk';
        IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = constraint_name) THEN
            EXECUTE format(
                'ALTER TABLE %I ADD CONSTRAINT %I FOREIGN KEY (indexing_target_id) REFERENCES indexing_targets(indexing_target_id) NOT VALID',
                table_name,
                constraint_name
            );
        END IF;
    END LOOP;
END $$;
