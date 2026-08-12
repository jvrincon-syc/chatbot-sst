# Fase 5 — Exploración: Variantes, DRAFT, membresías y orquestador de release

- **Fecha**: 2026-08-11
- **Tipo**: exploración previa (ponytail) — mapear qué reusar/extender antes de escribir
- **Estado**: borrador de terreno; no implementa, decide el mínimo compatible
- **Alcance**: solo Fase 5 del plan maestro (líneas 490-540)

> Objetivo ponytail: **no reescribir nada**. Fase 5 es *ensamblaje* sobre bloques
> ya construidos en Fases 1-4 (variantes, snapshots, elegibilidad, reuse policy,
> ledger, rebuild orchestrator). Este documento inventaría lo existente, marca qué
> se reusa/extiende y reduce lo "por crear" al mínimo que el plan no cubre ya.

---

## 1. Qué ya existe (reusar tal cual)

| Necesidad Fase 5 | Ya implementado | Ubicación |
| --- | --- | --- |
| Variante inmutable + fingerprint de receta | `RagVariant`, `RagVariantState`, `compute_semantic_recipe_fingerprint` | `rag_platform/domain/models.py:98,261` |
| Corpus snapshot inmutable + manifest hash reconstruible | `CorpusSnapshot`, `CorpusSnapshotDocument`, `compute_corpus_manifest_hash` | `rag_platform/domain/models.py:431-470` |
| Elegibilidad versionada (needs_review, waiver, blocked) | `EligibilityDecision`, `RevisionReviewState` | `rag_platform/domain/models.py:357-380` |
| Servicio de snapshot (crea, valida elegibilidad) | `CorpusSnapshotService` | `rag_platform/application/corpus_snapshot_service.py` |
| Reuse policy en orden normalize→chunk→embed | `ArtifactReusePolicy` (`find_reusable_normalized`/`_chunk_bundle`/`_embedding_bundle`) | `rag_platform/application/artifact_reuse_service.py:102-175` |
| Ledger durable de build (start/complete step, clasifica reuso) | `RagBuildRunRepository`, `RagBuildStep`, `BuildStage`, `BuildOutcome`, `ReuseKind` | `artifact_reuse_service.py:79`, `domain/models.py:510-545` |
| Etapa `index` del planner (embed→nodos→vectores→materialización sellada) | `RebuildPlatformArtifactsUseCase` + `MaterializeVectorsUseCase` | `rag_platform/application/rebuild_orchestrator.py`, `vector_materialization.py` |
| Contexto de build validado server-side (deriva project/variant/release) | `PlatformBuildContext` | `rag_platform/application/rebuild_orchestrator.py` |
| Contrato de identidad de release | `RagBuildContext`, `PlatformId(RAG_RELEASE)` | `rag_platform/domain/identity.py` |
| Aislamiento cross-proyecto (owner) | `ensure_reuse_within_project`, `CrossProjectReuseForbidden` | `domain/models.py`, `domain/errors.py` |
| Runs release-aware (columnas nullable) | `20260810_05` (`project_id/rag_variant_id/rag_release_id`) | `migrations/20260810_05_...sql:99-105` |

**Consecuencia:** de los 3 casos de uso que el plan pide *producir*
(`CreateRagReleaseDraft`, `BuildRagRelease`, `ValidateRagRelease`), ninguno
necesita lógica de pipeline nueva: orquestan puertos existentes.

## 2. Qué falta de verdad (crear, mínimo)

Lo único que Fase 5 introduce como concepto nuevo es la **release** y su lifecycle:

1. **Dominio** (`rag_platform/domain/lifecycle.py` — nuevo):
   - `RagRelease` (id, variante, snapshot, target binding pinneado, `release_number`,
     estado, `release_manifest_hash`, actor/motivo/timestamps).
   - `RagReleaseMembership` (release ↔ revisión ↔ artefactos concretos).
   - `ReleaseState` enum: `DRAFT → VALIDATED → PUBLISHED → RETIRED`, más `FAILED`.
   - `compute_release_manifest_hash(...)` — determinista, espeja
     `compute_corpus_manifest_hash`: hashes de snapshot + recipe + config + artefactos
     + conteos. **Reusa el patrón existente**, no inventa serialización nueva.
   - Guardas de transición (`ensure_transition_allowed`) — funciones puras, como
     `validate_materialization_*`.
   - **ponytail:** `release_number` único por `rag_variant_id`, no global — lo impone
     un índice único parcial en la migración (como `uq_..._physical_identity`), no
     código Python.

2. **Aplicación** (3 servicios, todos orquestan puertos existentes):
   - `CreateRagReleaseDraftUseCase`: valida que snapshot y variante son del mismo
     proyecto (reusa `ensure_reuse_within_project` / comparación de `project_id`),
     resuelve un `target_binding_key` permitido (reusa `ProjectIndexingTargetBinding`
     de `RagProject`), pinnea snapshots, crea `DRAFT`.
   - `BuildRagReleaseUseCase`: **el planner**. Recorre las revisiones del snapshot y,
     por cada una, aplica `ArtifactReusePolicy` en orden normalize→chunk→embed y luego
     `RebuildPlatformArtifactsUseCase` para index; registra cada paso en el ledger
     (`RagBuildRunRepository`) y crea la membresía en el mismo commit lógico.
     **No copia algoritmos**: invoca los servicios existentes por puerto.
   - `ValidateRagReleaseUseCase`: verifica completitud (toda revisión tiene membresía,
     ningún artefacto es de otro proyecto), congela `release_manifest_hash`, pasa a
     `VALIDATED`. Bloquea si alguna revisión es `BLOCKED` sin `operator_waiver`
     (reusa `EligibilityDecision`).

