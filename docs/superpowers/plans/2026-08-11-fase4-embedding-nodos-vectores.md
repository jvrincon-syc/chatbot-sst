# Fase 4 — Embedding, nodos y vectores físicos sin colisiones

> ✅ **CÓDIGO Y CONTRATO CERRADOS AL 100% (2026-08-13).** Bloques A–H + Stage 1/2a/2b-i/2b-ii
> + Stage 3 completo (CLI `rebuild_platform.py` encadena chunk→embed→index→materializa **y** la
> etapa `normalize` en `run_project_ingestion.py`) implementados, commiteados y verdes
> (`rag_platform` **135 passed**, 2026-08-13). No queda contrato abierto.
>
> **Remanentes NO de contrato, trasladados al plan maestro** (por eso el plan no es "100%
> operativo"): (1) **Stage 2b-iii** — retiro de la lane legacy document (~1600 LOC + ~30 tests,
> refactor de borrado; prerequisito ya cumplido); (2) **corrida operativa end-to-end con BGE
> vivo**, hoy bloqueada por falta de seed de proyecto/variante en BD. Ver "Cierre Fase 4" al final.

- **Fecha**: 2026-08-11 · unificado 2026-08-12
- **Rama**: main (aditivo; sin activar consumidores legacy)
- **Área**: embedding + indexing + rag_platform (dominio → aplicación → adaptadores → composition root)
- **Autoridad de decisiones**: [ADR-007](../docs/adr/ADR-007-phase4-physical-ownership-and-hard-reset.md), ADR-006
- **Master**: `docs/superpowers/plans/Plan_Ajustado_Plataforma_RAG_MultiProyecto(3).md`

> **Fuente única de verdad de Fase 4.** Unifica el subplan derivado
> (`plans/2026-08-11-...`) con el reporte reconstruido (que se había duplicado en
> `docs/superpowers/plans/2026-08-11-...`, ya eliminado). Los checkboxes reflejan
> el estado **real verificado el 2026-08-12** por lectura de código y ejecución de
> tests, no el estado histórico de "pendiente de ejecución".
>
> Aditivo sobre la lane legacy; **no retira constraints globales**. Entorno de
> **dev** (no producción): **hard reset + rebuild** de artefactos derivados en vez
> de backfill. SST queda **dormido** durante Fase 4–8: el rebuild es platform-only
> y no activa vectores ni cambia `is_active`/`retrieval_profiles`.

## Objetivo

Embeddings, nodos y vectores físicos son **propiedad del proyecto** e imposibles
de cruzar entre proyectos (aislamiento impuesto por la BD con FKs compuestas).

## Cómo leer los checkboxes

- `[x]` = implementado, commiteado y **verificado** (evidencia `archivo:línea` +
  test verde).
- `[~]` = código/contrato hecho; **acción operativa** (aplicar sobre BD/filesystem
  vivo) pendiente por diseño (gate destructivo o despliegue).
- `[ ]` = pendiente real.

---

## Estado de verificación (2026-08-12)

| Suite / acción | Resultado |
| --- | --- |
| `pytest app/back/tests/rag_platform -q` | **108 passed** (1.89s) |
| `pytest app/back/tests/embedding -q` | **70 passed** (12.98s) |
| `pytest app/back/tests/indexing` | passed (confirmado por usuario) |
| Hard reset de BD | ejecutado por usuario (BD vacía) |
| `npm run indexing:prepare-postgres` (aplica migraciones sobre BD vacía) | **status=prepared**, 27 migraciones (incluye plataforma `20260810_01–07`), `base_tables_present=12/12`, `active_profiles=7`, `vector_tables_ready=7`, `active_targets_ready=7` |

Los bloques **A–H** de código/contrato están **cerrados y verdes**. Los **gaps de
código de Fase 4 (auditados en el master, #1 identidad de bundle y #2 runs con
contexto de release) están CERRADOS** — ver "Auditoría verificada" abajo.

Lo que resta de Fase 4 es **operativo end-to-end**: no existe todavía un CLI de
la lane de plataforma que encadene `normalized → chunk → embed → index →
materializa` propagando `project_id`. `scripts/chunking/run_chunking.py` y
`scripts/indexing/run_indexing.py` son la **lane legacy** (sin `--project-id`); el
`RebuildPlatformArtifactsUseCase` parte de un `embedding_bundle_id` de plataforma
que hoy nada produce por CLI. → ver Gap #3 de la tabla.

## Auditoría verificada de gaps de código Fase 4 (2026-08-12, contra HEAD)

El master (`Plan_Ajustado_...(3).md` §Auditoría 2026-08-11) listaba 2 gaps de
código de Fase 4. Re-verificados contra el código actual:

