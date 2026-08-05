INSERT INTO indexing_targets (
    indexing_target_id,
    postgres_schema,
    vector_table,
    distance_ops,
    storage_schema_version,
    active
)
SELECT
    'target-' || replace(profile.vector_table, '_', '-') AS indexing_target_id,
    'public',
    profile.vector_table,
    CASE profile.distance_metric
        WHEN 'cosine' THEN 'vector_cosine_ops'
        WHEN 'l2' THEN 'vector_l2_ops'
        WHEN 'inner_product' THEN 'vector_ip_ops'
    END AS distance_ops,
    'idx-vec-v1',
    profile.active
FROM indexing_profiles AS profile
WHERE profile.vector_table IS NOT NULL
ON CONFLICT (postgres_schema, vector_table) DO UPDATE SET
    distance_ops = EXCLUDED.distance_ops,
    storage_schema_version = EXCLUDED.storage_schema_version,
    active = EXCLUDED.active;

UPDATE indexing_profiles AS profile
   SET default_indexing_target_id = target.indexing_target_id
  FROM indexing_targets AS target
 WHERE target.postgres_schema = 'public'
   AND target.vector_table = profile.vector_table
   AND profile.default_indexing_target_id IS NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conname = 'indexing_profiles_default_target_fk'
    ) THEN
        ALTER TABLE indexing_profiles
            ADD CONSTRAINT indexing_profiles_default_target_fk
            FOREIGN KEY (default_indexing_target_id)
            REFERENCES indexing_targets(indexing_target_id);
    END IF;
END $$;

