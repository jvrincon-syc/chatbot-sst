-- Fix the two seed placeholders that block explicit verification of the local
-- BGE-M3 profile, without ever promoting it.
--
-- Background: 20260722 seeded `local-bge-m3-v1` with `normalization` and
-- `model_revision` placeholders, and 20260805_14 forced every unverified
-- profile to `compatibility_not_proven` with both enablement flags false.
-- The explicit verification use case (scripts/embedding/verify_profile.py) then
-- fails two checks because the stored semantic fields do not match what a live
-- BGE runtime actually reports:
--   * normalization: stored `unknown_normalization` vs engine-applied `l2`
--   * model_revision: stored `unknown_revision` (proves nothing)
--
-- Both target values are runtime observations, not arbitrary choices:
--   * `l2` is the normalization the BGE engine applies to its dense vectors
--     (embedding.application.engine_registry._PROVIDER_NORMALIZATION["bge"]).
--   * `5617a9f61b028005a4858fdac845db406aefb181` is the Hugging Face snapshot
--     commit of `BAAI/bge-m3` resolved from the local cache via AutoConfig,
--     i.e. exactly what `_bge_revision` observes for this profile.
--
-- This migration only corrects the semantic descriptors of the row. It does NOT
-- set `compatibility_status = 'verified'` and does NOT flip `document_enabled`
-- or `query_enabled`: promotion stays exclusive to the verification use case,
-- which re-observes the live engine, records a readiness_checks row and seals
-- the configuration fingerprint. The row therefore remains blocked until an
-- operator runs `npm run embedding:verify-profile -- --profile-id
-- local-bge-m3-v1 --apply`.
--
-- Idempotent and guarded: only touches the row while it still holds the
-- placeholders and is still unverified, so re-running it or running it after a
-- later revision change is a no-op.

UPDATE indexing_profiles
   SET normalization = 'l2',
       model_revision = '5617a9f61b028005a4858fdac845db406aefb181'
 WHERE profile_id = 'local-bge-m3-v1'
   AND embedding_provider = 'bge'
   AND embedding_model = 'BAAI/bge-m3'
   AND compatibility_status <> 'verified'
   AND normalization = 'unknown_normalization'
   AND model_revision = 'unknown_revision';