- **Gap #1 — identidad de plataforma en el bundle de escritura: CERRADO.**
  `EmbeddingBundle.project_id` presente y persistido; `deterministic_id` sin cambio.
  - Evidencia: `embedding/domain/models.py:456-462`,
    `embedding/infrastructure/postgres/repositories.py:705,879`.
- **Gap #2 — runs no persisten contexto de release: CERRADO** (el master lo daba
  "solo a nivel DDL"; ya está en dominio + adaptador).
  - Evidencia: `embedding/domain/models.py:298-312` (`EmbeddingRun.project_id/
    rag_variant_id/rag_release_id`), `indexing/domain/bundle_first.py:87-102`
    (`IndexingRun` idem), `embedding/infrastructure/postgres/repositories.py:81-90`
    (`_RUN_COLUMNS`), `:534-550` (INSERT), `:673-675` (mapeo lectura).

---

## Gate 0 — estado real (verificado 2026-08-11, solo lectura)

- **Git:** baseline commiteado. HEAD limpio antes de empezar (`86b294f`).
- **DB `chatbot_sst`:** al inicio `20260810_01–04` aplicadas; hoy `01–07` aplicadas.
  Conteos iniciales: `chunk_bundles` 56, `embedding_bundles` 15, `embedding_runs` 9,
  `indexing_runs` 2, `indexing_nodes` 24, `idx_vec_local_bge_m3_v1` 18.
- **Unicidades reales:** `chunk_bundles` `UNIQUE(bundle_fingerprint)` = **global**
  (retiro diferido, D1). `embedding_bundles` `UNIQUE(source_chunk_bundle_id,
  embedding_profile_id, configuration_fingerprint, corpus_version,
  source_content_fingerprint, bundle_schema_version)` = **ya scoped** → NO se retira.
- **Filesystem:** legacy `data/chunks`, `data/embeddings`. `data/projects/` nace en rebuild.

### Reset Scope (firmado)

```
KEEP                                     RESET / REBUILD
rag_projects, project_*, configuración   chunk_bundles, embedding_bundles,
indexing_normalized_documents            embedding_bundle_chunks
raw / normalized (data/docs_*)           embedding_runs, indexing_runs
processing/chunking/embedding profiles   indexing_nodes, readiness_checks
indexing_profiles / targets              indexing_materializations (nueva)
rag_build_runs / rag_build_steps         idx_vec_* (filas)
                                         filesystem: data/chunks, data/embeddings,
                                                     data/projects/*
```

Nunca se borran `raw`, `normalized`, proyectos, perfiles ni configuración.

## Ajustes confirmados (usuario, 2026-08-11) — resumen ADR-007

1. **Hard reset en vez de backfill** (dev con respaldo raw/normalized).
2. **Gate 0 obligatorio** antes de fijar nombres de migración.
3. **Orden diseño:** dominio → puertos/aplicación → adaptadores → composition root.
   **Despliegue:** Gate 0 → DDL aditivo → dual-mode → reset → rebuild → validación → habilitación.
4. **`project_id` solo no basta:** FKs compuestas (BD, no Python).
5. **Parent físico ≠ source parent:** `parent_node_id` físico vs `source_parent_chunk_id` evidencia.
6. **Materialización lifecycle inmutable** `WRITING → SEALED | FAILED`; sellada no muta.
7. **Storage físico por proyecto:** `data/projects/{project_id}/embeddings/{embedding_bundle_id}/`.
8. **Runs no fabrican release:** `rag_variant_id`/`rag_release_id` nullable sin FK, derivados server-side.
9. **Backfill → reset tool** `--dry-run`/`--apply` + inventario before/after.
10. **Activation: prueba conductual**, no "SQL byte-idéntico".
11. **D1 sin DROP:** Fase 4 no retira constraints; colisión `bundle_fingerprint` cross-proyecto falla cerrado.

### D1 (confirmada)

Fase 4 **no** hace `DROP CONSTRAINT`. Colisión legacy cross-proyecto → error de
dominio `CrossProjectLegacyFingerprintCollision`, fail-closed. El retiro de la
unicidad global de `chunk_bundles` será migración separada con backup y aprobación.

---

## Bloque A — Dominio (identidad, lifecycle, invariantes) ✅

- [x] **`physical_node_id(project_id, source_chunk_bundle_id, source_chunk_id)`**
  función pura (sha256 canónico field-fenced `\x1f`, prefijo `pnode_`), fail-closed
  si algún componente vacío.
  - Evidencia: `app/back/src/rag_platform/domain/identity.py:38-66`.
- [x] **`PhysicalNode`** separa identidad física (`node_id`/`parent_node_id`) de
  evidencia débil (`source_chunk_id`/`source_parent_chunk_id`).
  - Evidencia: `app/back/src/rag_platform/domain/models.py` (`PhysicalNode`).
