# Handoff frontend — Embedding, Indexing y Retrieval bundle-first

Contrato **real implementado**. OpenAPI completo: `docs/api/pipeline-openapi.json`
(23 rutas, 40 schemas). Generado desde `api.app.create_app`.

Todos los cuerpos JSON son `snake_case`.

---

## 1. Envelope de error (idéntico a Chunking)

```json
{
  "error": {
    "code": "EMBEDDING_PROFILE_COMPATIBILITY_NOT_PROVEN",
    "message": "profile local-bge-m3-v1 is not enabled for document embedding",
    "run_id": null,
    "details": {}
  }
}
```

Códigos publicados:

```text
EMBEDDING_PROFILE_NOT_FOUND                     404
EMBEDDING_PROFILE_COMPATIBILITY_NOT_PROVEN      409
EMBEDDING_ENGINE_NOT_FOUND                      409
EMBEDDING_ENGINE_UNAVAILABLE                    503
EMBEDDING_ENGINE_REVISION_MISMATCH              409
EMBEDDING_ENGINE_SEMANTIC_MISMATCH              409
EMBEDDING_BUNDLE_INVALID                        409
EMBEDDING_BUNDLE_STALE                          409
EMBEDDING_BUNDLE_NOT_FOUND                      404
EMBEDDING_RUN_NOT_FOUND                         404
CHUNK_BUNDLE_NOT_FOUND                          404
IDEMPOTENCY_CONFLICT                            409
EMBEDDING_EXECUTOR_BUSY                         429
INDEXING_RUN_NOT_FOUND                          404
INDEXING_TARGET_INCOMPATIBLE                    409
INDEXING_EXECUTOR_BUSY                          429
INDEXING_ACTIVATION_BLOCKED                     409
QUERY_EMBEDDING_UNSUPPORTED                     409
RETRIEVAL_PROFILE_NOT_FOUND                     404
RETRIEVAL_PROFILE_BLOCKED                       409
POSTGRES_UNAVAILABLE                            503
PGVECTOR_UNAVAILABLE                            503
EMBEDDING_V2_DISABLED                           503
INDEXING_BUNDLE_FIRST_DISABLED                  503
RETRIEVAL_V1_DISABLED                           503
PIPELINE_INVALID_REQUEST                        422
PIPELINE_ROUTE_NOT_FOUND                        404
```

## 2. Paginación

Todo listado devuelve exactamente:

```json
{ "items": [], "page": 1, "page_size": 25, "total_items": 0, "total_pages": 0 }
```

Query params: `page >= 1`, `1 <= page_size <= 100` (default 25). Fuera de rango → `422 PIPELINE_INVALID_REQUEST`.

## 3. Headers

- `Idempotency-Key` **obligatorio** en `POST /api/embedding/runs` y `POST /api/indexing/runs`. Ausente → `422`.
- Misma key + mismo payload → devuelve el run existente (mismo id, `202`).
- Misma key + payload distinto → `409 IDEMPOTENCY_CONFLICT`.

---

## 4. Embedding

### `GET /api/embedding/profiles`

`items[]`:

```json
{
  "profile_id": "local-bge-m3-v1",
  "provider": "bge",
  "model": "BAAI/bge-m3",
  "model_revision": "unknown_revision",
  "dimension": 1024,
  "normalization": "unknown_normalization",
  "distance_metric": "cosine",
  "configuration_fingerprint": null,
  "ingestion_origin": "local",
  "chunking_version": "structure-aware-v1",
  "vector_table": "idx_vec_local_bge_m3_v1",
  "default_indexing_target_id": "target-idx-vec-local-bge-m3-v1",
  "active": true,
  "document_enabled": false,
  "query_enabled": false,
  "compatibility_status": "compatibility_not_proven",
  "deprecated_at": null,
  "can_embed_documents": false,
  "can_embed_queries": false
}
```

**Todo esto es metadata de solo lectura.** El frontend nunca envía provider,
model, dimension, normalization ni distance_metric.

Enums:
- `compatibility_status`: `verified | legacy_unverified | compatibility_not_proven`
- `normalization`: `unknown_normalization | none | l2 | provider_normalized`
- `distance_metric`: `cosine | l2 | inner_product`

**Selección permitida:** el usuario solo puede elegir un `profile_id` con
`can_embed_documents == true`. Los demás deben mostrarse **bloqueados**
(hoy los 7 perfiles legacy están bloqueados; ver §9).

### `GET /api/embedding/runtime`