3. **Infra**:
   - `migrations/20260810_07_create_rag_variants_releases_and_memberships.sql`:
     `rag_releases`, `rag_release_memberships`. Aditiva, FKs compuestas por
     `project_id` (mismo patrón Fase 4), índice único parcial de `release_number`
     por variante. **`rag_variants` ya existe** (catálogo Fase 1, `20260810_01`) —
     verificar antes de recrear; el nombre del archivo del plan sugiere crearla pero
     probablemente solo haya que añadir releases/memberships.
   - `rag_platform/infrastructure/postgres/release_repositories.py`: refleja el SQL;
     fake in-memory espejo para tests.

## 3. Desajustes plan↔código detectados (resolver en Fase 5)

- **`rag_variants` en el nombre de la migración `_07`:** el catálogo de variantes ya
  se crea en `20260810_01_create_rag_platform_catalog.sql` (Fase 1). Verificar; si ya
  existe, `_07` solo crea `rag_releases` + `rag_release_memberships` (ajuste mínimo:
  no recrear, no `DROP`).
- **`BuildRagReleaseUseCase` y el rebuild orchestrator (Fase 4):** el orquestador de
  Fase 4 cubre `embed→index→materialización` para **un** bundle. El planner de Fase 5
  lo llama por-revisión y añade las etapas `normalize→chunk` vía `ArtifactReusePolicy`.
  Extensión, no reescritura: el planner es un bucle que compone puertos ya existentes.
- **`FK a rag_releases`:** dos sitios esperan esta tabla:
  - `rag_build_runs.rag_release_id TEXT NOT NULL` (`20260810_04:52`) con comentario
    explícito *"FK a rag_releases se añade en Fase 5 (la tabla no existe todavía)"*.
  - `embedding_runs`/`indexing_runs.rag_release_id` nullable sin FK (`20260810_05:99-105`).
  Fase 5 crea `rag_releases` y **puede** añadir la FK ahora. Recomendación ponytail:
  añadir `FK ... NOT VALID` en `_07` para `rag_build_runs` (cierra el contrato que el
  propio comentario dejó pendiente, una línea); las de runs de embedding/indexing
  quedan opcionales (nullable) hasta que el orquestador las pueble.

## 4. Principios aplicados (buenas prácticas)

- **DRY:** `compute_release_manifest_hash` reusa el patrón de `compute_corpus_manifest_hash`
  y `_sanitize` (sin secretos); el planner reusa `ArtifactReusePolicy` +
  `RebuildPlatformArtifactsUseCase`, no reimplementa reuso ni indexado.
- **SOLID / hexagonal:** los 3 casos de uso dependen de puertos (Protocol), no de
  adaptadores; dominio sin SDK ni SQL. Cada servicio tiene una responsabilidad
  (crear / construir / validar).
- **Fail-closed:** transición inválida, revisión `BLOCKED` sin waiver, o artefacto de
  otro proyecto → error de dominio, nunca degradación silenciosa.
- **Inmutabilidad / determinismo:** release `VALIDATED` no se modifica en sitio
  (un cambio recrea snapshot/membresía); `release_manifest_hash` reconstruible.
- **Separación de semánticas (criterio del usuario):** `VALIDATED` ≠ `PUBLISHED` ≠
  activación legacy. `PUBLISHED` (Fase 6) = el catálogo acepta la release; no toca
  `is_active` ni `retrieval_profiles`.

## 5. Tests a crear (pendientes de ejecución, como Fase 4)

- `test_release_lifecycle.py`: transiciones válidas/ inválidas, actor/motivo/auditoría,
  `manifest_hash` se congela al validar, DRAFT validada no se muta en sitio.
- `test_release_incremental_build.py`: el planner reusa artefactos por identidad exacta
  (exit criteria: `r002` con 56 docs reconstruible; `r001` conserva 55 y no ve el 56).
- `test_release_membership_integrity.py`: release incompleta si falta una revisión;
  rechazo si un artefacto pertenece a otro proyecto; `release_number` único por variante.

Todos con fakes in-memory (sin red ni BD), espejo de los tests de Fases 1-4.

## 6. Orden de trabajo sugerido (dominio → app → infra)

1. `domain/lifecycle.py` (`RagRelease`, `RagReleaseMembership`, `ReleaseState`,
   `compute_release_manifest_hash`, guardas de transición) + test de lifecycle.
2. Puertos + `release_service.py` (`CreateRagReleaseDraft`) + `release_build_service.py`
   (planner) + `release_validator.py` (`ValidateRagRelease`).
3. `migrations/20260810_07_...sql` + `release_repositories.py` (postgres) + fakes.
4. Tests de build incremental e integridad de membresías.

## 7. Riesgos / deuda que hereda de Fase 4

- Migraciones `05/06` sin aplicar en la BD de dev → aplicar antes de correr los
  `postgres_live` de Fase 5.
- Composition root operativo (CLI de rebuild multi-documento) sigue siendo extensión
  menor; el planner de Fase 5 lo cubre a nivel de servicio.
- FK de `rag_release_id` en runs: decidir si se añade en `_07` (recomendado).