- [x] **`EmbeddingBundle` identidad basada en proyecto** (sin `corpus_version` en
  identidad física); `project_id` nullable, legacy conserva id con `corpus_version`.
  - Evidencia: `app/back/src/embedding/domain/models.py:442-448`.
- [x] **`MaterializationStatus` + `IndexingMaterialization`** lifecycle `WRITING →
  SEALED | FAILED`; sellada inmutable.
  - Evidencia: `app/back/src/rag_platform/domain/models.py:620-686`.
- [x] **Invariantes:** `ensure_materialization_sealed_is_immutable`,
  `validate_materialization_counts` (vector_count == child_node_count),
  `validate_materialization_ownership`. Errores nuevos en `errors.py`:
  `MaterializationSealed`, `CrossProjectLegacyFingerprintCollision`, `NodeProjectMismatch`.
  - Evidencia: `app/back/src/rag_platform/domain/models.py:711-775`, `domain/errors.py`.
- **Test:** `test_node_identity_isolation.py` (namespace por proyecto, parent
  expansion físico, dos proyectos mismo chunk no colisionan).

## Bloque B — Puertos / aplicación ✅

- [x] **`SealedEmbeddingStore` (Protocol)** — `stage_and_seal`/`verify_checksum`, nunca `replace`.
  - Evidencia: `app/back/src/rag_platform/application/vector_materialization.py:37-62`.
- [x] **`IndexingMaterializationRepository` (Protocol)** — `find_sealed`/`begin_writing`/`seal`/`mark_failed`, sin upsert sobre sellada.
  - Evidencia: `vector_materialization.py:65-103`.
- [x] **`MaterializeVectorsUseCase`** — fail-closed: reuse idempotente por checksum →
  `WRITING` → valida owner/dimensión/métrica/conteos → `FAILED` con `failure_code` o `SEALED`.
  - Evidencia: `vector_materialization.py:106-194`.
- [x] **`ChunkBundleRef.project_id`** propagado hacia embedding (nullable legacy).
  - Evidencia: `app/back/src/embedding/domain/models.py:442-448`; mappers en
    `embedding/infrastructure/postgres/repositories.py`.
- [x] **`find_reusable_embedding_bundle`** (cierra deuda Fase 3-b) por identidad
  física scoped por `project_id`, revalida dimensión/métrica, no cruza proyecto.
  - Evidencia: `app/back/src/rag_platform/application/artifact_reuse_service.py`.
- **Desviación deliberada (§B-5):** el escritor scoped de nodos vive en la lane
  indexing (`IndexingNodeWriter.replace_scoped_nodes`), no en un puerto duplicado
  de rag_platform, para no mapear dos veces el mismo row.
  - Evidencia: `vector_materialization.py:28-34` (comentario justifica).
- **Test:** `test_vector_lane_isolation.py` (9 casos), `test_embedding_reuse_isolation.py`.

## Bloque C — Adaptadores ✅

- [x] **`SealedEmbeddingStore` (filesystem)** — bajo `embeddings/{embedding_bundle_id}/`
  con `manifest.json` + vectores JSONL + `checksums.json`, escritura atómica reusando
  `core.atomic_fs`, nunca `replace`.
  - Evidencia: `app/back/src/rag_platform/infrastructure/storage/sealed_embedding_store.py:27,47,53-165`.
  - Decisión JSONL (no `.npy`): documentada en docstring (ADR-007 §4), parity con `SealedChunkStore`.
- [x] **`PostgresIndexingMaterializationRepository`** — lifecycle sobre
  `indexing_materializations`; `ON CONFLICT ... WHERE status <> sealed` bloquea reabrir sellada.
  - Evidencia: `app/back/src/rag_platform/infrastructure/postgres/vector_repositories.py:59-228`.
- [x] **Repos reuse por identidad física** scoped por `project_id`; traducen
  `UniqueViolation` del fingerprint global → `CrossProjectLegacyFingerprintCollision`.
  - Evidencia: `vector_repositories.py:12`, `artifact_repositories.py`.
- [x] **Namespacing gated** en lane bundle-first: `replace_scoped_nodes` +
  `project_id` en vectores (`idx_vec_*`), path legacy conserva `None` (byte-idéntico).
  - Evidencia: `app/back/src/indexing/application/bundle_first/index_bundle.py:431-433`,
    `indexing/infrastructure/postgres/bundle_first.py`, `indexing/domain/bundle_first.py`.
- **Test:** `test_sealed_embedding_store.py`, `test_vector_repository_contract.py`.

## Bloque D — DDL aditivo (migraciones) ✅ · aplicadas

