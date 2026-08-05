ALTER TABLE indexing_profiles
    ADD COLUMN IF NOT EXISTS model_revision TEXT NOT NULL DEFAULT 'unknown_revision',
    ADD COLUMN IF NOT EXISTS normalization TEXT NOT NULL DEFAULT 'unknown_normalization',
    ADD COLUMN IF NOT EXISTS semantic_config_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS configuration_fingerprint TEXT,
    ADD COLUMN IF NOT EXISTS document_enabled BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS query_enabled BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS default_indexing_target_id TEXT,
    ADD COLUMN IF NOT EXISTS deprecated_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS compatibility_status TEXT NOT NULL DEFAULT 'compatibility_not_proven';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conname = 'indexing_profiles_model_revision_not_blank'
    ) THEN
        ALTER TABLE indexing_profiles
            ADD CONSTRAINT indexing_profiles_model_revision_not_blank
            CHECK (length(trim(model_revision)) > 0);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conname = 'indexing_profiles_normalization_valid'
    ) THEN
        ALTER TABLE indexing_profiles
            ADD CONSTRAINT indexing_profiles_normalization_valid
            CHECK (
                normalization IN (
                    'unknown_normalization',
                    'none',
                    'l2',
                    'provider_normalized'
                )
            );
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conname = 'indexing_profiles_configuration_fingerprint_format'
    ) THEN
        ALTER TABLE indexing_profiles
            ADD CONSTRAINT indexing_profiles_configuration_fingerprint_format
            CHECK (
                configuration_fingerprint IS NULL
                OR configuration_fingerprint ~ '^[0-9a-f]{64}$'
            );
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conname = 'indexing_profiles_compatibility_status_valid'
    ) THEN
        ALTER TABLE indexing_profiles
            ADD CONSTRAINT indexing_profiles_compatibility_status_valid
            CHECK (
                compatibility_status IN (
                    'verified',
                    'legacy_unverified',
                    'compatibility_not_proven'
                )
            );
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conname = 'indexing_profiles_enablement_requires_verified_compatibility'
    ) THEN
        ALTER TABLE indexing_profiles
            ADD CONSTRAINT indexing_profiles_enablement_requires_verified_compatibility
            CHECK (
                (document_enabled = false AND query_enabled = false)
                OR compatibility_status = 'verified'
            );
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_indexing_profiles_configuration_fingerprint
    ON indexing_profiles (configuration_fingerprint);

CREATE INDEX IF NOT EXISTS idx_indexing_profiles_default_target
    ON indexing_profiles (default_indexing_target_id);

