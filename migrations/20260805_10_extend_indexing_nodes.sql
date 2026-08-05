ALTER TABLE indexing_nodes
    ADD COLUMN IF NOT EXISTS source_chunk_bundle_id TEXT,
    ADD COLUMN IF NOT EXISTS chunking_bundle_fingerprint TEXT,
    ADD COLUMN IF NOT EXISTS corpus_version TEXT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'indexing_nodes_source_chunk_bundle_fk'
    ) THEN
        ALTER TABLE indexing_nodes
            ADD CONSTRAINT indexing_nodes_source_chunk_bundle_fk
            FOREIGN KEY (source_chunk_bundle_id)
            REFERENCES chunk_bundles(chunk_bundle_id)
            NOT VALID;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'indexing_nodes_parent_self_fk'
    ) THEN
        ALTER TABLE indexing_nodes
            ADD CONSTRAINT indexing_nodes_parent_self_fk
            FOREIGN KEY (parent_node_id)
            REFERENCES indexing_nodes(node_id)
            DEFERRABLE INITIALLY DEFERRED
            NOT VALID;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_indexing_nodes_source_chunk_bundle
    ON indexing_nodes (source_chunk_bundle_id);

CREATE INDEX IF NOT EXISTS idx_indexing_nodes_corpus
    ON indexing_nodes (corpus_version);