- [x] **`20260810_05_release_aware_runs_and_namespaced_nodes.sql`:**
  `chunk_bundles UNIQUE(project_id, chunk_bundle_id)`; `embedding_bundles +project_id`,
  `UNIQUE(project_id, embedding_bundle_id)`, índice parcial físico `WHERE project_id
  IS NOT NULL`, FK compuesto `NOT VALID`; `indexing_nodes +project_id/source_chunk_id/
  source_parent_chunk_id`, `UNIQUE(project_id, node_id)` no parcial (destino FK), FK
  compuesto; `embedding_runs/indexing_runs +project_id/rag_variant_id/rag_release_id`
  nullable sin FK; tabla nueva `indexing_materializations` (lifecycle CHECK, unique
  compuesto, FK).
  - Evidencia: `migrations/20260810_05_...sql:1-152`.
- [x] **`20260810_06_extend_idx_vec_project_ownership.sql`:** 7 `idx_vec_*` ganan
  `project_id` + índice + **2 FKs compuestos** (embedding_bundles + indexing_nodes),
  conservan `UNIQUE(embedding_bundle_id, node_id)`; `rag_release_id` no vive en la fila vectorial.
  - Evidencia: `migrations/20260810_06_...sql:1-58`.
- [x] Idempotencia: `ADD COLUMN IF NOT EXISTS`, constraints guardados por
  `pg_constraint`, FKs `NOT VALID`. `MATCH SIMPLE` + `project_id NULL` ⇒ legacy bypassea FK compuesto.
- **Migraciones `01–07` aplicadas en BD** (confirmado usuario 2026-08-12). FKs
  compuestas/índices efectivos.
- **Test:** `test_embedding_persistence_migrations.py`.

## Bloque E — Código dual-mode / wiring ✅

- [x] **`build_nodes(..., project_id=None)`** ramifica: legacy ⇒ `node_id ==
  chunk_id` byte-idéntico, `source_*=None`; plataforma ⇒ `node_id`/`parent_node_id`
  vía `physical_node_id`, `source_*` como evidencia.
  - Evidencia: `index_bundle.py:109-190`.
- [x] **`execute` ramifica writer:** `replace_document_nodes` (legacy) vs
  `replace_scoped_nodes` (plataforma), propaga `project_id` desde `chunk_bundle.project_id`.
  - Evidencia: `index_bundle.py:377-433`; vectores en `indexing/.../vector_repository.py`.
- [x] Composition root: `api/dependencies.py` ya inyecta `ChunkBundleRepository`,
  `IndexingNodeWriter`, `BundleVectorWriter`; el dual-mode se resuelve server-side
  desde el contexto del bundle, nunca del payload HTTP.
- [x] Default seguro = legacy; ambos caminos con pruebas.
- **Test:** `app/back/tests/indexing/test_platform_dual_mode.py` (3 conductuales),
  `app/back/tests/rag_platform/test_node_identity_isolation.py:107-154`.

## Bloque F — Reset controlado (destructivo) ✅ código · [~] `--apply` pendiente

- [x] **`scripts/rag_platform/reset_derived_rag_artifacts.py`** con `--dry-run`
  (default)/`--apply`, handshake `--confirm-token` determinista, blocker checks
  (retrieval activo / `is_active`), inventario before/after, borrado FK-safe
  (idx_vec → runs → nodes → readiness → bundle_chunks → embedding_bundles →
  chunk_bundles), contención de rutas (solo derivados; preserva raw/normalized).
  - Evidencia: `reset_derived_rag_artifacts.py` (`DELETE_TABLES_IN_ORDER:31-40`,
    `derived_paths:59-73`, `build_confirmation_token:88`, `collect_blockers:114-150`,
    `apply_reset:215-256`, `_assert_within_repo:180-186`, handshake `main:276-293`).
- [x] Reusa `inventory_baseline.collect_inventory`; emite `inventory-before`/`inventory-after-reset`.
- **Test:** `test_reset_derived_rag_artifacts.py` (8 casos: blockers, dry-run plan,
  fail-closed, orden borrado, preserva raw/normalized, inventory-after, ruta fuera de repo).
- **Dry-run real (2026-08-11):** `status=blocked`, `active_retrieval_profiles=1`,
  `idx_vec_local_bge_m3_v1=288` activas, `confirmation_token=25885742c3edfc5d`;
  `--apply` sin token → `reason=confirmation_token_required`.
- [~] **`--apply` NO ejecutado** (destructivo; requiere confirmación humana + gate).
  El gate sigue **cerrado** por diseño hasta confirmación explícita. → ver Gaps.

## Bloque G — Rebuild limpio (composition root) ✅ contrato · [~] corrida real pendiente

- [x] **`RebuildPlatformArtifactsUseCase`** — dado `PlatformBuildContext` validado
  server-side, encadena indexado bundle-first + materialización sellada propagando
  `project_id`, deja vectores inactivos, falla cerrado si el bundle es de otro
  proyecto o si conteos/dimensión/métrica no cuadran.
  - Evidencia: `app/back/src/rag_platform/application/rebuild_orchestrator.py`
    (`PlatformBuildContext.__post_init__` valida kind; `execute` cablea
    `CreateIndexingRunUseCase` → `IndexingRunExecutor` → `MaterializeVectorsUseCase`;
    `_aggregate_counts` toma conteos reales de `run_documents`).
