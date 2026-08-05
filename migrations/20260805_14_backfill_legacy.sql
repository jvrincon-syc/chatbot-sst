UPDATE indexing_profiles
   SET compatibility_status = 'compatibility_not_proven',
       document_enabled = false,
       query_enabled = false
 WHERE compatibility_status <> 'verified';

INSERT INTO chunk_bundles (
    chunk_bundle_id,
    bundle_fingerprint,
    profile_id,
    profile_fingerprint,
    corpus_version,
    source_document_id,
    artifact_relpath,
    parent_count,
    child_count,
    status
)
SELECT
    'legacy-' || document.artifact_fingerprint,
    document.artifact_fingerprint,
    COALESCE(document.metadata->>'chunking_profile_id', document.metadata->>'chunking_version', 'legacy_unknown_profile'),
    COALESCE(document.metadata->>'profile_fingerprint', 'compatibility_not_proven'),
    document.corpus_version,
    document.document_id,
    document.markdown_relpath,
    0,
    0,
    'legacy_unverified'
FROM indexing_normalized_documents AS document
WHERE document.artifact_fingerprint IS NOT NULL
ON CONFLICT (chunk_bundle_id) DO NOTHING;

INSERT INTO embedding_bundles (
    embedding_bundle_id,
    source_chunk_bundle_id,
    embedding_profile_id,
    provider,
    model,
    model_revision,
    dimension,
    normalization,
    distance_metric,
    configuration_fingerprint,
    corpus_version,
    semantic_config_json,
    bundle_schema_version,
    source_content_fingerprint,
    vector_count,
    checksums_json,
    status,
    validation_status,
    readiness_status
)
SELECT
    'legacy-embedding-' || profile.profile_id || '-' || document.document_id,
    'legacy-' || document.artifact_fingerprint,
    profile.profile_id,
    profile.embedding_provider,
    profile.embedding_model,
    'unknown_revision',
    profile.embedding_dimension,
    'unknown_normalization',
    profile.distance_metric,
    profile.config_hash,
    document.corpus_version,
    '{}'::jsonb,
    'legacy-embedding-bundle-v1',
    document.source_hash,
    0,
    '{}'::jsonb,
    'legacy_unverified',
    'compatibility_not_proven',
    'compatibility_not_proven'
FROM indexing_normalized_documents AS document
JOIN indexing_profiles AS profile
  ON profile.active = true
WHERE document.artifact_fingerprint IS NOT NULL
  AND profile.default_indexing_target_id IS NOT NULL
ON CONFLICT (embedding_bundle_id) DO NOTHING;