```json
{
  "profile_id": "local-bge-m3-v1",
  "provider": "bge",
  "model": "BAAI/bge-m3",
  "runtime_mode": "local",
  "engine_available": true,
  "engine_revision_observed": "unknown_revision",
  "supports_documents": false,
  "supports_queries": false,
  "blocked_reason": "EMBEDDING_PROFILE_COMPATIBILITY_NOT_PROVEN"
}
```

`runtime_mode`: `local | cloud | dry_run | legacy`.

### `GET /api/embedding/chunk-bundles`

```json
{
  "chunk_bundle_id": "chunk-bundle-bd4a...",
  "bundle_fingerprint": "chunk-bundle-bd4a...",
  "profile_id": "local-structural-v1",
  "corpus_version": "phase1-main",
  "source_document_id": "doc_2fd43b5d3bcb833b",
  "parent_count": 1,
  "child_count": 1,
  "status": "legacy_unverified"
}
```

### `GET /api/embedding/chunk-bundles/{chunk_bundle_id}/summary`

Lo anterior más `profile_fingerprint` y `embedding_bundle_ids: string[]`.

### `POST /api/embedding/runs` → `202`

**Request (MVP — singular, NO una lista):**

```json
{ "chunk_bundle_id": "chunk-bundle-...", "profile_id": "local-bge-m3-v1" }
```

Header `Idempotency-Key` obligatorio.

**Response = objeto run completo** (mismo schema que `GET /runs/{id}`):

```json
{
  "embedding_run_id": "embedding-run-<sha256>",
  "idempotency_key": "...",
  "request_fingerprint": "<sha256>",
  "source_chunk_bundle_id": "chunk-bundle-...",
  "embedding_profile_id": "local-bge-m3-v1",
  "configuration_fingerprint": "<sha256>",
  "runtime_engine": "bge",
  "runtime_mode": "local",
  "engine_revision_observed": "unknown_revision",
  "status": "pending",
  "started_at": null,
  "completed_at": null,
  "created_at": "2026-08-05T21:00:00+00:00",
  "summary": { "requested_children": 12, "embedded_children": 0 },
  "warnings": [],
  "error_summary": null,
  "produced_embedding_bundle_id": null,
  "links": { "self": "/api/embedding/runs/embedding-run-..." }
}
```

**Estados** (`status`, valores reales del esquema SQL):

```text
pending  running  completed  failed  cancelled  blocked
```

- **Terminales:** `completed`, `failed`, `cancelled`, `blocked`.
- No hay cancelación cooperativa: `cancelled` existe en el esquema pero el
  backend nunca lo emite hoy.
- «completed con warnings» = `status == "completed"` y `warnings.length > 0`.
- Un run interrumpido por reinicio se reconcilia a `failed` con
  `error_summary == "EMBEDDING_RUN_INTERRUPTED"`.

**Polling recomendado:** `GET /api/embedding/runs/{id}` cada **1 s** hasta estado
terminal; timeout de UI 5 min. `summary.embedded_children / summary.requested_children`
sirve como barra de progreso.

**IDs persistibles:** `embedding_run_id`, `produced_embedding_bundle_id`.

### `GET /api/embedding/bundles/{embedding_bundle_id}`

```json
{
  "embedding_bundle_id": "embedding-bundle-<sha256>",
  "source_chunk_bundle_id": "chunk-bundle-...",
  "embedding_profile_id": "local-bge-m3-v1",
  "provider": "bge",
  "model": "BAAI/bge-m3",
  "model_revision": "abc123",
  "dimension": 1024,
  "normalization": "l2",
  "distance_metric": "cosine",
  "configuration_fingerprint": "<sha256>",
  "corpus_version": "phase1-main",
  "bundle_schema_version": "embedding-bundle-v1",
  "source_content_fingerprint": "<sha256>",
  "vector_dtype": "float32",
  "vector_shape": "12x1024",
  "vector_count": 12,
  "checksums": { "vectors.npy": "<sha256>", "chunk_map.jsonl": "<sha256>", "manifest.json": "<sha256>" },
  "status": "sealed",
  "validation_status": "passed",
  "readiness_status": "ready",
  "sealed_at": "2026-08-05T21:00:03+00:00",
  "links": { "self": "...", "chunks": "...", "validation": "...", "indexing_readiness": "..." }
}
```

Enums: `status`: `pending | sealed | failed | legacy_unverified`;
`validation_status`: `pending | passed | failed | legacy_unverified | compatibility_not_proven`;
`readiness_status`: `pending | ready | blocked | legacy_unverified | compatibility_not_proven`.

**Nunca devuelve vectores ni rutas absolutas.**