- [x] **Contexto derivado en servidor, nunca del payload** (ADR-007 §7);
  `rag_variant_id`/`rag_release_id` opcionales (Fase 5), validados por `kind`.
- **Decisión ponytail:** reusa casos de uso existentes (`build_nodes` vía
  `IndexEmbeddingBundleUseCase`, `MaterializeVectorsUseCase`); solo cablea y agrega
  conteos. Sin maquinaria nueva ni DDL.
- **Test:** `test_rebuild_orchestrator.py` (4 casos) — **verde** (108 passed rag_platform).
- [~] **Corrida de rebuild sobre datos reales pendiente:** depende de F `--apply`.
  El orquestador cubre `embedding → nodos → vectores → materialización`. El tramo
  `raw/normalized → chunks → embeddings` lo cubren los casos de uso de
  chunking/embedding existentes; **falta un CLI único de rebuild multi-documento**
  (composición operativa, no contrato). → ver Gaps.

## Bloque H — Validación conductual ✅

- [x] **Activation conductual** (no "SQL byte-idéntico"):
  `test_legacy_activation_still_activates_legacy_bundle`,
  `test_platform_indexing_does_not_activate_vectors`,
  `test_platform_materialization_not_visible_to_legacy_retrieval`.
  - Evidencia: `app/back/tests/indexing/test_platform_dual_mode.py:11-113`.
- [x] **Parent expansion físico:** `test_parent_expansion_uses_physical_parent_node_id`
  (`test_node_identity_isolation.py:80-104`), `test_parent_expansion_returns_parent_with_leaf_evidence`.
- [x] **Aislamiento cross-proyecto** (owner/conteos/checksum): `test_vector_lane_isolation.py` (9 casos).
- [x] **Rebuild end-to-end** (G): `test_rebuild_orchestrator.py` (4 casos) — **verde**.

---

## Cierre pure-platform (ADR-008, 2026-08-12) — en etapas

Con la BD **vacía** (hard reset del usuario), se abandona la coexistencia legacy:
`project_id` pasa a NOT NULL de raw a indexing y se retira la lane legacy. Ver
[ADR-008](../docs/adr/ADR-008-pure-platform-project-ownership-not-null.md), que
supersede ADR-007 §1 (nullable), §2 (dual-mode) y §9/D1 (unicidad global).

- **[x] Stage 1 — DDL de tightening (`migrations/20260810_08_pure_platform_project_not_null.sql`):**
  `project_id NOT NULL` en `chunk_bundles`, `embedding_bundles`, `indexing_nodes`,
  las 7 `idx_vec_*`, `embedding_runs`, `indexing_runs`, `indexing_materializations`;
  `DROP` de la unicidad global `chunk_bundles_bundle_fingerprint_key` reemplazada por
  scoped `UNIQUE(project_id, bundle_fingerprint)`; `VALIDATE` de los FKs compuestos
  que 05/06 dejaron `NOT VALID`; purga defensiva FK-safe de filas `project_id IS NULL`.
  - **Evidencia:** `npm run indexing:prepare-postgres` → `status=prepared`, 28
    migraciones aplicadas (incluye `20260810_08`), `base_tables_present=12/12`,
    `active_profiles=7`, `vector_tables_ready=7`. Aplicado 2026-08-12.
- **[x] Stage 2a — retiro de la rama legacy en la lane bundle-first (indexing):**
  `indexing/application/bundle_first/index_bundle.py`: `build_nodes` y
  `_build_vector_record` exigen `project_id` (sin `= None`); eliminada la rama
  `if project_id is None` (legacy `node_id == chunk_id` + `replace_document_nodes`),
  queda solo el path namespaced `replace_scoped_nodes`; guard fail-closed en
  `execute` si un chunk bundle llega sin `project_id`.
  - Tests reencuadrados a pure-platform: `test_node_identity_isolation.py`
    (`test_build_nodes_exige_project_id_pure_platform`), `test_platform_dual_mode.py`
    (`test_activation_activates_platform_bundle`,
    `test_other_project_indexing_not_visible_to_active_retrieval` — aislamiento
    cross-proyecto sustituye al viejo legacy-vs-plataforma).
  - **Evidencia (corrido por el usuario 2026-08-12):** `pytest app/back/tests/indexing`
    → **100 passed, 6 skipped**; `pytest app/back/tests/rag_platform` → **108 passed**.
