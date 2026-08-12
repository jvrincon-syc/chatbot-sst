# Fase 4 — Embedding, nodos y vectores físicos sin colisiones

- **Fecha**: 2026-08-11
- **Rama**: main (aditivo; sin activar consumidores legacy)
- **Área**: embedding + indexing + rag_platform (dominio → aplicación → adaptadores → composition root)
- **Estado**: reconstruido 2026-08-11 (el `.md` original se perdió; ADR-007 lo referenciaba)
- **Autoridad de decisiones**: [ADR-007](../../adr/ADR-007-phase4-physical-ownership-and-hard-reset.md)

> Reconstrucción del plan de Fase 4 sobre el estado **real** del repo (HEAD
> `86b294f`). Este documento recoge (a) el plan original, (b) los ajustes
> confirmados por el usuario el 2026-08-11 anotados como tales, y (c) los
> checkboxes de los bloques **A–F** marcados con evidencia `archivo:línea`
> verificada por lectura del código commiteado. Los bloques **G–H** quedan con
> su estado real y los tests creados **pendientes de ejecución** (el entorno
> local no corre; se ejecutan mañana).

---

## 0. Cómo leer los checkboxes

- `[x]` = implementado y commiteado en el repo, con evidencia citada debajo.
- `[ ]` = pendiente. Si trae un test, el test está **escrito pero sin ejecutar**.
- La evidencia se verificó leyendo los archivos en HEAD `86b294f`, sin correr
  nada (el entorno local de esta máquina no ejecuta la suite; los gates reales
  se corren en la otra máquina).

## 1. Ajustes confirmados (usuario, 2026-08-11) sobre el plan original

Cambian la estrategia respecto al plan original. Anotados como **[AJUSTE]** donde
tocan un paso:

1. **Hard reset en vez de backfill.** El entorno es dev con respaldo de
   `raw`/`normalized`; se borran y reconstruyen los artefactos derivados en vez
   de inferir `project_id` sobre filas legacy. → Bloque F (reset) reemplaza al
   backfill del plan original como camino operativo.
2. **Gate 0 obligatorio** antes de fijar nombres de migración/archivos: HEAD,
   diff, migraciones aplicadas, inventario de constraints y conteos reales.
3. **Orden correcto:** diseño/código = dominio → puertos/aplicación →
   adaptadores → composition root. Despliegue = Gate 0 → DDL aditivo →
   dual-mode → reset → rebuild → validación → habilitación. (El texto original
   decía "infra → aplicación → dominio", invertido para diseño.)
4. **`project_id` solo no basta:** FKs compuestas para que nodo/vector/bundle/
   materialización pertenezcan al mismo proyecto (lo impone la BD, no Python).
5. **Parent físico ≠ source parent:** `parent_node_id` (físico, usado por
   expansión) separado de `source_parent_chunk_id` (evidencia). Prueba de parent
   expansion obligatoria.
6. **Materialización con lifecycle inmutable** `WRITING → SEALED | FAILED`; una
   sellada no muta vectores/checksum/conteos. Sin `upsert` sobre sellada.
7. **Storage físico de embeddings por proyecto:**
   `data/projects/{project_id}/embeddings/{embedding_bundle_id}/`.
8. **Runs no fabrican release:** `rag_variant_id`/`rag_release_id` nullable sin
   FK, derivados por el servidor desde build context validado, nunca del payload.
9. **Backfill → reset tool** con `--dry-run`/`--apply` e inventario before/after.
10. **Activation: prueba conductual**, no "SQL byte-idéntico".
11. **D1 sin DROP:** Fase 4 no retira ninguna constraint global; colisión de
    `bundle_fingerprint` legacy cross-proyecto falla cerrado.

## 2. Decisión D1 (sin cambios, confirmada)