### `GET /api/embedding/bundles/{id}/chunks` (paginado)

```json
{
  "child_chunk_id": "child-...",
  "parent_chunk_id": "parent-...",
  "document_id": "doc_...",
  "vector_offset": 0,
  "vector_length": 1024,
  "vector_checksum": "<sha256>",
  "content_hash": "<sha256>",
  "chunk_ordinal": 0
}
```

Se lee de `embedding_bundle_chunks`. **Sin vectores.**

### `GET /api/embedding/bundles/{id}/validation`

```json
{
  "embedding_bundle_id": "...",
  "status": "passed",
  "validator_version": "embedding-validator-v1",
  "checks": [{ "name": "dimension_matches", "passed": true, "detail": "expected=1024" }]
}
```

### `GET /api/embedding/bundles/{id}/indexing-readiness`

```json
{
  "embedding_bundle_id": "...",
  "indexing_target_id": "target-idx-vec-local-bge-m3-v1",
  "status": "ready",
  "blocking_reasons": []
}
```

### Endpoints omitidos respecto al plan original

- `GET /api/embedding/runs/{id}/documents` — **omitido**. Un run consume un único
  `chunk_bundle_id` (= un documento); el detalle vive en `runs/{id}.summary.document_id`.
- `GET /api/embedding/runs/{id}/items` — **omitido**. No existe la tabla
  `embedding_run_items`; simular el detalle sería inventar datos. El detalle final
  por chunk está en `bundles/{id}/chunks`.

---

## 5. Indexing

### `GET /api/indexing/overview`

```json
{
  "targets": 7, "active_targets": 7,
  "profiles": 7, "verified_profiles": 0,
  "sealed_bundles": 0, "runs": 0, "completed_runs": 0, "active_runs": 0,
  "bundle_first_enabled": true
}
```

### `GET /api/indexing/targets` (paginado)

```json
{
  "indexing_target_id": "target-idx-vec-local-bge-m3-v1",
  "postgres_schema": "public",
  "vector_table": "idx_vec_local_bge_m3_v1",
  "distance_ops": "vector_cosine_ops",
  "storage_schema_version": "idx-vec-v1",
  "active": true,
  "deprecated_at": null
}
```

Informativo. **El frontend no elige target**: se resuelve desde
`indexing_profiles.default_indexing_target_id`.

### `POST /api/indexing/runs` → `202`

```json
{ "embedding_bundle_id": "embedding-bundle-..." }
```

Header `Idempotency-Key` obligatorio.
**No se envía** `provider`, `model`, `dimension`, `normalization`,
`distance_metric`, `indexing_target_id` ni `force`.

Response:

```json
{
  "run_id": "indexing-run-<sha256>",
  "profile_id": "local-bge-m3-v1",
  "status": "pending",
  "embedding_bundle_id": "embedding-bundle-...",
  "embedding_profile_id": "local-bge-m3-v1",
  "indexing_target_id": "target-idx-vec-local-bge-m3-v1",
  "corpus_version": "phase1-main",
  "idempotency_key": "...",
  "request_fingerprint": "<sha256>",
  "validation_status": "pending",
  "activation_status": "pending",
  "started_at": null,
  "completed_at": null,
  "summary": { "requested_documents": 1, "committed_documents": 0 },
  "warnings": [],
  "links": { "self": "...", "documents": "...", "errors": "...", "retrieval_readiness": "..." }
}
```

Enums:
- `status`: `pending | running | completed | failed | cancelled | blocked`
- `validation_status`: `pending | passed | failed | legacy_unverified | compatibility_not_proven`
- `activation_status`: `pending | active | inactive | rolled_back | blocked | legacy_unverified`

**Parcialmente completado** = `status == "failed"` con
`summary.committed_documents > 0`. Un run interrumpido añade
`summary.interrupted == true` y `warnings` incluye `INDEXING_RUN_INTERRUPTED`.

Polling: `GET /api/indexing/runs/{run_id}` cada **1 s**.

### `GET /api/indexing/runs/{run_id}/documents` (paginado)

```json
{
  "document_id": "doc_...",
  "source_relpath": "copasst/comunicacion.md",
  "status": "committed",
  "eligibility_status": "included",
  "eligibility_reason": "embedding_bundle_ready",
  "source_chunk_bundle_id": "chunk-bundle-...",
  "embedding_bundle_id": "embedding-bundle-...",
  "parent_count": 1,
  "child_count": 1,
  "vector_count": 1,
  "started_at": "...",
  "committed_at": "...",
  "error_code": null,
  "internal_error_id": null
}
```

