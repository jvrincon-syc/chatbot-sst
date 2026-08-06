-- Add the dedicated `embedding_profile_verification` readiness check kind.
--
-- `20260805_12` restricted `readiness_checks.check_kind` to three values, none of
-- which describes the explicit verification of a durable embedding profile. The
-- backend was therefore recording profile verifications as `indexing_readiness`
-- with `report_json->>'subject_kind' = 'embedding_profile'`, which overloads a
-- kind that must keep meaning "an embedding bundle is ready for one target".
--
-- This migration only widens the catalogue and reclassifies the rows this
-- implementation created. It touches no other table and no other row.
--
-- Logical rollback (no data loss, run inside one transaction):
--
--   UPDATE readiness_checks
--      SET check_kind = 'indexing_readiness'
--    WHERE check_kind = 'embedding_profile_verification';
--
--   ALTER TABLE readiness_checks DROP CONSTRAINT readiness_checks_check_kind_check;
--   ALTER TABLE readiness_checks
--       ADD CONSTRAINT readiness_checks_check_kind_check
--       CHECK (check_kind IN ('embedding_bundle_validation', 'indexing_readiness', 'retrieval_readiness'));
--
-- The reclassified rows keep `report_json->>'subject_kind' = 'embedding_profile'`,
-- so the rollback restores exactly the previous representation.

ALTER TABLE readiness_checks
    DROP CONSTRAINT IF EXISTS readiness_checks_check_kind_check;

ALTER TABLE readiness_checks
    ADD CONSTRAINT readiness_checks_check_kind_check
    CHECK (
        check_kind IN (
            'embedding_bundle_validation',
            'embedding_profile_verification',
            'indexing_readiness',
            'retrieval_readiness'
        )
    );

-- Reclassify only the profile verifications written by this implementation.
-- Real indexing readiness checks never carry `subject_kind`, so they are left
-- untouched.
UPDATE readiness_checks
   SET check_kind = 'embedding_profile_verification'
 WHERE check_kind = 'indexing_readiness'
   AND report_json ->> 'subject_kind' = 'embedding_profile';