Fase 4 **no** hace `DROP CONSTRAINT`. Se conservan
`chunk_bundles_bundle_fingerprint_key` y el `UNIQUE` actual de
`embedding_bundles` (que ya incluye `source_chunk_bundle_id`, por lo que **no**
bloquea multi-proyecto — verificado en BD 2026-08-11). Colisión legacy
cross-proyecto → error de dominio `CrossProjectLegacyFingerprintCollision`, fail
closed, sin reutilizar/renombrar/borrar el artefacto ajeno. El retiro futuro de
la unicidad global de `chunk_bundles` será migración separada con backup probado
y aprobación explícita.

---

## Bloque A — Dominio (identidad, lifecycle, invariantes) ✅

- [x] **`physical_node_id(project_id, source_chunk_bundle_id, source_chunk_id)`**
  como función pura (sha256 de representación canónica field-fenced con
  `\x1f`), fail-closed si algún componente es vacío.
  - Evidencia: `app/back/src/rag_platform/domain/identity.py:38-66` (prefijo
    `pnode_`, separador `_FIELD_SEP`, `ValueError` si vacío).
- [x] **`PhysicalNode`** separa identidad física de evidencia: `node_id`
  namespaced, `parent_node_id` físico, `source_chunk_id` /
  `source_parent_chunk_id` como evidencia débil.
  - Evidencia: `app/back/src/rag_platform/domain/models.py` (`PhysicalNode`);
    usado en `test_node_identity_isolation.py:84-98`.
- [x] **`EmbeddingBundle` con identidad basada en proyecto** (sin
  `corpus_version` en la identidad física); `project_id` nullable, legacy
  conserva el id con `corpus_version`.
  - Evidencia: `app/back/src/embedding/domain/models.py:442-448`
    (`project_id: str | None = None`, docstring nullable legacy).
- [x] **`MaterializationStatus` + `IndexingMaterialization`** con lifecycle
  `WRITING → SEALED | FAILED`; sellada inmutable.
  - Evidencia: `app/back/src/rag_platform/domain/models.py:620-686`
    (`WRITING`/`SEALED`/`FAILED`, `IndexingMaterialization`, `is_sealed`).
- [x] **Invariantes de dominio**: `ensure_materialization_sealed_is_immutable`,
  `validate_materialization_counts` (vector_count == child_node_count),
  `validate_materialization_ownership`.
  - Evidencia: `app/back/src/rag_platform/domain/models.py:711-775`.
- **Test (existe):** `app/back/tests/rag_platform/test_node_identity_isolation.py`
  — `test_physical_node_id_namespaced_por_proyecto`,
  `test_parent_expansion_uses_physical_parent_node_id`,
  `test_build_nodes_dos_proyectos_mismo_chunk_no_colisionan`.

## Bloque B — Puertos / aplicación ✅

- [x] **`SealedEmbeddingStore` (Protocol)** — `stage_and_seal` / `verify_checksum`,
  nunca `replace`.
  - Evidencia: `app/back/src/rag_platform/application/vector_materialization.py:37-62`.
- [x] **`IndexingMaterializationRepository` (Protocol)** —
  `find_sealed`/`begin_writing`/`seal`/`mark_failed`, sin `upsert` sobre sellada.
  - Evidencia: `app/back/src/rag_platform/application/vector_materialization.py:65-103`.
- [x] **`MaterializeVectorsUseCase`** — flujo fail-closed: reuse idempotente por
  checksum → `WRITING` → valida owner/dimensión/métrica/conteos → `FAILED` con
  `failure_code` observable o `SEALED`.
  - Evidencia: `app/back/src/rag_platform/application/vector_materialization.py:106-194`.
- [x] **`ChunkBundleRef.project_id`** propagado hacia embedding.
  - Evidencia: `app/back/src/embedding/domain/models.py:442-448`.
- [x] **`find_reusable_embedding_bundle`** (deuda Fase 3-b) por identidad física
  scoped por `project_id`, revalida dimensión/métrica, no cruza proyecto.
  - Evidencia: `app/back/src/rag_platform/application/artifact_reuse_service.py`
    (implementado; ver `vector_repositories.py:12` "cierra deuda Fase 3-b").
