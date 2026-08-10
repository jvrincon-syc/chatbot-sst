-- RAG platform catalog (Fase 1). Additive over the legacy bundle-first lane;
-- touches no legacy table. Every statement is CREATE ... IF NOT EXISTS and is
-- ordered after 20260806_01. Credentials never live here: profiles persist only
-- sanitized configuration plus a deterministic fingerprint.

-- Projects: ownership and storage boundary. project_id is a stable technical
-- slug, immutable once the project has documents (enforced in application).
CREATE TABLE IF NOT EXISTS rag_projects (
    project_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'active' CHECK (state IN ('active', 'archived')),
    storage_root_raw TEXT NOT NULL,
    storage_root_normalized TEXT NOT NULL,
    storage_root_chunks TEXT NOT NULL,
    storage_root_embeddings TEXT NOT NULL,
    storage_root_manifests TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Editable, versioned project configuration. Each edit is a new row.
CREATE TABLE IF NOT EXISTS project_configuration_versions (
    project_id TEXT NOT NULL REFERENCES rag_projects(project_id),
    version INTEGER NOT NULL CHECK (version >= 1),
    corpus_organization_policy TEXT NOT NULL CHECK (
        corpus_organization_policy IN (
            'sst-legacy-v1', 'source-folders-v1', 'document-types-v1', 'hybrid-v1'
        )
    ),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (project_id, version)
);

-- Document type catalog per project (from a selectable template).
CREATE TABLE IF NOT EXISTS project_document_types (
    project_id TEXT NOT NULL REFERENCES rag_projects(project_id),
    configuration_version INTEGER NOT NULL,
    code TEXT NOT NULL,
    display_name TEXT NOT NULL,
    template TEXT NOT NULL CHECK (template IN ('generic', 'sst')),
    PRIMARY KEY (project_id, configuration_version, code),
    FOREIGN KEY (project_id, configuration_version)
        REFERENCES project_configuration_versions(project_id, version)
);

-- Embedding profiles a project is allowed to use (global resources, ADR-005).
CREATE TABLE IF NOT EXISTS project_embedding_profiles (
    project_id TEXT NOT NULL REFERENCES rag_projects(project_id),
    configuration_version INTEGER NOT NULL,
    embedding_profile_id TEXT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (project_id, configuration_version, embedding_profile_id),
    FOREIGN KEY (project_id, configuration_version)
        REFERENCES project_configuration_versions(project_id, version)
);

-- Backend allowlist: logical binding key -> compatible global target.
-- The client never sends a raw indexing_target_id or vector table name.
CREATE TABLE IF NOT EXISTS project_indexing_target_bindings (
    project_id TEXT NOT NULL REFERENCES rag_projects(project_id),
    binding_key TEXT NOT NULL,
    indexing_target_id TEXT NOT NULL,
    embedding_profile_id TEXT NOT NULL,
    PRIMARY KEY (project_id, binding_key)
);

-- Processing recipe: provider/engine/observed revision + sanitized config and an
-- immutable fingerprint. No secrets are stored (see AGENTS §6, plan §4.3).
CREATE TABLE IF NOT EXISTS document_processing_profiles (
    processing_profile_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES rag_projects(project_id),
    provider TEXT NOT NULL,
    engine TEXT NOT NULL,
    observed_revision TEXT NOT NULL,
    origin TEXT NOT NULL CHECK (origin IN ('local', 'llama_cloud')),
    sanitized_config_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    fingerprint TEXT NOT NULL CHECK (fingerprint ~ '^[0-9a-f]{64}$'),
    status TEXT NOT NULL CHECK (status IN ('verified', 'unverifiable')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Chunking recipe with an immutable fingerprint.
CREATE TABLE IF NOT EXISTS chunking_profiles (
    chunking_profile_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES rag_projects(project_id),
    strategy TEXT NOT NULL,
    sanitized_config_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    fingerprint TEXT NOT NULL CHECK (fingerprint ~ '^[0-9a-f]{64}$'),
    status TEXT NOT NULL CHECK (status IN ('verified', 'unverifiable')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- RAG variant: an immutable semantic recipe within a project. The target is not
-- part of the recipe. UNIQUE(project_id, semantic_recipe_fingerprint) applies
-- while the variant is active (partial index below); plan §4.4.
CREATE TABLE IF NOT EXISTS rag_variants (
    rag_variant_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES rag_projects(project_id),
    processing_profile_id TEXT NOT NULL
        REFERENCES document_processing_profiles(processing_profile_id),
    chunking_profile_id TEXT NOT NULL
        REFERENCES chunking_profiles(chunking_profile_id),
    embedding_profile_id TEXT NOT NULL,
    semantic_recipe_fingerprint TEXT NOT NULL
        CHECK (semantic_recipe_fingerprint ~ '^[0-9a-f]{64}$'),
    state TEXT NOT NULL DEFAULT 'active' CHECK (state IN ('active', 'retired')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_rag_variants_active_recipe
    ON rag_variants (project_id, semantic_recipe_fingerprint)
    WHERE state = 'active';

CREATE INDEX IF NOT EXISTS idx_rag_variants_project
    ON rag_variants (project_id);
