# Retrieval

## 1. Purpose and scope

Retrieval validates a consumer-scoped lane, embeds queries with the exact durable profile, searches active vector rows, and uses lexical fallback only under policy. It returns evidence with document, child/parent, page/section, profile, corpus, and bundle provenance.

## 2. Current branch state

This reflects committed `main` at `f918b512a5320b6fc434feefe1e3e9f780bc097b`. No retrieval README existed in that commit. The durable retrieval profile table comes from `migrations/20260805_13_create_retrieval_profiles.sql`.

## 3. Code map

- Domain profiles, errors, and evidence: `app/back/src/retrieval/domain/`.
- Lifecycle, readiness, query embeddings, and search: `app/back/src/retrieval/application/`.
- API: `app/back/src/retrieval/api/` under `/api/retrieval`.
- PostgreSQL/in-memory adapters: `app/back/src/retrieval/infrastructure/`.
- Fusion, evidence, and parent expansion: `app/back/src/retrieval/*.py`.
- Tests: `app/back/tests/retrieval/`.

## 4. Inputs and outputs

A profile binds consumer scope, corpus version, embedding profile, indexing target, and lexical policy. Search consumes that resolved profile, query, and `top_k`; it never accepts a client-supplied vector table. It returns `RetrievedEvidence` with source, score, location, profile/corpus, and vector bundle identity when available.

## 5. Operational flow

1. Create an inactive profile after proving profile/target compatibility.
2. Validate using a synthetic smoke query, then activate only when ready.
3. Readiness requires active/validated profile, query engine, compatible target, active rows, and one active bundle.
4. Resolve the query engine, vector-search the exact target/profile/corpus lane, then expand parents.
5. On query embedding failure, use lexical-only search only when policy permits; otherwise block.

## 6. Rules and invariants

- `retrieval_profiles` is the activation authority; vector `is_active` is a projection.
- A usable profile is active, validated, and not deprecated; one active profile exists per scope/corpus.
- Target table and metric must match the embedding profile.
- PostgreSQL vector and lexical searches restrict evidence to processed, approved documents.
- Zero or multiple active bundles block readiness; policy `never` forbids lexical-only answers.

## 7. Critical variables and configuration

- `SST_FEATURE_RETRIEVAL_V1` gates profile creation and activation routes;
  `retrieval_v1` is the internal resolved flag field.
- `lexical_fallback_policy` is `allowed_when_vector_unavailable`, `never`, or `always`; committed fallback is reached on query-embedding failure.
- `RETRIEVAL_VALIDATOR_VERSION=retrieval-validator-v1`; the smoke query is synthetic.
- Query engine semantics are resolved through the embedding registry.

## 8. Logs, manifests, and observability

Lifecycle code emits shared typed events and readiness is durable in `readiness_checks`. Use [current-contracts.md](../observability/current-contracts.md) for destinations and redaction. Do not log queries, evidence text, vectors, secrets, or provider bodies.

## 9. Commands and verification

```powershell
npm run test:retrieval
npm run test:pipeline
```

Focused coverage includes bundle-first end-to-end, API lifecycle, evidence/fusion/parent expansion, FTS, vector retrieval, and isolation audits.

## 10. Visible inconsistencies and debt

- The committed tree had no README for this area.
- `RetrievalSearchService.search` exists, but the committed router exposes lifecycle/status/validation only: no HTTP search endpoint calls it.
- The observability snapshot omits a retrieval event family despite shared event emission.

## 11. Missing pieces to reach the target model

- No public guarded query endpoint and operator contract are committed.
- No retrieval CLI/runbook covers smoke validation, policy decisions, failure, or rollback.
- Answer generation and citation verification are outside this module and have no implemented handoff documented here.

## 12. References

- `app/back/src/retrieval/domain/models.py`
- `app/back/src/retrieval/application/retrieval_service.py`
- `app/back/src/retrieval/application/query_embedding_service.py`
- `app/back/src/retrieval/infrastructure/postgres/repositories.py`
- `app/back/src/retrieval/evidence_builder.py`
- `app/back/tests/retrieval/`