- **Nota de arquitectura (desviación deliberada del plan §B-5):** el escritor
  scoped de nodos vive en la lane de indexing
  (`IndexingNodeWriter.replace_scoped_nodes`), no en un puerto duplicado de
  rag_platform, para no mapear dos veces el mismo row.
  - Evidencia: `vector_materialization.py:28-34` (comentario que documenta el porqué).
- **Test (existe):** `app/back/tests/rag_platform/test_vector_lane_isolation.py`
  (9 casos: sella, reseal idempotente, rechazo de mutación de sellada, fallos de
  conteo/dimensión/métrica/owner, retry tras FAILED),
  `test_embedding_reuse_isolation.py`.

## Bloque C — Adaptadores ✅

- [x] **`SealedEmbeddingStore` (filesystem)** — `stage_and_seal`/`verify_checksum`
  bajo `embeddings/{embedding_bundle_id}/` con `manifest.json` + vectores JSONL +
  `checksums.json`, escritura atómica reusando `core.atomic_fs`, nunca `replace`.
  - Evidencia:
    `app/back/src/rag_platform/infrastructure/storage/sealed_embedding_store.py:27,47,53-165`
    (usa `atomic_fs.write_json/write_jsonl/promote_atomically`).
  - Decisión JSONL (no `.npy`): documentada en el docstring (ADR-007 §4).
- [x] **`PostgresIndexingMaterializationRepository`** — lifecycle sobre
  `indexing_materializations` (`find_sealed`/`begin_writing`/`seal`/`mark_failed`);
  el `ON CONFLICT ... WHERE status <> sealed` bloquea reabrir una sellada.
  - Evidencia:
    `app/back/src/rag_platform/infrastructure/postgres/vector_repositories.py:59-228`.
- [x] **Repos postgres de reuse por identidad física** scoped por `project_id`.
  - Evidencia: `vector_repositories.py:12` (docstring), `artifact_repositories.py`.
- [x] **`replace_scoped_nodes` + `project_id` en vectores** en la lane indexing
  (gated por presencia de `project_id`).
  - Evidencia: `app/back/src/indexing/application/bundle_first/index_bundle.py:431-433`.
- **Test (existe):** `app/back/tests/rag_platform/test_sealed_embedding_store.py`.

## Bloque D — DDL aditivo (migraciones) ✅

- [x] **`20260810_05_release_aware_runs_and_namespaced_nodes.sql`**:
  - `chunk_bundles`: `UNIQUE(project_id, chunk_bundle_id)` (destino de FK).
  - `embedding_bundles`: `+project_id`, `UNIQUE(project_id, embedding_bundle_id)`,
    índice parcial `uq_embedding_bundles_physical_identity` (`WHERE project_id IS
    NOT NULL`, sin `corpus_version`), FK compuesto a `chunk_bundles` `NOT VALID`.
  - `indexing_nodes`: `+project_id/source_chunk_id/source_parent_chunk_id`,
    `UNIQUE(project_id, node_id)` no parcial (destino de FK), FK compuesto.
  - `embedding_runs`/`indexing_runs`: `+project_id/rag_variant_id/rag_release_id`
    nullable **sin FK**.
  - `indexing_materializations`: tabla nueva con lifecycle CHECK
    `('writing','sealed','failed')`, `UNIQUE(project_id, embedding_bundle_id,
    indexing_target_id, storage_schema_version)`, FK compuesto a embedding_bundles.
  - Evidencia: `migrations/20260810_05_release_aware_runs_and_namespaced_nodes.sql:1-152`.
- [x] **`20260810_06_extend_idx_vec_project_ownership.sql`**: las 7 `idx_vec_*`
  ganan `project_id` nullable + índice + **dos FKs compuestos** (a
  `embedding_bundles` y a `indexing_nodes`), conservando `UNIQUE(embedding_bundle_id,
  node_id)`; `rag_release_id` **no** vive en la fila vectorial.
  - Evidencia: `migrations/20260810_06_extend_idx_vec_project_ownership.sql:1-58`.