- **[x] Stage 2b-i — retirar el método muerto `replace_document_nodes` del puerto
  bundle-first** `IndexingNodeWriter` (`ports.py` + impls `in_memory/bundle_first.py`,
  `postgres/bundle_first.py`) — sin caller tras Stage 2a. **No** se tocó el
  `replace_document_nodes` de la lane legacy document (`node_repository.py`,
  `pipeline_factory.py:824`), que sigue viva. `py_compile` OK.
- **Stage 2b-ii — endurecer dominio a `project_id: str` (PARCIAL):**
  - **[x]** `IndexingNodeRecord` (`indexing/domain/bundle_first.py:167`) y
    `AppendOnlyVectorRecord` (`indexing/infrastructure/postgres/vector_repository.py:68`)
    → `project_id` requerido. Seguros: solo se construyen en el path plataforma
    (`build_nodes`/`_build_vector_record`) + 1 test que ya pasa `project_id`.
    `py_compile` OK.
  - **[x] Threading `project_id` en el artefacto de chunk (desbloqueo):** chunking
    escribe `project_id` en `chunking_metadata.json`
    (`chunking/infrastructure/filesystem_chunk_repository.py`, vía `getattr` del repo
    postgres-backed) y el catálogo filesystem lo lee
    (`embedding/infrastructure/filesystem/chunk_bundle_catalog.py`). Aditivo.
  - **[x] `ChunkBundleRef.project_id` → requerido** (`embedding/domain/models.py:453`).
    Fixes: `artifact_repositories._row_to_ref(row, project_id)` (pasa el `project_id`
    del WHERE, sin tocar índices de row); 3 construcciones de test
    (`test_postgres_chunk_bundle_repository`, `test_artifact_reuse`,
    `test_postgres_release_wiring`) + 2 en `test_chunking_orchestrator`. rag_platform
    **114 passed**; embedding/chunking pendientes de tu corrida.
  - **[x] `EmbeddingBundle.project_id` → requerido** (`:346`). `bundle_builder:318` ya
    pasa `project_id` del chunk bundle; read mapper postgres lo trae de
    `_BUNDLE_COLUMNS`. Reencuadrado `test_embedding_domain:139` (legacy→dos proyectos,
    misma identidad). rag_platform **114 passed**; embedding pendiente de tu corrida.
  - **[x] Runs `EmbeddingRun`/`IndexingRun.project_id` → requerido.** Las use cases
    ahora derivan `project_id` del **bundle** (server-side, ADR-007 §7), no del payload:
    `run_service` usa `chunk_bundle.project_id`, `index_bundle` usa `bundle.project_id`.
    `rag_variant_id`/`rag_release_id` siguen nullable (Fase 5). Reencuadrados
    `test_embedding_domain` (`test_run_es_terminal`, `test_run_transporta_contexto_de_release`).
    rag_platform **114 passed**; embedding/indexing pendientes de tu corrida.

**2b-ii COMPLETO:** `ChunkBundleRef`, `EmbeddingBundle`, `IndexingNodeRecord`,
`AppendOnlyVectorRecord`, `EmbeddingRun`, `IndexingRun` — todos `project_id` requerido.
- **[→] Stage 2b-iii — retirar la lane legacy document** (`run_indexing.py` →
  `IndexDocumentUseCase` → `LlamaIndexingPort`), que escribe `project_id NULL` y ahora
  fallaría contra la BD (NOT NULL). Capa grande; sus tests son in-memory y hoy pasan.
  **TRASLADADO AL PLAN MAESTRO (2026-08-13)** como refactor de borrado, no de contrato;
  su prerequisito (CLI de plataforma end-to-end) ya está cumplido.
- **Stage 3 — CLI de rebuild de plataforma** (`chunk→embed→index→materializa` con `project_id`):
  - **[x] Enabler raw→chunk:** `FilesystemBackedPostgresChunkBundleRepository` gana
    `project_id` y lo estampa en el `ChunkBundleRef` que registra en `chunk_bundles`
    (`chunking/infrastructure/postgres_chunk_repository.py`); `build_run_service`/
    `build_run_service_from_env` (`chunking/api/dependencies.py`) propagan `project_id`.
    Aditivo (`str | None = None`), no rompe callers. `py_compile` OK.
  - **[x] Etapa chunk del CLI:** `scripts/rag_platform/rebuild_platform.py --project-id`
    reusa `build_run_service_from_env(project_id=...)` → registra `chunk_bundles` con
    dueño de proyecto. `py_compile` OK. **Falta tu corrida** (chunking tests + run real).
  - **[x] Etapas embed → index → materializa del CLI (2026-08-13):**
    `scripts/rag_platform/rebuild_platform.py` encadena `chunk→embed→index→materializa`:
    resuelve el perfil de embedding de la variante server-side, corre
    `embedding_create_run`+`embedding_executor` (BGE) y `rag_platform_rebuild`
    (`RebuildPlatformArtifactsUseCase`, ya en el composition root), namespaced por proyecto,
    vectores inactivos. El orquestador deriva checksum/dimensión/métrica server-side (firma
    colapsada). Raíces por proyecto vía `ProjectStorageResolver`. Fail-closed:
    `embedding_profile_unresolved`, `postgres_required_for_materialization`. Tests
    `test_rebuild_orchestrator.py` (reencuadrado) + `test_platform_cli_wrappers.py`.
    **Falta solo la corrida con BGE vivo** (operativo, trasladado al maestro).

