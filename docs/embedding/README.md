# Embedding

## 1. Purpose and scope

Embedding turns one registered chunk bundle into a sealed, auditable embedding bundle. It owns engine compatibility, vector artifacts, validation, and readiness for indexing; it neither indexes vectors nor falls back to another vector space.

## 2. Current branch state

This reflects committed `main` at `f918b512a5320b6fc434feefe1e3e9f780bc097b`. No embedding README existed in that commit. Migrations `20260805_01` through `20260806_01` define the durable contract.

> Baseline de plataforma RAG: ver `docs/rag-platform/migration-baseline.md` (autoridad del baseline reproducible; este hash histórico se conserva por precisión).

## 3. Code map

- Domain models/errors: `app/back/src/embedding/domain/`.
- Runs, bundles, verification, ports: `app/back/src/embedding/application/`.
- API: `app/back/src/embedding/api/` under `/api/embedding`.
- Filesystem, in-memory, PostgreSQL adapters: `app/back/src/embedding/infrastructure/`.
- CLI and tests: `scripts/embedding/verify_profile.py`, `app/back/tests/embedding/`.

## 4. Inputs and outputs

Input: registered `ChunkBundleRef`, durable `EmbeddingProfile`, and `Idempotency-Key` for `POST /api/embedding/runs`. Output: `EmbeddingRun`, sealed `EmbeddingBundle`, child-vector map, validation/readiness checks, plus `manifest.json`, `vectors.npy`, and `chunk_map.jsonl`.

## 5. Operational flow

1. Explicitly verify the durable profile.
2. Create an idempotent run for exactly one chunk bundle/profile pair.
3. Read child chunks as `context_prefix\\ntext` and embed in batches.
4. Stage artifacts, validate source/profile/artifacts, persist the map/checks, and seal.
5. Hand only a ready sealed bundle to indexing.

## 6. Rules and invariants

- Profiles must be active, verified, and document-enabled; queries also require query enablement.
- Profile/provider/model/dimension/normalization/metric must agree. No provider fallback exists.
- Run, bundle, request, and readiness identifiers are deterministic for their identity inputs.
- A sealed bundle has passed validation and maps every source child to its vector.
- `cohere` is an explicit non-operational stub; `mock` requires explicit allowance.

## 7. Critical variables and configuration

- `SST_FEATURE_EMBEDDING_V2` gates run creation; `embedding_v2` is the internal
  resolved flag field, not the env var name.
- Durable profile fields force semantic settings; environment supplies credentials, batching, timeout, device, and cache.
- `VOYAGE_API_KEY` is required by Voyage. `UNKNOWN_REVISION` blocks proof unless allowed operator attestation proves it.
- `DEFAULT_EMBEDDING_BATCH_SIZE=32`; `DEFAULT_MAX_QUEUE_SIZE=32`.

## 8. Logs, manifests, and observability

Typed embedding events carry stable IDs such as run, document, profile, provider, capability, and configuration hash. Never log chunks, vectors, credentials, URLs, or provider payloads. The shared contract is [current-contracts.md](../observability/current-contracts.md).

## 9. Commands and verification

```powershell
npm run test:embedding
npm run embedding:verify-profile -- --profile-id <profile-id> --dry-run
npm run embedding:verify-profile -- --profile-id <profile-id> --apply
```

The verification command requires PostgreSQL configuration; `--apply` persists the verified profile and check, while dry run does not.

## 10. Visible inconsistencies and debt

- The committed tree had no README for this area.
- `cohere` is present in provider types but intentionally unavailable at runtime.
- No committed standalone CLI creates and executes embedding runs; the implemented entrypoint is the gated API.

## 11. Missing pieces to reach the target model

- No versioned runbook covers retry, cancellation, queue saturation, and artifact recovery.
- No CLI provides safe run creation/replay.
- The observability snapshot does not enumerate the embedding event family.

## 12. References

- `app/back/src/embedding/domain/models.py`
- `app/back/src/embedding/application/bundle_builder.py`
- `app/back/src/embedding/application/run_service.py`
- `app/back/src/embedding/application/profile_verification.py`
- `app/back/src/embedding/application/engine_registry.py`
- `app/back/tests/embedding/`