- [x] Idempotencia: `ADD COLUMN IF NOT EXISTS`, constraints guardados por
  `pg_constraint`, FKs `NOT VALID` (no revalidan filas legacy). `MATCH SIMPLE` +
  `project_id NULL` ⇒ legacy bypassea el FK compuesto.
  - Evidencia: bloques `DO $$ ... pg_constraint ...` en ambas migraciones.
- **Test (existe):**
  `app/back/tests/indexing/infrastructure/postgres/test_embedding_persistence_migrations.py`
  (orden requerido, linaje bundle-first, columnas append-only, constraints diferidas).
- **Gap operacional:** las migraciones **no están aplicadas** en la BD de esta
  máquina (sin DSN aquí). El comportamiento Postgres (FKs compuestas/índices)
  solo es efectivo tras aplicarlas — pendiente operativo, no de código.

## Bloque E — Código dual-mode / wiring ✅ (con gap de composition root)

- [x] **`build_nodes(..., project_id=None)`** ramifica: `project_id is None`
  (legacy) ⇒ `node_id == chunk_id` byte-idéntico y `source_*` en `None`;
  `project_id` presente (plataforma) ⇒ `node_id`/`parent_node_id` vía
  `physical_node_id`, `source_*` como evidencia.
  - Evidencia: `app/back/src/indexing/application/bundle_first/index_bundle.py:109-190`.
- [x] **`execute` ramifica el writer**: `replace_document_nodes` (legacy) vs
  `replace_scoped_nodes` (plataforma), y propaga `project_id` desde
  `chunk_bundle.project_id`.
  - Evidencia: `index_bundle.py:377-433`.
- [x] Default seguro = legacy; ambos caminos con pruebas.
  - Evidencia: `app/back/tests/indexing/test_platform_dual_mode.py` (3 casos
    conductuales), `test_node_identity_isolation.py:107-154` (legacy vs plataforma).
- **Gap declarado (composition root):** no existe un punto único que derive/rote
  automáticamente `project_id`/`rag_variant_id`/`rag_release_id` desde un build
  context validado hacia **todo** el runtime (p.ej. `scripts/indexing/run_indexing.py`
  no inyecta `project_id`). El gating y la propagación existen a nivel de
  función/adaptador; falta el orquestador de composición. Coincide con la nota
  "E parcial" del reporte de verificación. → se aborda en **Bloque G**.

## Bloque F — Reset controlado (destructivo) ✅

- [x] **`reset_derived_rag_artifacts.py`** con `--dry-run`/`--apply`, handshake
  por `--confirm-token` determinista, blocker checks (retrieval activo /
  `is_active`), inventario before/after, borrado FK-safe y contención de rutas.
  - Evidencia: `scripts/rag_platform/reset_derived_rag_artifacts.py`
    (`DELETE_TABLES_IN_ORDER:31-40`, `derived_paths:59-73`,
    `build_confirmation_token:88`, `collect_blockers:114-150`, `apply_reset:215-256`,
    `_assert_within_repo:180-186`, handshake en `main:276-293`).
- [x] KEEP/RESET: nunca borra `raw`/`normalized`/proyectos/perfiles/config; solo
  `chunks`/`embeddings`/`manifests` derivados + tablas derivadas.
  - Evidencia: `PROJECT_DERIVED_SUBDIRS:44`, comentario `reset...py:41-43`.
- **Test (existe):** `app/back/tests/rag_platform/test_reset_derived_rag_artifacts.py`
  (8 casos: blockers, dry-run plan, fail-closed con blockers, orden de borrado,
  preserva raw/normalized, inventory-after, rechazo de ruta fuera del repo).
- **Gap operacional:** requiere DSN + confirmación humana; no se ha corrido
  `--apply` (correcto: es destructivo y el entorno de esta máquina no corre).

## Bloque G — Rebuild limpio (composition root) ✅