## Gaps y trabajo pendiente de Fase 4

Todo el **código, contratos y tests A–H están cerrados y verdes**. Lo pendiente es
**operativo** o **diferido explícito**:

| # | Gap | Tipo | Bloqueo / plan |
| --- | --- | --- | --- |
| 1 | **Reset `--apply` no ejecutado** sobre BD/filesystem vivos | Operativo destructivo | Gate cerrado por diseño: requiere DSN + dry-run mostrado + confirmación humana + `--confirm-token`. Blocker actual: `active_retrieval_profiles=1` (`idx_vec_local_bge_m3_v1=288`). |
| 2 | **Rebuild sobre datos reales no corrido** (G) | Operativo | Depende del gap 1. Tras reset, correr rebuild plataforma y emitir `inventory-after-rebuild`. |
| 3 | **CLI único de rebuild multi-documento** (`raw/normalized → chunks → embeddings → nodos → vectores → materialización`) | Extensión menor de composición | `scripts/indexing/run_indexing.py` no inyecta `project_id`. El orquestador cubre desde `embedding`; falta atar el tramo de chunking/embedding bajo un solo entrypoint. No es contrato. |
| 4 | **`project_id` no endurecido a `NOT NULL`** | Diferido (D1) | Mientras la lane legacy coexista. Migración futura. |
| 5 | **Retiro de unicidad global** `chunk_bundles_bundle_fingerprint_key` | Diferido (D1, fuera de Fase 4) | Migración separada con backup probado + aprobación explícita. |
| 6 | **Reconexión consumidor SST** | Diferido (ADR-007 §8) | SST dormido Fase 4–8; se reactiva después. |

## Verificación de cierre

```powershell
npm run test:embedding      # 70 passed (2026-08-12)
npm run test:indexing       # passed (2026-08-12)
npm run python -- -m pytest app/back/tests/rag_platform -q   # 108 passed (2026-08-12)
npm run python -- -m pip check
npm run indexing:validate
# Destructivo, solo con autorización + tras aplicar migraciones (ya aplicadas):
# npm run python -- scripts/rag_platform/reset_derived_rag_artifacts.py            # dry-run
# npm run python -- scripts/rag_platform/reset_derived_rag_artifacts.py --apply --confirm-token <token>
```

## Riesgos

- Reset destructivo sobre BD viva + filesystem → mitigado por dry-run obligatorio,
  guard `is_active`, inventarios before/after, datos dev con respaldo.
- Bifurcación legacy/plataforma en lane compartida → cubierta por pruebas de ambos
  caminos con default legacy.
- Fail-closed en materialización y en colisión de fingerprint global.

## Desviaciones deliberadas del plan original (registradas)

