# Indexing

## 1. Purpose and scope

Bundle-first indexing persists approved pre-computed embedding bundles as durable parent/child nodes and inactive pgvector rows, then activates or rolls back separately. It must not re-chunk or generate document embeddings.

## 2. Current branch state

This reflects committed `main` at `f918b512a5320b6fc434feefe1e3e9f780bc097b`. No indexing README existed in that commit. Migrations `20260805_01` through `20260805_15` define the bundle-first contract; legacy LlamaIndex-oriented code and CLI remain committed.

## 3. Code map

- Domain runs, targets, nodes, and readiness: `app/back/src/indexing/domain/`.
- Bundle-first indexing, activation, eligibility, and ports: `app/back/src/indexing/application/`.
- API: `app/back/src/indexing/api/` under `/api/indexing`.
- PostgreSQL, in-memory, provider, and LlamaIndex adapters: `app/back/src/indexing/infrastructure/`.
- Scripts/tests: `scripts/indexing/`, `app/back/tests/indexing/`.

## 4. Inputs and outputs

Bundle-first input is a sealed `EmbeddingBundle`, source chunk bundle, compatible durable profile/target, and vector artifact. The target comes from the profile, never browser input. Outputs are indexing run/document records, node rows, append-only vector rows, readiness checks, and activation state.

## 5. Operational flow

1. Prepare PostgreSQL and pgvector migrations.
2. Verify the embedding profile and obtain a sealed, validated bundle.
3. Resolve the profile default target and prove table/metric compatibility.
4. Build nodes directly from source chunk IDs and commit nodes/vectors per document, initially inactive.
5. Activate or roll back through the separate bundle-first activation use cases.

## 6. Rules and invariants

- Bundle-first code never calls embedding providers or re-chunks source content.
- Only sealed/validated bundles from verified profiles with unchanged source fingerprints are indexable.
- The target must be active, profile-table aligned, and metric-compatible.
- Eligibility excludes non-processed or unapproved documents.
- Vector rows are append-only/inactive first; `retrieval_profiles` is the authority over retrieval activation.

## 7. Critical variables and configuration

- `SST_FEATURE_INDEXING_BUNDLE_FIRST` gates bundle-first API writes and
  activation; `indexing_bundle_first` is the internal resolved flag field.
- `SST_POSTGRES_DSN`, `POSTGRES_*`, or `DATABASE_URL` configure preparation.
- The provider type includes mock/BGE/Voyage/Cohere, but live PostgreSQL CLI writes allow only BGE or Voyage; Voyage needs `VOYAGE_API_KEY`.
- `DEFAULT_MAX_QUEUE_SIZE=16`; vector tables match `idx_vec_[a-z0-9_]+`.

## 8. Logs, manifests, and observability

The canonical contract lists indexing document/profile/bundle/node/persistence events. CLI stdout is final JSON and stderr is structured operational logging. Inventory and review manifests under `data/docs_normalized/_manifests` support validation. See [current-contracts.md](../observability/current-contracts.md).

## 9. Commands and verification

```powershell
npm run test:indexing
npm run indexing:prepare-postgres
npm run indexing:run -- --dry-run
npm run indexing:validate
```

Preparation applies all committed SQL migrations and verifies base tables, active profiles, vector tables, and targets.

## 10. Visible inconsistencies and debt

- The committed tree had no README for this area.
- `run_indexing.py` uses the legacy normalized-document/LlamaIndex path; bundle-first consumes `EmbeddingBundle`. No single documented orchestrator joins them.
- Declared provider types and live PostgreSQL CLI allowances differ.

## 11. Missing pieces to reach the target model

- No committed bundle-first CLI performs create, execute, activate, rollback, or resume.
- The documented dry-run only covers the legacy CLI path.
- No consolidated migration/rollback runbook exists for vector tables and activation changes.

## 12. References

- `app/back/src/indexing/domain/bundle_first.py`
- `app/back/src/indexing/application/bundle_first/index_bundle.py`
- `app/back/src/indexing/application/bundle_first/activation.py`
- `app/back/src/indexing/application/eligibility.py`
- `scripts/indexing/prepare_postgres_indexing.py`
- `scripts/indexing/run_indexing.py`
- `scripts/indexing/validate_index.py`
- `app/back/tests/indexing/`