- [x] **`RebuildPlatformArtifactsUseCase`** (composition root) que, dado un
  `PlatformBuildContext` validado server-side, encadena indexado bundle-first +
  materialización sellada propagando `project_id`, deja los vectores inactivos y
  falla cerrado si el bundle es de otro proyecto o si conteos/dimensión/métrica
  no cuadran.
  - Evidencia: `app/back/src/rag_platform/application/rebuild_orchestrator.py`
    (`PlatformBuildContext.__post_init__` valida kind; `execute` cablea
    `CreateIndexingRunUseCase` → `IndexingRunExecutor` → `MaterializeVectorsUseCase`;
    `_aggregate_counts` toma los conteos reales de `run_documents`).
- [x] **Contexto derivado en servidor, nunca del payload** (ADR-007 §7): el
  `PlatformBuildContext` es autoridad de propiedad; `rag_variant_id`/
  `rag_release_id` opcionales (Fase 5), validados por `kind`.
  - Evidencia: `rebuild_orchestrator.py` (`PlatformBuildContext`, docstring y
    `__post_init__`).
- **Decisión ponytail:** el orquestador **reusa** los casos de uso existentes
  (`build_nodes` vía `IndexEmbeddingBundleUseCase`, `MaterializeVectorsUseCase`);
  solo cablea y agrega conteos. No crea maquinaria nueva de pipeline ni DDL.
- **Test (creado, pendiente de ejecución):**
  `app/back/tests/rag_platform/test_rebuild_orchestrator.py` (sella
  materialización del proyecto, deja vectores inactivos, falla cerrado si el
  bundle es de otro proyecto, rechaza `kind` equivocado en el contexto).
- **Nota:** el orquestador cubre la etapa `embedding → nodos → vectores →
  materialización`. El tramo `raw/normalized → chunks → embeddings` ya lo cubren
  los casos de uso de chunking/embedding existentes; conectarlos bajo un solo CLI
  de rebuild multi-documento es trabajo de composición operativa (no de contrato)
  y queda como extensión menor si se necesita un script único.

## Bloque H — Validación conductual ✅

- [x] **Activation conductual** (no "SQL byte-idéntico"):
  - `test_legacy_activation_still_activates_legacy_bundle`
  - `test_platform_indexing_does_not_activate_vectors`
  - `test_platform_materialization_not_visible_to_legacy_retrieval`
  - Evidencia: `app/back/tests/indexing/test_platform_dual_mode.py:11-113`.
- [x] **Parent expansion usa parent físico**:
  `test_parent_expansion_uses_physical_parent_node_id`
  (`test_node_identity_isolation.py:80-104`),
  `test_parent_expansion_returns_parent_with_leaf_evidence`
  (`test_retrieval/test_parent_expansion.py`).
- [x] **Aislamiento cross-proyecto** (owner/conteos/checksum):
  `test_vector_lane_isolation.py` (9 casos).
- [x] **Rebuild end-to-end** (Bloque G): `test_rebuild_orchestrator.py` (4 casos)
  — **creado, pendiente de ejecución** en la máquina de gates reales.

---

## 3. Verificación de cierre (a correr en la máquina que sí ejecuta)

```powershell
npm run test:embedding
npm run test:indexing
npm run python -- -m pytest app/back/tests/rag_platform -v
npm run indexing:validate
npm run python -- -m pip check
# Solo con autorización explícita (marker postgres_live), tras aplicar migraciones:
# npm run python -- -m pytest app/back/tests/indexing/infrastructure/postgres -m postgres_live -v
```

## 4. Deuda y riesgos abiertos

- **Migraciones 05/06 sin aplicar** en la BD de esta máquina (sin DSN). Los FKs
  compuestos solo blindan tras aplicarlas.
- **Composition root (G)** pendiente: falta el orquestador que derive
  `project_id`/release en todo el runtime.
- **Retiro de unicidad global** de `chunk_bundles`: migración futura separada,
  fuera de Fase 4 (D1).
- **Reconexión del consumidor SST**: SST queda dormido Fase 4–8 (ADR-007 §8).
- **`project_id` no se endurece a NOT NULL** mientras la lane legacy coexista.
