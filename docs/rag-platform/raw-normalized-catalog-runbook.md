# Runbook — Catálogos físicos raw/normalized por proyecto

Operación de la lane de plataforma que persiste en PostgreSQL el catálogo físico de
`raw` y `normalized` por `project_id`, con provenance de variante (`rag_variant_id`,
`semantic_recipe_fingerprint`) auditable de normalized a chunk. No sustituye el
dominio lógico (`project_documents`, `source_document_revisions`,
`project_normalized_documents`); lo acompaña con catálogos físicos.

## Invariantes

- `project_id` es **identidad obligatoria** de todo artefacto de plataforma (la BD lo
  exige NOT NULL en `chunk_bundles`, `embedding_bundles`, `indexing_nodes`, `idx_vec_*`,
  runs, materializaciones — ADR-008).
- `rag_variant_id` + `semantic_recipe_fingerprint` son **provenance nullable**, par
  atómico (ambos o ninguno). Nunca identidad ni dueño físico del artefacto.
- Los CLIs legacy (`scripts/ingestion/run_pipeline.py`, `scripts/chunking/run_chunking.py`)
  quedan intactos. La lane de plataforma entra por `scripts/rag_platform/`.
- Fail-closed: sin DSN o con `--project-id`/`--rag-variant-id` inexistente, los wrappers
  abortan con código 2 y no escriben nada.

## Precondición: esquema aplicado

```powershell
npm run indexing:prepare-postgres   # aplica migraciones en orden; status=prepared
```

Migraciones relevantes: `20260810_08` (project_id NOT NULL pure-platform),
`20260812_01` (catálogos raw/normalized), `20260812_02` (FKs compuestos a
profile/variant), `20260812_03` (provenance de variante en `chunk_bundles`).

## Secuencia operativa por proyecto

1. **Raw → catálogo físico** (revisión lógica + `project_raw_document_artifacts`):

   ```powershell
   npm run python -- scripts/rag_platform/run_project_ingestion.py --project-id proj_<slug>
   ```

   Escanea la raíz declarada `raw` del proyecto (catalog-driven; honra `raw` o
   `docs_raw` según `storage_roots`), crea/reutiliza cada revisión inmutable y hace
   upsert del sidecar físico. Idempotente.

2. **Normalize con provenance** (sidecar enriquecido + `project_normalized_document_artifacts`):
   la normalización corre por `run_pipeline` con un `platform_context_resolver` que
   inyecta `platform_identity` + `platform_provenance` en el metadata sidecar, y
   `PersistNormalizedArtifactCatalogUseCase` persiste la fila física con la receta de
   procesamiento (provider/engine/origin/config sanitizada) y, si aplica, la variante.
   Con `platform_context_resolver=None` el pipeline legacy queda byte-idéntico.

3. **Chunk con provenance** (nodos físicos + `chunk_bundles` con provenance):

   ```powershell
   npm run python -- scripts/rag_platform/rebuild_platform.py --project-id proj_<slug> [--rag-variant-id ragv_<x>]
   ```

   Con `--rag-variant-id`, la receta semántica se **deriva server-side** (nunca del
   payload) y se expone para auditoría. La provenance viaja al chunk desde el sidecar
   normalizado vía `platform_context`; `chunk_bundles` la persiste sin volverla identidad.

4. **Embed → index → materializa** (Fase 4 Stage 3): requieren BGE vivo y el wiring de
   materialización en el composition root; ver
   `plans/2026-08-11-fase4-embedding-nodos-vectores.md`.

## Verificación

```powershell
npm run python -- -m pytest app/back/tests/rag_platform app/back/tests/embedding app/back/tests/chunking app/back/tests/indexing -q
```

Focalizados de esta lane: `test_artifact_catalog_models`, `test_postgres_artifact_catalog_repositories`,
`test_raw_ingestion_service`, `test_normalized_catalog_service`, `test_platform_metadata_in_pipeline`,
`test_chunk_bundle_catalog`, `test_platform_cli_wrappers`.

## Seguridad de datos

- No se persisten secretos: solo `sanitized_config_json`, provider, engine, observed
  revision y fingerprints.
- Los bytes originales viven bajo `data/projects/{project_id}/raw`; PostgreSQL es la
  fuente de verdad de identidad y catálogo.