`status`: `pending | running | committed | failed | skipped | legacy_unverified`.
**Un documento solo cuenta como indexado con `committed_at != null`.**

### `GET /api/indexing/runs/{run_id}/errors` (paginado)

```json
{ "document_id": "doc_...", "status": "failed", "error_code": "EMBEDDING_BUNDLE_STALE", "internal_error_id": "a1b2..." }
```

`internal_error_id` correlaciona con los logs del backend. **No hay stack traces.**

### `GET /api/indexing/runs/{run_id}/retrieval-readiness`

```json
{
  "run_id": "...",
  "embedding_bundle_id": "...",
  "indexing_target_id": "...",
  "corpus_version": "phase1-main",
  "ready": false,
  "active_vector_rows": 0,
  "blocking_reasons": ["INDEXING_BUNDLE_NOT_ACTIVATED"]
}
```

`blocking_reasons` posibles: `INDEXING_RUN_NOT_COMPLETED`,
`INDEXING_BUNDLE_NOT_ACTIVATED`, `NO_ACTIVE_VECTOR_ROWS`,
`INDEXING_TARGET_INCOMPATIBLE`.

### `POST /api/indexing/activations` (indexar ≠ activar)

Requiere el flag `indexing_bundle_first`; con el flag apagado devuelve
`503 INDEXING_BUNDLE_FIRST_DISABLED`.

**El `consumer_scope` NO se envía en el body.** Lo resuelve el servidor
(`SST_CONSUMER_SCOPE_TYPE` / `SST_CONSUMER_SCOPE_ID`, por defecto
`chatbot` / `sst-default`). Un body que incluya `consumer_scope_type` o
`consumer_scope_id` es rechazado con `422 PIPELINE_INVALID_REQUEST`: un cliente
no puede elegir el scope cuyo perfil activo muta.

```json
{
  "run_id": "indexing-run-...",
  "lexical_fallback_policy": "allowed_when_vector_unavailable"
}
```

→ `200`:

```json
{
  "run_id": "...",
  "embedding_bundle_id": "...",
  "indexing_target_id": "...",
  "retrieval_profile_id": "retrieval-profile-<sha256>",
  "activated_rows": 12
}
```

### `POST /api/indexing/rollbacks`

Mismo gate (`indexing_bundle_first`) y mismo scope server-side que
`/activations`. El scope tampoco se envía en el body.

```json
{
  "current_embedding_bundle_id": "...",
  "previous_embedding_bundle_id": "..."
}
```

Misma response. **No regenera embeddings.**

---

## 6. Retrieval

`consumer_scope_type` / `consumer_scope_id` son genéricos mientras no exista una
entidad concreta de chatbot. Convención sugerida: `"chatbot"` / `"sst-default"`.

### `GET /api/retrieval/profiles` (paginado)

```json
{
  "retrieval_profile_id": "retrieval-profile-<sha256>",
  "consumer_scope_type": "chatbot",
  "consumer_scope_id": "sst-default",
  "corpus_version": "phase1-main",
  "embedding_profile_id": "local-bge-m3-v1",
  "indexing_target_id": "target-idx-vec-local-bge-m3-v1",
  "lexical_fallback_policy": "allowed_when_vector_unavailable",
  "active": true,
  "validation_status": "passed",
  "validated_at": "...",
  "last_runtime_status": "ok",
  "created_at": "...",
  "deprecated_at": null
}
```

Enums:
- `validation_status`: `pending | passed | failed | compatibility_not_proven`
- `last_runtime_status`: `never_run | ok | failed | blocked`
- `lexical_fallback_policy`: `allowed_when_vector_unavailable | never | always`

### `POST /api/retrieval/profiles` → `201`

```json
{
  "consumer_scope_type": "chatbot",
  "consumer_scope_id": "sst-default",
  "corpus_version": "phase1-main",
  "embedding_profile_id": "local-bge-m3-v1",
  "indexing_target_id": "target-idx-vec-local-bge-m3-v1",
  "lexical_fallback_policy": "allowed_when_vector_unavailable"
}
```

Se crea **inactivo**.

### `POST /api/retrieval/profiles/{id}/activate`

Sin cuerpo. `409 RETRIEVAL_PROFILE_BLOCKED` si readiness falla; el perfil queda
`validation_status: "failed"`, `active: false`.

### `GET /api/retrieval/profiles/{id}/status`