- **Diseño invertido:** original decía "infra → aplicación → dominio"; se ejecutó
  dominio → puertos → adaptadores → composition root (ajuste #3).
- **`IndexingNodeWriter.replace_scoped_nodes` en lane indexing**, no puerto
  duplicado en rag_platform (evita doble mapeo de row).
- **Vectores serializados como `vectors.jsonl`** (no `.npy`) para parity con
  `SealedChunkStore` y reuso de `core.atomic_fs`.
- **Traducción `UniqueViolation` → `CrossProjectLegacyFingerprintCollision`** en el
  repo donde ocurre el insert (`artifact_repositories.py`).

---

## Cierre Fase 4 (2026-08-12) — estado definitivo y qué falta

> Esta sección **supersede** la tabla "Gaps y trabajo pendiente" anterior: tras
> ADR-008 + migración `20260810_08`, los gaps #4 (`project_id` NOT NULL) y #5
> (retiro unicidad global) **ya están hechos**, y #1 (reset `--apply`) quedó moot
> porque el usuario ejecutó un hard reset y la BD arrancó vacía.

### Hecho y verificado (evidencia)

- **Bloques A–H** (dominio, puertos, adaptadores, DDL, dual-mode→pure-platform,
  reset tool, rebuild orchestrator, validación conductual): código + tests verdes.
- **ADR-008 + migración `20260810_08`**: `project_id` NOT NULL en toda la cadena
  derivada; unicidad global `chunk_bundles_bundle_fingerprint_key` dropeada →
  scoped `(project_id, bundle_fingerprint)`; FKs compuestos validados.
- **Stage 2a**: rama legacy retirada de la lane bundle-first (`index_bundle.py`).
- **Stage 2b-i**: método muerto `replace_document_nodes` retirado del puerto bundle-first.
- **Stage 2b-ii COMPLETO**: `ChunkBundleRef`, `EmbeddingBundle`, `IndexingNodeRecord`,
  `AppendOnlyVectorRecord`, `EmbeddingRun`, `IndexingRun` exigen `project_id`.
- **Stage 3 enabler + etapa chunk del CLI**: `project_id` de raw→chunk persistido;
  `scripts/rag_platform/rebuild_platform.py --project-id [--rag-variant-id]`.
- **Wiring raw/normalized por proyecto + provenance de variante**: plan
  `docs/superpowers/plans/2026-08-12-project-raw-normalized-catalog-wiring.md`
  (Tasks 1-7), migraciones `20260812_01/02/03`.
- **Evidencia de suites (2026-08-12):** `rag_platform` 132 · `embedding` 73 ·
  `chunking` 89 · `indexing` 101 · combinado `embedding+chunking+indexing`
  **264 passed, 7 skipped** · `prepare-postgres` = `prepared` (31 migraciones).
- **Gaps colaterales cerrados:** INSERT de `chunk_bundles` ahora persiste `project_id`;
  migración `20260812_02` idempotente (guard `pg_class`).

### Falta para cerrar Fase 4 del todo

1. **Stage 2b-iii — retirar la lane legacy document** (`scripts/indexing/run_indexing.py`
   store legacy + `IndexDocumentUseCase` + `LlamaIndexingPort`/`pipeline_factory.py` +
   `node_repository.py`, ~1600 LOC + ~30 tests in-memory). Escribe `project_id NULL` →
   rota contra la BD NOT NULL; hoy verde solo por tests in-memory. Borrado grande con
   cirugía de tests. **Prerequisito:** que exista el CLI de plataforma end-to-end (abajo)
   para no quedar sin entrypoint de indexing.
2. **Stage 3 embed → index → materializa:**
   - **[x] Cableado del `RebuildPlatformArtifactsUseCase` en el composition root
     (2026-08-12).** `api/dependencies.py`: nuevo campo `PipelineServices.rag_platform_rebuild`
     + helper `_build_rag_platform_rebuild(...)` que, tras el flag `rag_platform_v1` y con
     conexión Postgres, encadena `CreateIndexingRunUseCase` + `IndexingRunExecutor` (reusa
     `index_bundle`/repos ya construidos) + `MaterializeVectorsUseCase(PostgresIndexingMaterializationRepository)`
     con `storage_schema_version="idx-vec-v1"` (default del target). Sin conexión (modo
     memoria) → `None` por diseño (la materialización sella en Postgres).
     - **Cómo se resolvió:** se montó sobre el patrón existente de `rag_platform_build`/
       `_publish` (gated por flag), reusando los casos de uso ya cableados; cero maquinaria
       nueva. `MaterializeVectorsUseCase` solo requería `IndexingMaterializationRepository`.
     - **Evidencia:** `app/back/src/api/dependencies.py` (`PipelineServices.rag_platform_rebuild`,
       `_build_rag_platform_rebuild`); tests `app/back/tests/core/test_pipeline_composition.py`
       (`test_wire_rag_platform_rebuild_con_conexion_devuelve_orquestador`,
       `..._sin_conexion_es_none`, + aserciones flag on/off). Suites `core` + `rag_platform`
       **158 passed** (2026-08-12).
   - **[ ] Falta:** correr `chunk→embed→index→materializa` end-to-end con **BGE vivo**
     (operativo, datos reales). El wiring de contrato ya está; resta la corrida.
3. **Etapa `normalize` dentro de `run_project_ingestion.py`: CERRADA (2026-08-13).**
   Se cableó el motor real `run_pipeline` raw→`data/projects/{slug}/normalized` por proyecto
   con `platform_context_resolver` (sidecar con `platform_identity`/`platform_provenance`),
   fail-closed sin perfil resoluble. Evidencia: `scripts/rag_platform/run_project_ingestion.py`;
   test `test_project_ingestion_normalize.py`. Con esto **todo el código de la cadena
   `raw→normalize→chunk→embed→index→materializa` existe**.
4. **Corrida operativa end-to-end con BGE vivo** para un proyecto — **trasladada al plan
   maestro**. Bloqueada hoy por falta de proyecto/variante sembrados en BD (no hay CLI de seed).

Los remanentes son **operativos** (item 4: BGE + datos + seed) o **refactor de borrado**
(item 1: Stage 2b-iii), ambos trasladados al plan maestro. **Nada de contrato queda abierto:
A–H, Stage 3 (CLI embed→index→materializa + normalize) y el wiring de catálogos están cerrados.**