```json
{
  "profile": { "...": "RetrievalProfileSchema" },
  "runtime": {
    "retrieval_profile_id": "...",
    "embedding_profile_id": "...",
    "indexing_target_id": "...",
    "query_engine_available": true,
    "engine_revision_observed": "abc123",
    "vector_retrieval_enabled": true,
    "lexical_fallback_allowed": true,
    "blocked_reason": null
  },
  "readiness": {
    "retrieval_profile_id": "...",
    "ready": true,
    "active_vector_rows": 12,
    "embedding_bundle_id": "embedding-bundle-...",
    "blocking_reasons": []
  }
}
```

`blocking_reasons` posibles: `RETRIEVAL_PROFILE_BLOCKED`,
`RETRIEVAL_PROFILE_NOT_VALIDATED`, `EMBEDDING_PROFILE_COMPATIBILITY_NOT_PROVEN`,
`INDEXING_TARGET_INCOMPATIBLE`, `NO_ACTIVE_VECTOR_ROWS`, `MULTIPLE_ACTIVE_BUNDLES`.

### `POST /api/retrieval/validate`

```json
{ "retrieval_profile_id": "retrieval-profile-..." }
```

→

```json
{
  "retrieval_profile_id": "...",
  "status": "passed",
  "validator_version": "retrieval-validator-v1",
  "query_dimension": null,
  "candidates_found": 3,
  "blocking_reasons": []
}
```

Usa una **query sintética** interna. Nunca se almacena una pregunta real de
usuario en `readiness_checks`.

---

## 7. Feature flags

Variables de entorno del backend (no expuestas por API):

```text
SST_FEATURE_EMBEDDING_V2
SST_FEATURE_INDEXING_BUNDLE_FIRST
SST_FEATURE_RETRIEVAL_V1
```

Con el flag apagado, las **lecturas siguen funcionando** y las escrituras
devuelven `503` con `EMBEDDING_V2_DISABLED` / `INDEXING_BUNDLE_FIRST_DISABLED` /
`RETRIEVAL_V1_DISABLED`. El frontend debe deshabilitar los botones de creación
cuando reciba esos códigos, no ocultarlos.

`/api/indexing/activations` y `/api/indexing/rollbacks` también exigen
`indexing_bundle_first`; con el flag apagado devuelven `503
INDEXING_BUNDLE_FIRST_DISABLED`.

### Modo de persistencia (composición del servidor)

El servidor GUI elige el modo de persistencia de forma explícita:

```text
SST_PERSISTENCE_MODE   memory | postgres   (por defecto: postgres si hay
                                            SST_POSTGRES_DSN, si no memory)
SST_POSTGRES_DSN       DSN durable de PostgreSQL
```

- `postgres`: perfiles, targets y repositorios se leen de la base durable;
  aplica el filtro `review_status = approved`.
- `memory`: adaptadores en memoria, solo para demo y desarrollo local.
- En modo `postgres`, si la base no está disponible el arranque **falla cerrado**
  (`PostgresUnavailableAtStartup`); nunca degrada silenciosamente a memoria.

El scope de consumidor para activación/rollback es server-side
(`SST_CONSUMER_SCOPE_TYPE` / `SST_CONSUMER_SCOPE_ID`, por defecto
`chatbot` / `sst-default`) y no se acepta desde el body.

## 8. Flujo de pantalla recomendado

```text
1. GET /api/embedding/profiles      → elegir profile_id con can_embed_documents
2. GET /api/embedding/chunk-bundles → elegir chunk_bundle_id
3. POST /api/embedding/runs         (Idempotency-Key)  → poll 1s
4. GET  /api/embedding/bundles/{id}/indexing-readiness → status == "ready"
5. POST /api/indexing/runs          (Idempotency-Key)  → poll 1s
6. POST /api/indexing/activations   → devuelve retrieval_profile_id
7. GET  /api/retrieval/profiles/{id}/status  → readiness.ready == true
8. POST /api/retrieval/validate     → status == "passed"
```

## 9. Estado real de los perfiles hoy

Los 7 perfiles legacy quedaron, por el backfill `20260805_14`:

```text
compatibility_status = compatibility_not_proven
document_enabled     = false
query_enabled        = false
configuration_fingerprint = NULL
model_revision       = "unknown_revision"
```

Por tanto **`can_embed_documents` y `can_embed_queries` son `false` en todos**, y
`POST /api/embedding/runs` responde `409
EMBEDDING_PROFILE_COMPATIBILITY_NOT_PROVEN`. Es el comportamiento correcto:
la UI debe mostrarlos bloqueados con ese motivo.

Se desbloquean solo por el proceso explícito de verificación del backend:

```bash
npm run embedding:verify-profile -- --profile-id local-bge-m3-v1 --apply
```

No hay endpoint HTTP de verificación en el MVP.
