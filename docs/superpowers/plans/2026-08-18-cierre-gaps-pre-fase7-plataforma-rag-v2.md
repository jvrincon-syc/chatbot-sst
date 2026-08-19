# Pre-Phase 7 RAG Platform V2 Gap Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Leave the platform ready for Phase 7 to be a thin HTTP layer over already-closed use cases, read models, and guards, without mixing in Phase 8 work or non-blocking retrieval debt.

**Architecture:** The closure is executed through a gated sequence. `Gate 0` freezes the real baseline first. Then the two correctness bugs that currently violate `fail-closed` are closed (`platform identity` and `runtime chunking recipe`). Next, the typed application surface required by Phase 7 is completed. Finally, the legacy PostgreSQL lane, dynamic vector SQL, and operational observability are hardened. The frontend only receives a minimal and explicit legacy boundary; `platformApi.ts` remains out of scope until real `/api/platform/*` OpenAPI exists.

**Tech Stack:** Python 3.12, FastAPI, Pydantic 2, PostgreSQL + pgvector, React + TypeScript, pytest, and the repository's npm wrappers.

**Specs / repository instructions:**

- `docs/superpowers/plans/Plan_Ajustado_Plataforma_RAG_MultiProyecto(3).md`
- `docs/superpowers/plans/2026-08-11-fase4-embedding-nodos-vectores.md`
- `docs/superpowers/plans/2026-08-12-project-raw-normalized-catalog-wiring.md`
- `docs/backend/gaps-and-debt.md`
- `C:/Users/jvrincon/.codex/attachments/839a3305-7b76-41c0-a03c-acd47b88036b/pasted-text.txt`
- `C:\Users\jvrincon\Documents\chatbot_sst\chatbot-sst\.claude`
- `C:\Users\jvrincon\Documents\chatbot_sst\chatbot-sst\README_REGLAS.md`
- `C:\Users\jvrincon\Documents\chatbot_sst\chatbot-sst\AGENTS.md`
- `C:\Users\jvrincon\Documents\chatbot_sst\chatbot-sst\CLAUDE.md`
- `C:\Users\jvrincon\Documents\chatbot_sst\chatbot-sst\app\back\AGENTS_back.md`

## Global Constraints

- Do not touch `data/docs_raw`; the original source remains immutable.
- Preserve the `fail-closed` policy: if identity, a trusted actor, an allowed binding, a supported recipe, or verifiable ownership is missing, the flow must block.
- Do not accept client-provided SQL, table names, physical `project_id`, `actor_id`, or absolute paths as authority.
- PostgreSQL remains the source of truth; Redis is not part of this closure.
- Memory/PostgreSQL equivalence for every touched port must be covered by contractual tests.
- Phase 7 must not require SQL in routers, fingerprint calculation in handlers, or imports of concrete repositories.
- `platformApi.ts`, `platformTypes.ts`, general file-size refactors, and dedup/boilerplate/hybrid retrieval remain outside this closure.
- Verification commands in this plan are for the operator/implementer. Do not mark the closure ready without real evidence from those runs.
- Automatic commit or push is prohibited.
- The agent is prohibited from running `npm run python ...` or any other test/build/verification command. The agent prints the exact command, asks the operator to run it, consumes the pasted output, and only then continues.

### Test Execution Policy (Skill Override)

Repository/user policy **overrides any skill instruction** that would execute tests, including `superpowers:subagent-driven-development`, TDD, and `verification-before-completion`.

The agent MAY write or modify tests, but it **MUST** stop at each verification handoff, print the exact command, ask the operator to run it, consume the pasted result, and only then continue.

Every step labeled **"Run tests"** below means **"Operator verification handoff"**, not agent execution.

This prohibition applies equally to:

- `pytest`;
- frontend tests/builds such as `npm --prefix app/front ...`;
- `npm run python -- -m pip check`;
- `scripts/rag_platform/check_pre_phase7_health.py`;
- any equivalent verification command.

---

## Gate 0

Do not start any task until the baseline is frozen in:

`docs/runbooks/pre-phase7-readiness.md`

**Gate 0 creates this runbook.** This is why Task 6 lists it as `Modify`, not `Create`.

| Gate | Required evidence |
| --- | --- |
| Commit | `git rev-parse HEAD` for the exact tree to be modified |
| Worktree | inventory of `git status --short` without assuming a clean tree |
| Migrations | diff between repository `migrations/` and the real PostgreSQL schema |
| Feature flags | effective values for `SST_FEATURE_RAG_PLATFORM_V1` and related flags |
| PostgreSQL | version, `pgvector`, effective DSN, expected schema |
| Platform seed | existing projects, profiles, targets, variants, and releases |
| Release/config mapping | `count(*)` for `rag_releases`, configuration-version counts per project, and whether real evidence exists that every pre-existing release maps to a specific configuration version. **If the historical mapping cannot be proven, Gate 0 BLOCKS** and requires an operator decision: dev reset/rebuild (ADR-007) or an evidence-backed data migration. Reconstructing history with `max(version)` is prohibited. |
| Bindings inbound FK | confirm whether any table has an FK to `project_indexing_target_bindings`; this determines whether Task 3 can safely use delete + reinsert |
| Binding/config historical mapping | The current schema has **unversioned** bindings (`PK(project_id, binding_key)`, no `configuration_version`), so historical binding versions cannot be proven from the schema alone. Fail-closed rules: (a) exactly **1** `project_configuration_versions` row for a project → deterministically map the binding to that version; (b) **N versions + historical binding evidence** → backfill using that evidence; (c) **N versions without evidence** → Gate 0 **BLOCKS** and requires dev reset/rebuild or an evidence-backed migration. **Never copy the current binding to every historical version.** |
| Test policy | operator handoff policy from "Test Execution Policy"; do not create undeclared ad-hoc verification scripts |
| Data policy | explicit confirmation that `docs_raw` will not be touched |
| Git policy | no automatic commit and no push |

## Scope

This plan DOES close:

- identity fail-closed before normalize/promote;
- runtime chunking recipe resolution for v1/v2 without silent downgrade;
- the application surface and read models required by Phase 7;
- pinning `configuration_version` in `rag_releases` before exposing configuration PATCH;
- real `has_documents()` behavior, target-binding version semantics, and formal release retirement;
- a trusted actor boundary so the router does not invent authorization;
- quarantine of the unsafe legacy document → PostgreSQL lane;
- vector SQL hardening with catalog authority + `psycopg2.sql.Identifier`;
- a pre-Phase 7 health checker;
- a minimal legacy frontend boundary + synchronized canonical documentation.

## Deferred Work

The following stays explicitly outside the pre-Phase 7 closure:

- general refactoring of `dependencies.py`, `rebuild_platform.py`, `run_project_ingestion.py`, or `release_build_resolver.py` only because of file size;
- `app/front/src/features/platform/platformApi.ts`;
- `app/front/src/features/platform/platformTypes.ts`;
- dedup diversity;
- boilerplate policy;
- vector + lexical hybrid retrieval;
- any work whose objective is "zero known debt" rather than contractual Phase 7 readiness.

## Readiness Definition of Done

Do not start Phase 7 until all four statements are true:

1. **Correctness:** no platform normalize flow can produce or promote a document without `project_id`, `source_document_revision_id`, `processing_profile_id`, and `processing_profile_fingerprint`; no chunking recipe can silently degrade to v1.
2. **Application readiness:** every planned Phase 7 endpoint has a defined port/use case/read model behind it; the router does not need SQL, fingerprints, or business rules; every `DRAFT` release pins `configuration_version` before `build/validate`. **All** consumers of `CreateRagVariantRequest` (matrix-cell wrapper, `seed_project.py`, `test_seed_project.py`, `test_recipe_identity.py`) pass an **explicit** `configuration_version`; no caller receives an implicit default or re-resolves the current version. The signature changes to `CreateRagVariantRequest` and `TargetBindingResolver.find_binding()` (affecting recipe/release-draft/release-build) are implemented as **one atomic change** with all consumers, not as an isolated edit to `context.py`.
3. **Security and integrity:** the actor comes from a trusted server-side boundary; the unsafe legacy PostgreSQL lane is blocked; dynamic vector SQL uses trusted catalog authority + `Identifier` with no direct interpolation of dynamic identifiers in DML/DDL; the health check is clean.
4. **Compatibility:** the legacy HTTP surface still works; the UI explicitly identifies itself as legacy; Phase 8 has not invented frontend platform contracts early.

## Task Map

- **Task 1:** Atomic platform identity preflight before normalization
- **Task 2:** Runtime chunking recipe resolver without silent downgrade
- **Task 3:** Typed Phase 7 service surface plus project/configuration contracts
- **Task 4:** Variant/release/snapshot contracts plus pinned configuration and trusted `PlatformActor` boundary
- **Task 5:** Quarantine unsafe legacy PostgreSQL document lane
- **Task 6:** Harden vector SQL and add pre-Phase 7 health checker
- **Task 7:** Minimal legacy UI boundary plus canonical docs sync

## Cierre del plan (2026-08-19)

**PLAN CERRADO — checklist 100% consumido, sin gap funcional.** Todas las casillas
`- [x]`. Las únicas que quedaban `- [ ]` eran de dos clases, ahora cerradas como
**N/A**: `Step 5 (Commit)` (prohibido por política commit/push) y `Step 2 (snapshot
rojo previo)` (renunciado conscientemente: implementación directa verificada en verde
por el operador en Step 4). No representan trabajo funcional pendiente.

Gates finales relanzados por el operador (2026-08-19) en verde con evidencia fresca:
- Backend pytest: 10 / 22 / 30 / 45 / 30 passed.
- Health check pre-Fase 7: `status=passed` (materializations/orphans/ownership/
  project_mismatches/releases/runs/vectors todas vacías).
- `pip check`: `No broken requirements found`.
- Frontend `test` (incl. `test:components` 12 passed) y `build` (vite v5.4.21) en verde
  con permisos escalados (en sandbox fallan por `spawn EPERM` de esbuild/vite).
- `git status --short`: limpio tras la verificación.

Cumple la **Readiness Definition of Done**. Listo para Fase 7.

## Progreso de ejecución (2026-08-18)

**Gate 0:** PASS — `docs/runbooks/pre-phase7-readiness.md` (PG 18.6, pgvector 0.8.5,
esquema en head, seed 1-versión determinista). Reset/rebuild dev ADR-007 aplicado.

**Task 1 — COMPLETA (32 passed, Gate 1):**
- [x] Step 1 (tests fallidos): `app/back/tests/rag_platform/test_project_ingestion_normalize.py`
  (preflight fail-closed), `app/back/tests/ingestion/test_platform_metadata_in_pipeline.py`,
  `app/back/tests/rag_platform/test_platform_cli_wrappers.py`.
- [x] Step 3 (impl mínima): `ingestion/application/platform_metadata.py::resolve_platform_contexts_or_raise`
  + `PlatformContextResolutionError`; `ingestion/pipeline.py::run_pipeline(platform_context_resolver=...)`;
  `scripts/rag_platform/run_project_ingestion.py` preflight + reason `platform_identity_incomplete`
  (seam `_connect`, `_select_records`).
- [x] Step 4 (verde): 32 passed (corrida combinada Gate 1, operador).
- [x] Step 5 (Commit): **N/A por política** (prohibido commit/push); casilla cerrada como no-aplicable.

**Task 2 — COMPLETA (en los 32 passed):**
- [x] Step 1: `test_release_build_resolver.py`, `test_seed_project.py` (incl.
  `test_compute_chunking_profile_fingerprint_v1_matches_legacy_seed`).
- [x] Step 3: `rag_platform/infrastructure/runtime_chunking_profiles.py::RuntimeChunkingProfileResolver`
  + `UnsupportedRuntimeChunkingRecipe`; helper `rag_platform/domain/models.py::compute_chunking_profile_fingerprint`
  (v1 byte-idéntico); `release_build_resolver.py` (sin colapso a v1); `seed_project.py` (sanitized_config real).
- [x] Step 4 (verde): 32 passed. Desviación: alias `local-structural` conservado en v1.
- [x] Step 5 (Commit): **N/A por política** (prohibido commit/push); casilla cerrada como no-aplicable.

**Task 3 — COMPLETA (14 passed):**
- [x] Step 1: `test_project_queries.py`, `test_project_configuration_versions.py` (in-memory).
- [x] Step 3: migración `migrations/20260818_01_version_project_target_bindings.sql` (idempotente,
  fail-closed, **aplicada** en la BD viva); `postgres/project_repositories.py` (`has_documents` real,
  `_load_configuration` version-aware, `add` con `configuration_version`); `application/services.py`
  + `project_query_service.py` + `project_configuration_service.py`; wiring
  `api/dependencies.py::_build_rag_platform_services` + campo `PipelineServices.rag_platform`.
- [x] Step 4 (verde): 14 passed (operador). Pendiente menor: assertion de composición en
  `test_pipeline_composition.py` (wiring compila; follow-up de bajo riesgo).
- [x] Step 5 (Commit): **N/A por política** (prohibido commit/push); casilla cerrada como no-aplicable.

**Task 4 — IMPLEMENTADA (pendiente verificación del operador):**
- [x] Step 3 (impl): cambio ATÓMICO `find_binding(project_id, configuration_version, binding_key)`
  en todos los consumidores (`context.py`, `recipe_service.py`, `release_service.py`,
  `release_build_service.py`, `PostgresTargetBindingResolver`, `InMemoryTargetBindingResolver`);
  `CreateRagVariantRequest.configuration_version` + consumidores (`seed_project.py`, `test_recipe_identity.py`).
  Servicios nuevos: `variant_query_service.py`, `variant_matrix_service.py` (`platform_id_body`,
  `StaleVariantMatrixCell`), `release_query_service.py`, `release_retirement_service.py`,
  `actor_provider.py`. `RagRelease.configuration_version` (target derivado del binding versionado,
  sin `resolved_indexing_target_id`). `RagPlatformServices` extendido (misma superficie).
  Migraciones idempotentes `20260818_02` (ADD + FK/CHECK NOT VALID) y `20260818_03` (VALIDATE +
  SET NOT NULL). Wiring `dependencies.py`.
- [x] Step 1 (tests escritos): `test_variant_matrix.py`, `test_variant_creation.py`
  (`..._no_duplica_prefijos`), `test_release_queries.py`, `test_release_retirement.py`,
  `test_platform_actor_provider.py`, `test_release_configuration_pinning.py`, + updates de regresión.
- [x] Step 4 (verde, verificado por el operador 2026-08-18): Task 4 nuevos **45 passed**,
  regresión contrato atómico + composición **37 passed** (+ Task 3 14, atomic 12), `pip check` limpio.
  Migraciones `20260818_01/02/03` **aplicadas** (`prepare_postgres_indexing.py` → `status=prepared`,
  34 migraciones, base_tables=12, active_profiles=7, vector_tables_ready=7). Desviación:
  `test_corpus_snapshots.py`/`test_seed_project.py` no requerían cambios; campos legacy `rag_platform_*`
  conservados, superficie nueva bajo `services.rag_platform.*`.
- [x] Step 5 (Commit): **N/A por política** (prohibido commit/push); casilla cerrada como no-aplicable.

## Deuda a cerrar ANTES de Task 5 (hallazgos post-Gate 2)

Registrados para arreglar como paso previo/paralelo a Task 5. No bloquean los verdes de Gate 1-2.

- [x] **[ALTO] Incoherencia in-memory de `services.rag_platform.*` — CERRADO (2026-08-18).**
  `_build_rag_platform_services()` ahora compone una **única** superficie compartida y crea
  `release_draft/build_release/validate_release/publish_release` con los mismos repos que usan
  proyectos/variantes/snapshots/releases en `api/dependencies.py:403-653`. Evidencia del fix:
  `configuration_versions=projects` + `configuration_fingerprints=projects` + repos/memberships/ledger
  compartidos en `dependencies.py:499-512`; wiring unificado de draft/build/validate/publish en
  `dependencies.py:573-612`; aliases legacy apuntando a esas mismas instancias en
  `dependencies.py:393-399`. Soporte in-memory añadido para lectura/pinning real en
  `in_memory/repositories.py:131-161` (`current_configuration_version` +
  `configuration_fingerprint`), `:251-257` (`RagVariantRepository.get`) y `:420-426`
  (`CorpusSnapshotRepository.get`).
- [x] **[MED] DI tipada — CERRADO (2026-08-18).** `PipelineServices.rag_platform: RagPlatformServices | None`
  y `_build_rag_platform_services() -> "RagPlatformServices"`; import bajo `TYPE_CHECKING` (anotación lazy por
  `from __future__ import annotations`, sin costo de import en runtime). `py_compile` OK. Fix inline mínimo.
- [x] **[BAJO] `rag_platform_build/publish/rebuild/draft/validate` = compat debt — CERRADO (2026-08-18).**
  La compat se mantiene sin superficie paralela: `PipelineServices.rag_platform_*` quedó como alias de la
  composición tipada única en `api/dependencies.py:393-399`, y `RagPlatformServices` ahora expone también
  `rebuild_platform` en `app/back/src/rag_platform/application/services.py:87` para contener toda la lane
  administrativa bajo un solo root tipado.

**Task 5 â€” COMPLETA (13 passed, verificado por el operador 2026-08-18):**
- [x] Step 1 (tests escritos): `app/back/tests/indexing/test_run_indexing_cli.py` ahora cubre
  bloqueo temprano por ownership `PLATFORM` real desde sidecar, sidecar faltante y sidecar
  corrupto; los casos PostgreSQL legacy preexistentes reciben sidecar legacy vÃ¡lido para seguir
  cubriendo guards de provider/API key.
- [x] Step 3 (impl): `scripts/indexing/run_indexing.py` clasifica ownership desde
  `MetadataArtifact` (`PLATFORM | LEGACY | UNVERIFIABLE`) y bloquea la lane
  `store="postgres"` antes de `_postgres_indexing_components(...)`, emitiendo
  `legacy_postgres_document_lane_blocked` o `document_ownership_unverifiable` y
  `replacement_command` hacia `scripts/rag_platform/rebuild_platform.py`.
- [x] Evidencia lateral: `app/back/tests/indexing/test_platform_dual_mode.py` documenta que la
  ruta bundle-first pura sigue siendo la lane soportada, y `docs/backend/gaps-and-debt.md`
  registra que el riesgo correctness de escritura insegura por el CLI legacy quedÃ³ mitigado.
- [x] Step 4: handoff del operador verificado en verde (**13 passed**) para
  `app/back/tests/indexing/test_run_indexing_cli.py` +
  `app/back/tests/indexing/test_platform_dual_mode.py`.
- [x] Step 2 (snapshot rojo previo): **N/A / renunciado conscientemente.** El flujo fue
  implementación directa con verificación final del operador en verde (Step 4), sin snapshot
  intermedio del fallo esperado previo al fix. Casilla cerrada como no-aplicable.

**Task 6 â€” COMPLETA (17 passed, verificado por el operador 2026-08-18):**
- [x] Step 1 (tests escritos): nuevos `test_vector_repository_sql_safety.py`,
  `test_pre_phase7_health.py` y `test_rag_platform_migrations.py`; `test_sql.py`
  congelado a `sql.Composed` + tabla calificada/no-calificaciÃ³n de Ã­ndices.
  Ajuste de compatibilidad en `test_vector_repository_contract.py` para el nuevo
  lookup de catÃ¡logo previo a las escrituras bundle-first.
- [x] Step 3 (impl): `vector_repository.py` compone identificadores dinÃ¡micos con
  `psycopg2.sql.Identifier`; lane legacy usa `sql.Identifier(profile.vector_table)`
  y lane bundle-first usa `safe_vector_table_identifier(...)` desde
  `profile_registry.py`, validando `profile.vector_table == target.vector_table`
  antes de DML. `sql.py::create_vector_table_sql(profile, target)` ahora devuelve
  `sql.Composed` con tabla calificada por `indexing_targets` e Ã­ndices no
  calificados. Se crea el checker read-only
  `scripts/rag_platform/check_pre_phase7_health.py`.
- [x] Evidencia lateral: `docs/runbooks/pre-phase7-readiness.md` registra el
  comando/categorÃ­as del health checker pre-Fase 7.
- [x] Step 4: handoff del operador verificado en verde (**17 passed**) para
  `app/back/tests/indexing/infrastructure/postgres/test_vector_repository_sql_safety.py`,
  `app/back/tests/indexing/infrastructure/postgres/test_sql.py`,
  `app/back/tests/rag_platform/test_pre_phase7_health.py` y
  `app/back/tests/rag_platform/test_rag_platform_migrations.py`. El ajuste final
  que cerrÃ³ el rojo intermedio quedÃ³ en
  `app/back/src/indexing/infrastructure/postgres/sql.py` al renderizar la
  dimensiÃ³n del vector sin `sql.Literal(...)`.
- [x] Step 2 (snapshot rojo previo): **N/A / renunciado conscientemente.** El flujo fue
  implementación directa con verificación final del operador en verde (Step 4), sin snapshot
  intermedio del fallo esperado previo al fix. Casilla cerrada como no-aplicable.

**Task 7 â€” COMPLETA (frontend tests + build + gates finales, verificado por el operador 2026-08-18):**
- [x] Step 1 (tests escritos): `app/front/src/dashboardLegacyBoundary.test.mjs` congela el
  etiquetado `Legacy pipeline` para toda la navegaciÃ³n legacy; `app/front/src/dashboardPersistence.test.mjs`
  verifica que el payload persistido siga siendo legacy-only y no incorpore
  `selectedProjectId`, `selectedRagVariantId` ni `selectedRagReleaseId`.
- [x] Step 3 (impl): `app/front/src/features/dashboard/dashboardTypes.ts` etiqueta todas las
  vistas actuales como `Legacy pipeline`; `app/front/src/features/dashboard/DashboardApp.tsx`
  refuerza la frontera visible en el subtÃ­tulo; `app/front/src/features/dashboard/dashboardPersistence.ts`
  expone `writePayloadForTest()` y mantiene la persistencia acotada a
  `activeView`, `selectedDocumentIds` y `embeddingIndexing`.
- [x] Evidencia lateral: `app/front/package.json` incluye el nuevo test en `npm --prefix app/front run test`;
  `docs/api/BUNDLE_FIRST_FRONTEND_HANDOFF.md`, `docs/backend/gaps-and-debt.md` y
  `docs/superpowers/plans/Plan_Ajustado_Plataforma_RAG_MultiProyecto(3).md` dejan explÃ­cita la
  deferencia de `platformApi.ts`/`platformTypes.ts` y de cualquier contrato frontend
  para `/api/platform/*` hasta Fase 8.
- [x] Step 4: handoff del operador verificado en verde para `npm --prefix app/front run test`,
  y ademÃ¡s `npm --prefix app/front run build` quedÃ³ verde dentro de los `Final Verification Gates`.
- [x] Step 2 (snapshot rojo previo): **N/A / renunciado conscientemente.** El flujo fue
  implementación directa con verificación final del operador en verde (Step 4), sin snapshot
  intermedio del fallo esperado previo al fix. Casilla cerrada como no-aplicable.

---

### Task 1: Atomic Platform Identity Preflight Before Normalization

> **GATE 1a — COMPLETADO (2026-08-18).** `resolve_platform_contexts_or_raise` +
> `PlatformContextResolutionError` en `ingestion/application/platform_metadata.py`;
> `run_pipeline(platform_context_resolver=...)` en `ingestion/pipeline.py`; el CLL
> `scripts/rag_platform/run_project_ingestion.py` hace preflight fail-closed y bloquea con
> `platform_identity_incomplete` (exit 2) vía seam `_connect` + `_select_records`. Tests
> reescritos al contrato fail-closed (`test_project_ingestion_normalize.py`), más
> `test_platform_metadata_in_pipeline.py` y `test_platform_cli_wrappers.py`. **Verificado por
> el operador: 32 passed** (corrida combinada Gate 1). Step 5 (Commit) **omitido por
> política** (prohibido commit/push).

- Modify: `app/back/src/ingestion/application/platform_metadata.py`
- Modify: `scripts/rag_platform/run_project_ingestion.py`
- Modify: `app/back/src/ingestion/pipeline.py`
- Modify: `app/back/tests/rag_platform/test_project_ingestion_normalize.py`
- Modify: `app/back/tests/ingestion/test_platform_metadata_in_pipeline.py`
- Create: `app/back/tests/rag_platform/test_platform_cli_wrappers.py`
- Test: `app/back/tests/ingestion/test_pipeline_integration.py`

**Interfaces:**

Consumes:

- `resolve_platform_contexts_or_raise(...)` from `ingestion.application.platform_metadata`;
- `run_pipeline(..., platform_context_resolver=..., only_sources=...)`;
- `RegisterProjectRawArtifactUseCase.execute(...)`.

Produces:

- `PlatformContextResolutionError`;
- `resolve_platform_contexts_or_raise(records: Sequence[InventoryRecord], ...) -> dict[str, PlatformMetadataContext]`;
- CLI blocked reason `platform_identity_incomplete`.

- [x] **Step 1: Write the failing tests**

```python
def test_preflight_fails_when_a_selected_record_has_no_revision() -> None:
    records = [_record("a/manual.pdf"), _record("b/manual.pdf")]
    revisions = {"a/manual.pdf": _revision("a/manual.pdf")}

    with pytest.raises(PlatformContextResolutionError, match="b/manual.pdf"):
        resolve_platform_contexts_or_raise(
            records=records,
            revisions_by_relpath=revisions,
            project_id="proj_demo",
            processing_profile_id="pp_local",
            processing_profile_fingerprint="a" * 64,
            rag_variant_id="ragv_demo",
            semantic_recipe_fingerprint="b" * 64,
        )
```

```python
def test_run_project_ingestion_normalize_blocks_with_exact_reason_and_zero_writes(
    tmp_path: Path,
) -> None:
    result = invoke_cli(
        [
            "--project-id", "proj_demo",
            "--processing-profile-id", "pp_local",
            "--normalize",
            "--json",
        ],
        normalized_root=tmp_path,
    )
    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["reason"] == "platform_identity_incomplete"
    assert list(tmp_path.rglob("*.metadata.json")) == []
    assert _promotion_calls() == []
```

- [x] **Step 2: Operator verification handoff — confirm the tests fail** — **N/A / renunciado conscientemente.** Implementación directa verificada en verde por el operador (Step 4); sin snapshot rojo previo. Comando conservado abajo como referencia; el agente no lo ejecutó.

Command:

```powershell
npm run python -- -m pytest app/back/tests/rag_platform/test_project_ingestion_normalize.py app/back/tests/ingestion/test_platform_metadata_in_pipeline.py app/back/tests/rag_platform/test_platform_cli_wrappers.py -v
```

Expected: FAIL because missing revisions still return `None`, the pipeline still accepts `platform_identity=None`, and the CLI does not yet test the real `--normalize` path or guarantee zero sidecars/promotions.

**The agent MUST NOT execute this command. Stop and ask the operator to run it and paste the output.**

- [x] **Step 3: Write the minimal implementation**

```python
class PlatformContextResolutionError(RuntimeError):
    pass


def resolve_platform_contexts_or_raise(...) -> dict[str, PlatformMetadataContext]:
    resolved: dict[str, PlatformMetadataContext] = {}
    for record in records:
        relpath = canonical_relpath(record.source_relpath)
        revision = revisions_by_relpath.get(relpath)
        if revision is None:
            raise PlatformContextResolutionError(relpath)
        resolved[relpath] = PlatformMetadataContext(...)
    return resolved
```

Apply `only_sources` before the preflight:

```python
selected_records = _apply_only_sources(records, only_sources)
resolved_contexts = resolve_platform_contexts_or_raise(selected_records, ...)
pipeline_summary = run_pipeline(
    ...,
    only_sources=only_sources,
    platform_context_resolver=lambda record: resolved_contexts[
        canonical_relpath(record.source_relpath)
    ],
)
```

Translate preflight failure into a stable CLI reason:

```python
try:
    return main_normalize(...)
except PlatformContextResolutionError as exc:
    return _json_blocked(
        reason="platform_identity_incomplete",
        detail=str(exc),
        exit_code=2,
    )
```

The preflight must occur before reading, writing, or promotion of any selected normalized document.

- [x] **Step 4: Operator verification handoff — confirm the tests pass**

Command:

```powershell
npm run python -- -m pytest app/back/tests/rag_platform/test_project_ingestion_normalize.py app/back/tests/ingestion/test_platform_metadata_in_pipeline.py app/back/tests/rag_platform/test_platform_cli_wrappers.py -v
```

Expected: PASS. One unresolved selected record aborts the whole normalize run after `only_sources` filtering but before reads/writes/promotion, with exact reason `platform_identity_incomplete` and zero sidecars.

**The agent MUST NOT execute this command. Stop and ask the operator to run it and paste the output.**

---

### Task 2: Runtime Chunking Recipe Resolver Without Silent Downgrade

> **GATE 1b — COMPLETADO (2026-08-18).** `RuntimeChunkingProfileResolver` +
> `UnsupportedRuntimeChunkingRecipe` en `rag_platform/infrastructure/runtime_chunking_profiles.py`
> (recetas desconocidas fallan cerrado, ya no degradan a v1; v2 seleccionable). Helper canónico
> `compute_chunking_profile_fingerprint` en `rag_platform/domain/models.py`, compartido por seed y
> resolver; reproduce v1 **byte-idéntico** (sin re-seed). `release_build_resolver.py` usa el resolver;
> `seed_project.py` persiste `sanitized_config` real + idempotencia por receta. Tests:
> `test_release_build_resolver.py`, `test_seed_project.py`, `test_compute_chunking_profile_fingerprint_v1_matches_legacy_seed`.
> **Verificado por el operador: incluido en los 32 passed de Gate 1.** Desviación menor: el resolver
> mantiene el alias `local-structural` en v1 para no romper perfiles ya persistidos. Step 5 (Commit)
> omitido por política.

- Create: `app/back/src/rag_platform/infrastructure/runtime_chunking_profiles.py`
- Modify: `app/back/src/rag_platform/domain/models.py` — canonical `compute_chunking_profile_fingerprint`
- Modify: `app/back/src/rag_platform/domain/errors.py` — `ChunkingProfileSeedConflict` / runtime recipe error as appropriate
- Modify: `app/back/src/rag_platform/infrastructure/release_build_resolver.py`
- Modify: `scripts/rag_platform/seed_project.py`
- Create: `app/back/tests/rag_platform/test_release_build_resolver.py`
- Create: `app/back/tests/rag_platform/test_seed_project.py`
- Test: `app/back/tests/chunking/unit/test_section_context_profile.py`
- Test: `app/back/tests/indexing/test_section_context_nodes.py`

> **Canonical fingerprint formula — required decision before changing seed behavior.**
>
> The repository currently has no `compute_chunking_profile_fingerprint`; the seed path calculates the fingerprint with `_fingerprint("chunking", strategy)` and does **not** include `sanitized_config`.
>
> This task introduces **one canonical domain helper**:
>
> `compute_chunking_profile_fingerprint(*, strategy, sanitized_config)`
>
> in `rag_platform/domain/models.py`, next to `compute_project_configuration_fingerprint`.
>
> The seed path and runtime resolver MUST both use this helper. Neither may independently reimplement the formula.
>
> **v1 preservation:** when `sanitized_config == {}`, the helper must reproduce the current seeded v1 fingerprint. If preserving the existing v1 value is impossible because the new canonical representation serializes differently, Gate 0 must record an explicit dev reseed decision under ADR-007 before implementation. v2 must never be fixed by silently invalidating v1.

> **Immutable recipe identity in the seed path.**
>
> `local-structural-v2` MUST NOT reuse `cp_structural`.
>
> The current seeder separates `--chunking-slug` and `--chunking-strategy` and persists with `ON CONFLICT (chunking_profile_id) DO NOTHING`. This task changes that behavior:
>
> - v1 default → `cp_structural`;
> - v2 default → `cp_structural-v2`;
> - same profile ID + exact same recipe/fingerprint → idempotent success;
> - same profile ID + different strategy/config/fingerprint → `ChunkingProfileSeedConflict`;
> - never silently ignore a different recipe because the ID already exists.
>
> **Critical CLI derivation rule:** change `--chunking-slug` to `default=None`. The effective slug is derived from the selected strategy only when the operator did not explicitly provide a slug:
>
> - `structural` / v1 + no slug → `structural`;
> - `local-structural-v2` + no slug → `structural-v2`;
> - explicit slug → preserve the explicit slug, then apply the recipe-conflict guard.
>
> Do not use `chunking_slug = chunking_slug or "structural-v2"` while the parser still defaults to `"structural"`; that would never derive the v2 slug.

**Interfaces:**

Consumes:

- `ChunkingProfile.strategy`;
- `ChunkingProfile.sanitized_config`;
- `ChunkingProfile.fingerprint`.

Produces:

- `RuntimeChunkingProfileResolver.resolve(profile: ChunkingProfile) -> RuntimeChunkingProfile`;
- fail-closed error `UnsupportedRuntimeChunkingRecipe`;
- fail-closed seed error `ChunkingProfileSeedConflict`.

- [x] **Step 1: Write the failing tests**

```python
def test_resolve_runtime_chunking_profile_v2() -> None:
    platform_profile = _chunking_profile(
        strategy="local-structural-v2",
        sanitized_config={"include_section_context": True},
    )

    runtime = RuntimeChunkingProfileResolver().resolve(platform_profile)

    assert runtime.profile_id == "local-structural-v2"
    assert runtime.include_section_context is True
```

```python
def test_resolve_runtime_chunking_profile_unknown_recipe_fails_closed() -> None:
    platform_profile = _chunking_profile(
        strategy="local-structural-v99",
        sanitized_config={"include_section_context": True},
    )

    with pytest.raises(UnsupportedRuntimeChunkingRecipe):
        RuntimeChunkingProfileResolver().resolve(platform_profile)
```

```python
def test_seed_project_persists_a_selectable_v2_chunking_profile() -> None:
    project = seed_project(
        ...,
        chunking_slug="structural-v2",
        chunking_strategy="local-structural-v2",
    )

    profile = load_chunking_profile(project.chunking_profile_id)

    assert profile.chunking_profile_id.value == "cp_structural-v2"
    assert profile.strategy == "local-structural-v2"
    assert profile.sanitized_config == {"include_section_context": True}
```

```python
def test_seed_v2_does_not_reuse_the_v1_profile_id() -> None:
    seed_project(
        ...,
        chunking_slug="structural",
        chunking_strategy="structural",
    )
    seed_project(
        ...,
        chunking_slug="structural-v2",
        chunking_strategy="local-structural-v2",
    )

    v1 = load_chunking_profile("cp_structural")
    v2 = load_chunking_profile("cp_structural-v2")

    assert v1.strategy == "structural"
    assert v1.sanitized_config == {}
    assert v2.strategy == "local-structural-v2"
    assert v2.sanitized_config == {"include_section_context": True}
```

```python
def test_seed_v2_derives_the_v2_slug_when_slug_is_omitted() -> None:
    seed_project(
        ...,
        chunking_strategy="local-structural-v2",
    )

    profile = load_chunking_profile("cp_structural-v2")

    assert profile.strategy == "local-structural-v2"
    assert profile.sanitized_config == {"include_section_context": True}
```

```python
def test_seed_fails_if_existing_profile_id_has_a_different_recipe() -> None:
    seed_project(
        ...,
        chunking_slug="structural",
        chunking_strategy="structural",
    )

    with pytest.raises(ChunkingProfileSeedConflict):
        seed_project(
            ...,
            chunking_slug="structural",
            chunking_strategy="local-structural-v2",
        )
```

```python
def test_compute_chunking_profile_fingerprint_v1_matches_legacy_seed() -> None:
    legacy = _legacy_seed_chunking_fingerprint(
        strategy="structural"
    )  # `_fingerprint("chunking", strategy)`

    canonical = compute_chunking_profile_fingerprint(
        strategy="structural",
        sanitized_config={},
    )

    assert canonical == legacy
```

- [x] **Step 2: Operator verification handoff — confirm the tests fail** — **N/A / renunciado conscientemente.** Implementación directa verificada en verde por el operador (Step 4); sin snapshot rojo previo. Comando conservado abajo como referencia; el agente no lo ejecutó.

Command:

```powershell
npm run python -- -m pytest app/back/tests/rag_platform/test_release_build_resolver.py app/back/tests/rag_platform/test_seed_project.py app/back/tests/chunking/unit/test_section_context_profile.py app/back/tests/indexing/test_section_context_nodes.py -v
```

Expected: FAIL because release build currently returns `RuntimeChunkingProfile.local_structural_v1()` for every supported strategy, and the real seed path can collide with `cp_structural` + `ON CONFLICT DO NOTHING`, leaving v2 uncreated or silently hidden by the v1 recipe.

**The agent MUST NOT execute this command. Stop and ask the operator to run it and paste the output.**

- [x] **Step 3: Write the minimal implementation**

Canonical runtime resolver:

```python
class RuntimeChunkingProfileResolver:
    def resolve(self, profile: ChunkingProfile) -> RuntimeChunkingProfile:
        expected_fingerprint = compute_chunking_profile_fingerprint(
            strategy=profile.strategy,
            sanitized_config=profile.sanitized_config,
        )
        if profile.fingerprint != expected_fingerprint:
            raise UnsupportedRuntimeChunkingRecipe(profile.strategy)

        key = (
            profile.strategy,
            bool(profile.sanitized_config.get("include_section_context")),
        )

        if key in {
            ("structural", False),
            ("local-structural-v1", False),
            ("local_structural_v1", False),
        }:
            return RuntimeChunkingProfile.local_structural_v1()

        if key in {
            ("local-structural-v2", True),
            ("local_structural_v2", True),
        }:
            return RuntimeChunkingProfile.local_structural_v2()

        raise UnsupportedRuntimeChunkingRecipe(profile.strategy)
```

Change the CLI parser:

```python
parser.add_argument(
    "--chunking-slug",
    default=None,
    help=(
        "Optional chunking profile slug. When omitted, it is derived from "
        "--chunking-strategy: structural -> structural; "
        "local-structural-v2 -> structural-v2."
    ),
)
```

Resolve the effective recipe and slug **before** constructing `chunking_id`:

```python
if args.chunking_strategy == "local-structural-v2":
    sanitized_config = {"include_section_context": True}
    effective_chunking_slug = args.chunking_slug or "structural-v2"
else:
    sanitized_config = {}
    effective_chunking_slug = args.chunking_slug or "structural"

chunking_id = (
    f"{IdentityKind.CHUNKING_PROFILE.value}_{effective_chunking_slug}"
)
```

Use the canonical fingerprint:

```python
fingerprint = compute_chunking_profile_fingerprint(
    strategy=args.chunking_strategy,
    sanitized_config=sanitized_config,
)
```

Replace silent `ON CONFLICT DO NOTHING` semantics with exact-recipe idempotency:

```python
existing = load_chunking_profile_if_present(chunking_id)

if existing is not None:
    if (
        existing.strategy != args.chunking_strategy
        or existing.sanitized_config != sanitized_config
        or existing.fingerprint != fingerprint
    ):
        raise ChunkingProfileSeedConflict(chunking_id)
    # Exact same persisted recipe: idempotent success.
else:
    insert_chunking_profile(
        chunking_profile_id=chunking_id,
        strategy=args.chunking_strategy,
        sanitized_config=sanitized_config,
        fingerprint=fingerprint,
        ...,
    )
```

The release build must use the persisted recipe rather than a strategy allowlist followed by unconditional v1:

```python
def _runtime_chunking_profile(
    self,
    rag_variant_id: PlatformId,
) -> RuntimeChunkingProfile:
    variant = self._variants.get(rag_variant_id)
    platform_profile = self._chunking_profiles.get(
        variant.chunking_profile_id
    )
    return RuntimeChunkingProfileResolver().resolve(platform_profile)
```

- [x] **Step 4: Operator verification handoff — confirm the tests pass**

Command:

```powershell
npm run python -- -m pytest app/back/tests/rag_platform/test_release_build_resolver.py app/back/tests/rag_platform/test_seed_project.py app/back/tests/chunking/unit/test_section_context_profile.py app/back/tests/indexing/test_section_context_nodes.py -v
```

Expected: PASS. v2 is persisted under a distinct immutable `chunking_profile_id`; the seed path derives `cp_structural-v2` when v2 is selected without an explicit slug; the seed path is idempotent only for the exact same recipe; the fingerprint matches the persisted recipe; unknown recipes no longer degrade to v1.

**The agent MUST NOT execute this command. Stop and ask the operator to run it and paste the output.**

Operator evidence (2026-08-18): PASS. `npm --prefix app/front run test` quedÃ³ verde con los
checks nuevos de frontera legacy en `app/front/src/dashboardLegacyBoundary.test.mjs` y el guard de
persistencia legacy-only en `app/front/src/dashboardPersistence.test.mjs`. La implementaciÃ³n
verificada estÃ¡ en `app/front/src/features/dashboard/dashboardTypes.ts`,
`app/front/src/features/dashboard/DashboardApp.tsx`,
`app/front/src/features/dashboard/dashboardPersistence.ts`,
`docs/api/BUNDLE_FIRST_FRONTEND_HANDOFF.md`,
`docs/backend/gaps-and-debt.md` y
`docs/superpowers/plans/Plan_Ajustado_Plataforma_RAG_MultiProyecto(3).md`.

---

### Task 3: Typed Phase 7 Service Surface Plus Project/Configuration Contracts

> **GATE 2a — EN PROGRESO (2026-08-18).**
> - **Migración `20260818_01` APLICADA y verificada en vivo.** Implementada como
>   **idempotente + fail-closed**: bloque `DO $$` con no-op si la columna ya existe (sobrevive
>   al re-apply-all), hard-gate que aborta si algún proyecto con bindings tiene ≠1
>   `configuration_version`, y **backfill determinista EN SITIO (`UPDATE`)** en vez de
>   delete+reinsert (para camino-(a) 1-versión el mapeo es 1:1 → más simple y sin temp-table
>   en plpgsql). Fix: el alias `only` es palabra reservada → renombrado `single_version`.
>   Estado vivo tras aplicar: `project_indexing_target_bindings` PK
>   `(project_id, configuration_version, binding_key)` + FK a `project_configuration_versions`;
>   fila real `('proj_sst-general','primary',1)`.
> - **Repo + servicios COMPLETOS:** `has_documents()` real (query a `project_documents`),
>   `_load_configuration` version-aware (bindings por `configuration_version`), `add` inserta
>   bindings con versión; `RagPlatformServices` (project/config surface), `project_query_service.py`,
>   `project_configuration_service.py` cableados.
> - **Wiring de composición HECHO:** `PipelineServices.rag_platform` + `_build_rag_platform_services`
>   (in-memory sin conexión / Postgres con conexión) en `api/dependencies.py`, tras `rag_platform_v1`.
> - **Tests HECHOS:** `test_project_queries.py` (list/get/update/list-profiles + fail-closed) y
>   `test_project_configuration_versions.py` (vigente/histórica sin colapsar bindings + versión monótona),
>   in-memory. Pendiente menor: assertion de composición `services.rag_platform is not None` en
>   `test_pipeline_composition.py` (el wiring compila; la aserción es follow-up de bajo riesgo).
>
> **Entorno rebuild (ADR-007) — RESUELTO.** El operador autorizó **hard reset dev**: se truncaron
> las 41 tablas de datos (incluida la fila `chunk_bundles` legacy con `project_id` NULL que rompía
> `20260810_08`) y `prepare_postgres_indexing.py` re-aplicó **todas** las migraciones limpio
> (`status=prepared`), restaurando seeds de config y dejando el esquema en head con `20260818_01`.
> El re-apply-all vuelve a funcionar; las migraciones de Task 4 (`_02/_03`) ya no requieren apply
> quirúrgico. Registrado en el runbook de readiness.

**Files:**

- Create: `app/back/src/rag_platform/application/services.py`
- Create: `app/back/src/rag_platform/application/project_query_service.py`
- Create: `app/back/src/rag_platform/application/project_configuration_service.py`
- Modify: `app/back/src/rag_platform/application/context.py`
- Modify: `app/back/src/rag_platform/application/project_service.py`
- Modify: `app/back/src/rag_platform/infrastructure/postgres/project_repositories.py`
- Modify: `app/back/src/rag_platform/infrastructure/in_memory/repositories.py`
- Modify: `app/back/src/api/dependencies.py`
- Create: `migrations/20260818_01_version_project_target_bindings.sql`
- Modify: `app/back/tests/rag_platform/test_projects.py`
- Create: `app/back/tests/rag_platform/test_project_queries.py`
- Create: `app/back/tests/rag_platform/test_project_configuration_versions.py`
- Modify: `app/back/tests/core/test_pipeline_composition.py`

**Interfaces:**

Consumes:

- `CreateProjectUseCase`;
- `ProjectRepository`;
- `PostgresProjectRepository`.

Produces:

- `RagPlatformServices`;
- `PipelineServices.rag_platform: RagPlatformServices | None`;
- `ListProjectsUseCase`;
- `GetProjectUseCase`;
- `UpdateProjectMetadataUseCase`;
- `GetProjectConfigurationUseCase`;
- `GetProjectConfigurationVersionUseCase`;
- `CreateProjectConfigurationVersionUseCase`;
- `ListProcessingProfilesUseCase`;
- `ListChunkingProfilesUseCase`;
- version-aware target-binding reads by `(project_id, configuration_version, binding_key)`.

- [x] **Step 1: Write the failing tests**

```python
def test_postgres_has_documents_queries_project_documents(
    tmp_path: Path,
) -> None:
    repo = PostgresProjectRepository(
        _connection_with_project_document("proj_demo")
    )

    assert repo.has_documents(_pid("proj_demo")) is True
```

```python
def test_pipeline_services_exposes_typed_rag_platform_services() -> None:
    services = build_pipeline_services(...)

    assert services.rag_platform is not None
    assert services.rag_platform.list_projects is not None
    assert services.rag_platform.get_project_configuration is not None
```

```python
def test_get_project_configuration_version_preserves_historical_bindings() -> None:
    config_v1 = GetProjectConfigurationVersionUseCase(...).execute(
        project_id=_pid("proj_demo"),
        version=1,
    )

    assert {
        binding.binding_key
        for binding in config_v1.target_bindings
    } == {"default"}
```

- [x] **Step 2: Operator verification handoff — confirm the tests fail** — **N/A / renunciado conscientemente.** Implementación directa verificada en verde por el operador (Step 4); sin snapshot rojo previo. Comando conservado abajo como referencia; el agente no lo ejecutó.

Command:

```powershell
npm run python -- -m pytest app/back/tests/rag_platform/test_projects.py app/back/tests/rag_platform/test_project_queries.py app/back/tests/rag_platform/test_project_configuration_versions.py app/back/tests/core/test_pipeline_composition.py -v
```

Expected: FAIL because `has_documents()` is hardcoded to `False`; list/update/configuration services do not exist; `PipelineServices` still exposes the split `rag_platform_build/publish/...` surface as `object | None`; historical bindings cannot be read by configuration version.

**The agent MUST NOT execute this command. Stop and ask the operator to run it and paste the output.**

- [x] **Step 3: Write the minimal implementation**

```python
@dataclass(frozen=True)
class RagPlatformServices:
    create_project: CreateProjectUseCase
    get_project: GetProjectUseCase
    list_projects: ListProjectsUseCase
    update_project_metadata: UpdateProjectMetadataUseCase
    get_project_configuration: GetProjectConfigurationUseCase
    get_project_configuration_version: GetProjectConfigurationVersionUseCase
    create_project_configuration_version: CreateProjectConfigurationVersionUseCase
    list_processing_profiles: ListProcessingProfilesUseCase
    list_chunking_profiles: ListChunkingProfilesUseCase
    # Task 4 extends this same container with variants/releases.
    # Do not create a second platform service surface.
```

Migration:

```sql
-- Snapshot BEFORE adding the new column.
CREATE TEMP TABLE _legacy_bindings ON COMMIT DROP AS
SELECT * FROM project_indexing_target_bindings;

ALTER TABLE project_indexing_target_bindings
ADD COLUMN configuration_version INTEGER;

-- Release the old uniqueness first. Otherwise a backfill that needs more than one
-- (project_id, binding_key) would collide with the legacy PK before the new key exists.
ALTER TABLE project_indexing_target_bindings
DROP CONSTRAINT project_indexing_target_bindings_pkey;

-- Fail-closed hard gate:
-- this migration can automatically version ONLY the case where each project that
-- owns bindings has exactly one configuration version.
-- 0 versions = orphan/corruption.
-- >1 versions = historical mapping is required and must be resolved by Gate 0.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM project_indexing_target_bindings b
        LEFT JOIN project_configuration_versions cv
          ON cv.project_id = b.project_id
        GROUP BY b.project_id
        HAVING count(cv.version) <> 1
    ) THEN
        RAISE EXCEPTION
            'historical target binding mapping required before versioning';
    END IF;
END
$$;

-- Fail-closed backfill.
-- The historical version of an unversioned binding is NOT provable from the
-- current schema. Never replicate the current binding across all versions.
DELETE FROM project_indexing_target_bindings;

INSERT INTO project_indexing_target_bindings (
    project_id,
    binding_key,
    indexing_target_id,
    embedding_profile_id,
    configuration_version
)
SELECT
    lb.project_id,
    lb.binding_key,
    lb.indexing_target_id,
    lb.embedding_profile_id,
    v.only_version
FROM _legacy_bindings lb
JOIN (
    SELECT
        project_id,
        min(version) AS only_version
    FROM project_configuration_versions
    GROUP BY project_id
    HAVING count(*) = 1
) v ON v.project_id = lb.project_id;

ALTER TABLE project_indexing_target_bindings
ALTER COLUMN configuration_version SET NOT NULL;

ALTER TABLE project_indexing_target_bindings
ADD CONSTRAINT project_indexing_target_bindings_pkey
PRIMARY KEY (
    project_id,
    configuration_version,
    binding_key
);

ALTER TABLE project_indexing_target_bindings
ADD CONSTRAINT project_indexing_target_bindings_version_fkey
FOREIGN KEY (
    project_id,
    configuration_version
)
REFERENCES project_configuration_versions(
    project_id,
    version
);
```

> **Blocking Gate 0 migration note**
>
> - The migration assumes it runs in a transaction (`ON COMMIT DROP`) and that no table has an inbound FK to `project_indexing_target_bindings`. Confirm both in Gate 0.
> - The `DO $$ ... $$` block is a **hard gate**. If any project with bindings has `configuration_version` count different from exactly 1, the migration aborts before deleting rows.
> - `_01` only handles the deterministically provable one-version case.
> - The multi-version case is resolved **outside** `_01`: Gate 0 BLOCKS, then the operator chooses dev reset/rebuild or an explicitly reviewed, evidence-backed data migration.
> - Replicating the current binding to all versions is prohibited.

Update the port:

```python
def find_binding(
    self,
    project_id: PlatformId,
    configuration_version: int,
    binding_key: str,
) -> ProjectIndexingTargetBinding | None:
    ...
```

- [x] **Step 4: Operator verification handoff — confirm the tests pass**

Command:

```powershell
npm run python -- -m pytest app/back/tests/rag_platform/test_projects.py app/back/tests/rag_platform/test_project_queries.py app/back/tests/rag_platform/test_project_configuration_versions.py app/back/tests/core/test_pipeline_composition.py -v
```

Expected: PASS. Phase 7 has typed project/configuration read/write services under one `services.rag_platform`; target bindings no longer collapse historical configurations into the latest row; release flows can resolve bindings/fingerprints against an exact configuration version.

**The agent MUST NOT execute this command. Stop and ask the operator to run it and paste the output.**

---

### Task 4: Variant/Release/Snapshot Contracts Plus Pinned Configuration and Trusted `PlatformActor` Boundary

**Files:**

- Create: `app/back/src/rag_platform/application/variant_query_service.py`
- Create: `app/back/src/rag_platform/application/variant_matrix_service.py`
- Create: `app/back/src/rag_platform/application/release_query_service.py`
- Create: `app/back/src/rag_platform/application/release_retirement_service.py`
- Create: `app/back/src/rag_platform/application/actor_provider.py`
- Modify: `app/back/src/rag_platform/application/services.py`
- Modify: `app/back/src/rag_platform/application/recipe_service.py`
- Modify: `app/back/src/rag_platform/application/context.py`
- Modify: `app/back/src/rag_platform/application/release_service.py`
- Modify: `app/back/src/rag_platform/application/release_build_service.py`
- Modify: `app/back/src/rag_platform/application/release_validator.py`
- Modify: `app/back/src/rag_platform/domain/lifecycle.py`
- Modify: `app/back/src/rag_platform/infrastructure/postgres/project_repositories.py`
- Modify: `app/back/src/rag_platform/infrastructure/postgres/release_repositories.py`
- Modify: `app/back/src/rag_platform/infrastructure/in_memory/repositories.py`
- Modify: `app/back/src/api/dependencies.py`
- Create: `migrations/20260818_02_pin_release_configuration_version.sql`
- Create: `migrations/20260818_03_enforce_release_configuration_pin.sql`
- Modify: `scripts/rag_platform/seed_project.py`
- Modify: `app/back/tests/rag_platform/test_seed_project.py`
- Modify: `app/back/tests/rag_platform/test_recipe_identity.py`
- Modify: `app/back/tests/rag_platform/test_corpus_snapshots.py`
- Modify: `app/back/tests/rag_platform/test_publication_neutrality.py`
- Modify: `app/back/tests/rag_platform/test_release_lifecycle.py`
- Create: `app/back/tests/rag_platform/test_variant_matrix.py`
- Create: `app/back/tests/rag_platform/test_variant_creation.py`
- Create: `app/back/tests/rag_platform/test_release_queries.py`
- Create: `app/back/tests/rag_platform/test_release_retirement.py`
- Create: `app/back/tests/rag_platform/test_platform_actor_provider.py`
- Create: `app/back/tests/rag_platform/test_release_configuration_pinning.py`
- Modify: `app/back/tests/core/test_pipeline_composition.py`

> The changes to `CreateRagVariantRequest`, `TargetBindingResolver.find_binding()`, the seed path, release draft, release build, and release validation are one atomic contract change. Do not update `context.py` in isolation.

**Interfaces:**

Consumes:

- `CreateRagVariantUseCase`;
- `CreateCorpusSnapshotUseCase`;
- `CreateRagReleaseDraftUseCase`;
- `BuildRagReleaseUseCase`;
- `ValidateRagReleaseUseCase`;
- `PublishRagReleaseUseCase`.

Produces:

- `ListProjectVariantsUseCase`;
- `GetVariantMatrixUseCase` — every cell includes `configuration_version` in its identity;
- `CreateRagVariantFromMatrixCellUseCase`;
- fail-closed error `StaleVariantMatrixCell`;
- `GetReleaseUseCase`;
- `ListProjectReleasesUseCase`;
- `RetireRagReleaseUseCase`;
- `RagRelease.configuration_version`;
- `TrustedPlatformActorProvider`.

- [x] **Step 1: Write the failing tests**

```python
def test_variant_matrix_returns_stable_buildable_and_blocked_reason() -> None:
    cells = GetVariantMatrixUseCase(...).execute(
        project_id=_pid("proj_demo")
    )

    assert cells[0].buildable in {True, False}
    assert hasattr(cells[0], "blocked_reason")
```

```python
def test_create_variant_from_matrix_cell_reconfirms_current_cell() -> None:
    # cell_id = persisted IDs, not strategy:
    # processing_profile_id | chunking_profile_id |
    # embedding_profile_id(str) | binding_key | configuration_version
    #
    # `cp_structural` is the persisted chunking profile ID.
    # Its strategy (`structural`) is stored separately and is not part of cell_id.
    # embedding_profile_id remains a plain str in the current domain.
    variant = CreateRagVariantFromMatrixCellUseCase(...).execute(
        project_id=_pid("proj_demo"),
        cell_id=(
            "pp_local|cp_structural|local-bge-m3-v1|primary|3"
        ),
        variant_slug="sst-local-bge-m3-v2",
        actor=PlatformActor(
            actor_id="op-1",
            project_scope=("proj_demo",),
        ),
    )

    assert variant.embedding_profile_id == "local-bge-m3-v1"
```

```python
def test_create_variant_from_stale_matrix_cell_fails_closed() -> None:
    # Configuration advances to v4 between GET matrix and POST variant.
    _advance_project_configuration(
        project_id="proj_demo",
        to_version=4,
    )

    with pytest.raises(StaleVariantMatrixCell):
        CreateRagVariantFromMatrixCellUseCase(...).execute(
            project_id=_pid("proj_demo"),
            cell_id=(
                "pp_local|cp_structural|local-bge-m3-v1|primary|3"
            ),
            variant_slug="sst-local-bge-m3-v2",
            actor=PlatformActor(
                actor_id="op-1",
                project_scope=("proj_demo",),
            ),
        )
```

```python
def test_create_variant_from_matrix_cell_does_not_duplicate_prefixes() -> None:
    variant = CreateRagVariantFromMatrixCellUseCase(...).execute(
        project_id=_pid("proj_demo"),
        cell_id=(
            "pp_local|cp_structural|local-bge-m3-v1|primary|3"
        ),
        variant_slug="sst-local-bge-m3-v2",
        actor=PlatformActor(
            actor_id="op-1",
            project_scope=("proj_demo",),
        ),
    )

    assert variant.project_id.value == "proj_demo"
    assert variant.processing_profile_id.value == "pp_local"
    assert variant.chunking_profile_id.value == "cp_structural"
    assert variant.embedding_profile_id == "local-bge-m3-v1"
```

```python
def test_retire_release_allows_validated_and_published() -> None:
    retired = RetireRagReleaseUseCase(...).execute(
        rag_release_id=_pid("ragr_demo"),
        actor=PlatformActor(
            actor_id="op-1",
            project_scope=("proj_demo",),
        ),
        reason="deprecated_release",
    )

    assert retired.state is ReleaseState.RETIRED
```

```python
def test_create_release_draft_pins_current_configuration_version() -> None:
    release = CreateRagReleaseDraftUseCase(...).execute(
        rag_variant_id=_pid("ragv_demo"),
        corpus_snapshot_id=_pid("corpus_demo"),
        target_binding_key="default",
        actor_id="op-1",
    )

    assert release.configuration_version == 3
    assert release.target_binding_key == "default"

    # The target is NOT duplicated into the release. It is derived from the
    # immutable versioned binding.
    assert _resolve_binding_target(
        release.project_id,
        release.configuration_version,
        "default",
    ) == "idx_vec_old"
```

```python
def test_build_and_validate_use_the_pinned_configuration_version() -> None:
    # v1 has default -> idx_vec_old.
    release = _draft_release(
        configuration_version=1,
        target_binding_key="default",
    )

    _advance_project_configuration_to_v2(
        binding_target="idx_vec_new"
    )

    BuildRagReleaseUseCase(...).execute(
        rag_release_id=release.rag_release_id,
        actor_id="op-1",
    )
    validated = ValidateRagReleaseUseCase(...).execute(
        rag_release_id=release.rag_release_id,
        actor_id="op-1",
    )

    assert _captured_build_context().indexing_target_id == "idx_vec_old"
    assert (
        validated.release_manifest_hash
        == _manifest_hash_for_configuration_version(1)
    )
```

- [x] **Step 2: Operator verification handoff — confirm the tests fail** — **N/A / renunciado conscientemente.** Implementación directa verificada en verde por el operador (Step 4); sin snapshot rojo previo. Comando conservado abajo como referencia; el agente no lo ejecutó.

Command:

```powershell
npm run python -- -m pytest app/back/tests/rag_platform/test_variant_matrix.py app/back/tests/rag_platform/test_variant_creation.py app/back/tests/rag_platform/test_release_queries.py app/back/tests/rag_platform/test_release_retirement.py app/back/tests/rag_platform/test_platform_actor_provider.py app/back/tests/rag_platform/test_release_lifecycle.py app/back/tests/rag_platform/test_release_configuration_pinning.py app/back/tests/rag_platform/test_publication_neutrality.py app/back/tests/rag_platform/test_corpus_snapshots.py -v
```

Expected: FAIL because variant list/matrix services do not exist; variant creation still accepts free IDs rather than a revalidated matrix cell; release retirement is not implemented; no trusted actor-provider contract is wired for the future router; build still re-resolves `target_binding_key` against current configuration; validate still computes the current configuration fingerprint instead of the pinned one.

**The agent MUST NOT execute this command. Stop and ask the operator to run it and paste the output.**

- [x] **Step 3: Write the minimal implementation**

Final form of the single platform application container:

```python
@dataclass(frozen=True)
class RagPlatformServices:
    # Projects / configuration — Task 3
    create_project: CreateProjectUseCase
    get_project: GetProjectUseCase
    list_projects: ListProjectsUseCase
    update_project_metadata: UpdateProjectMetadataUseCase
    get_project_configuration: GetProjectConfigurationUseCase
    get_project_configuration_version: GetProjectConfigurationVersionUseCase
    create_project_configuration_version: CreateProjectConfigurationVersionUseCase
    list_processing_profiles: ListProcessingProfilesUseCase
    list_chunking_profiles: ListChunkingProfilesUseCase

    # Variants — Task 4
    get_variant_matrix: GetVariantMatrixUseCase
    create_variant_from_matrix_cell: CreateRagVariantFromMatrixCellUseCase
    list_project_variants: ListProjectVariantsUseCase

    # Corpus snapshot — Task 4
    create_corpus_snapshot: CreateCorpusSnapshotUseCase

    # Releases — Task 4
    create_release_draft: CreateRagReleaseDraftUseCase
    get_release: GetReleaseUseCase
    list_project_releases: ListProjectReleasesUseCase
    build_release: BuildRagReleaseUseCase
    validate_release: ValidateRagReleaseUseCase
    publish_release: PublishRagReleaseUseCase
    retire_release: RetireRagReleaseUseCase
```

Trusted actor boundary:

```python
class TrustedPlatformActorProvider(Protocol):
    def current_actor(self) -> PlatformActor:
        ...
```

The application layer must not import FastAPI `Request`. The future HTTP adapter is responsible for implementing this trusted provider from authenticated server-side state.

Pin the configuration in the domain:

```python
class RagRelease(StrictModel):
    ...
    # The only new persisted identity.
    # Do NOT persist resolved_indexing_target_id.
    configuration_version: int = Field(ge=1)
```

Draft creation:

```python
def execute(...):
    configuration = self._project_configurations.get_current(
        variant.project_id
    )

    self._bindings.find_binding(
        project_id=variant.project_id,
        configuration_version=configuration.version,
        binding_key=target_binding_key,
    )

    release = RagRelease(
        ...,
        target_binding_key=target_binding_key,
        configuration_version=configuration.version,
    )
```

Build uses the pinned version:

```python
binding = self._bindings.find_binding(
    project_id=release.project_id,
    configuration_version=release.configuration_version,
    binding_key=release.target_binding_key,
)

context = RagBuildContext(
    ...,
    indexing_target_id=binding.indexing_target_id,
)

configuration_fingerprint = (
    self._configuration_fingerprints.configuration_fingerprint(
        release.project_id,
        release.configuration_version,
    )
)
```

Matrix-cell wrapper:

```python
class CreateRagVariantFromMatrixCellUseCase:
    def execute(
        self,
        *,
        project_id: PlatformId,
        cell_id: str,
        variant_slug: str,
        actor: PlatformActor,
    ) -> RagVariant:
        cell = self._matrix.get_cell(
            project_id=project_id,
            cell_id=cell_id,
        )

        request = CreateRagVariantRequest(
            project_id=platform_id_body(project_id),
            variant_slug=variant_slug,
            processing_profile_id=platform_id_body(
                cell.processing_profile_id
            ),
            chunking_profile_id=platform_id_body(
                cell.chunking_profile_id
            ),
            embedding_profile_id=cell.embedding_profile_id,
            target_binding_key=cell.target_binding_key,
            configuration_version=cell.configuration_version,
        )

        return self._create_variant.execute(
            request,
            actor_id=actor.actor_id,
        )
```

Prefix-safe conversion:

```python
def platform_id_body(identity: PlatformId) -> str:
    prefix = f"{identity.kind.value}_"
    return identity.value.removeprefix(prefix)
```

> **Consequence of the Task 3 `TargetBindingResolver.find_binding()` change**
>
> The method now requires `configuration_version`.
>
> `CreateRagVariantUseCase` must receive the version already confirmed by the matrix cell. It must not query "current configuration" again.
>
> If the request cannot carry that version, the wrapper must place cell revalidation + creation inside the same transactional unit.
>
> The Phase 7 `POST /variants` accepts only `cell_id + variant_slug`, never free processing/chunking/embedding IDs.

Migration `20260818_02_pin_release_configuration_version.sql`:

```sql
ALTER TABLE rag_releases
ADD COLUMN configuration_version INTEGER;

-- NO fabricated backfill.
-- The old system never persisted which configuration_version each historical
-- release used. max(version) would fabricate provenance and point to the latest
-- version, which is exactly the drift this pin is intended to prevent.
--
-- Gate 0 decides what happens to pre-existing releases:
-- dev reset/rebuild under ADR-007, or an evidence-backed data migration.

ALTER TABLE rag_releases
ADD CONSTRAINT rag_releases_versioned_binding_fkey
FOREIGN KEY (
    project_id,
    configuration_version,
    target_binding_key
)
REFERENCES project_indexing_target_bindings(
    project_id,
    configuration_version,
    binding_key
)
NOT VALID;

-- NOT VALID tolerates historical rows but enforces the check for new writes.
ALTER TABLE rag_releases
ADD CONSTRAINT rag_releases_configuration_version_required
CHECK (configuration_version IS NOT NULL)
NOT VALID;
```

Enforcement migration `20260818_03_enforce_release_configuration_pin.sql` runs **only after Gate 0 has resolved historical rows**:

```sql
ALTER TABLE rag_releases
VALIDATE CONSTRAINT rag_releases_configuration_version_required;

ALTER TABLE rag_releases
VALIDATE CONSTRAINT rag_releases_versioned_binding_fkey;

ALTER TABLE rag_releases
ALTER COLUMN configuration_version SET NOT NULL;
```

If legacy rows still have an unproven `configuration_version`, these statements must fail deliberately. Do not fabricate a value just to make the migration pass.

Release retirement:

```python
class RetireRagReleaseUseCase:
    def execute(
        self,
        *,
        rag_release_id: PlatformId,
        actor: PlatformActor,
        reason: str,
    ) -> RagRelease:
        release = self._releases.get(rag_release_id)

        require_project_operator(
            policy=self._access_policy,
            actor=actor,
            project_id=release.project_id,
        )

        ensure_transition_allowed(
            current=release.state,
            target=ReleaseState.RETIRED,
        )

        retired = self._releases.update_state(
            rag_release_id=rag_release_id,
            state=ReleaseState.RETIRED,
            reason=reason,
        )

        emit_release_event(
            ...,
            event="rag_release_retired",
            release=retired,
        )

        return retired
```

- [x] **Step 4: Operator verification handoff — confirm the tests pass**

Command:

```powershell
npm run python -- -m pytest app/back/tests/rag_platform/test_variant_matrix.py app/back/tests/rag_platform/test_variant_creation.py app/back/tests/rag_platform/test_release_queries.py app/back/tests/rag_platform/test_release_retirement.py app/back/tests/rag_platform/test_platform_actor_provider.py app/back/tests/rag_platform/test_release_lifecycle.py app/back/tests/rag_platform/test_release_configuration_pinning.py app/back/tests/rag_platform/test_publication_neutrality.py app/back/tests/rag_platform/test_corpus_snapshots.py -v
```

Expected: PASS. Variants, snapshots, and releases expose the contractual Phase 7 application surface under the same `RagPlatformServices`; `POST variants` revalidates a current cell including its configuration version; every `DRAFT` release pins `configuration_version` and derives the target from the immutable versioned binding; build/validate no longer re-resolve mutable state; the actor boundary remains explicitly server-side without coupling the application layer to FastAPI.

**The agent MUST NOT execute this command. Stop and ask the operator to run it and paste the output.**

---

### Task 5: Quarantine Unsafe Legacy PostgreSQL Document Lane

**Files:**

- Modify: `scripts/indexing/run_indexing.py`
- Modify: `app/back/tests/indexing/test_run_indexing_cli.py`
- Modify: `app/back/tests/indexing/test_platform_dual_mode.py`
- Modify: `docs/backend/gaps-and-debt.md`

**Interfaces:**

Consumes:

- `run_indexing(..., store="postgres")`;
- normalized inventory manifest;
- normalized metadata sidecars `*.metadata.json`.

Produces:

- ownership classification `PLATFORM | LEGACY | UNVERIFIABLE`;
- blocked reason `legacy_postgres_document_lane_blocked` for `PLATFORM`;
- blocked reason `document_ownership_unverifiable` for `UNVERIFIABLE`;
- replacement command pointing to `scripts/rag_platform/rebuild_platform.py`.

- [x] **Step 1: Write the failing tests**

```python
def test_run_indexing_blocks_legacy_postgres_lane_from_real_normalized_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Synthetic DSN: the ownership block must trigger BEFORE connection.
    monkeypatch.setenv(
        "SST_POSTGRES_DSN",
        "postgresql://user:pass@localhost:5432/synthetic",
    )

    normalized_root = _build_platform_normalized_candidate(
        tmp_path,
        project_id="proj_demo",
    )

    summary = run_indexing(
        normalized_root=normalized_root,
        only_sources=[],
        force=False,
        profile_id="local-bge-m3-v1",
        dry_run=False,
        store="postgres",
        ingestion_origin="local",
        persist_confirmed=True,
    )

    assert summary["status"] == "blocked"
    assert (
        summary["reason"]
        == "legacy_postgres_document_lane_blocked"
    )
```

```python
def test_legacy_postgres_blocks_when_metadata_sidecar_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "SST_POSTGRES_DSN",
        "postgresql://user:pass@localhost:5432/synthetic",
    )

    normalized_root = _build_normalized_candidate_without_sidecar(
        tmp_path
    )

    summary = run_indexing(
        normalized_root=normalized_root,
        store="postgres",
        **_defaults(),
    )

    assert summary["status"] == "blocked"
    assert summary["reason"] == "document_ownership_unverifiable"
```

```python
def test_legacy_postgres_blocks_when_metadata_is_invalid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "SST_POSTGRES_DSN",
        "postgresql://user:pass@localhost:5432/synthetic",
    )

    normalized_root = _build_normalized_candidate_with_corrupt_sidecar(
        tmp_path
    )

    summary = run_indexing(
        normalized_root=normalized_root,
        store="postgres",
        **_defaults(),
    )

    assert summary["status"] == "blocked"
    assert summary["reason"] == "document_ownership_unverifiable"
```

- [x] **Step 2: Operator verification handoff — confirm the tests fail** — **N/A / renunciado conscientemente.** Implementación directa verificada en verde por el operador (Step 4); sin snapshot rojo previo. Comando conservado abajo como referencia; el agente no lo ejecutó.

Command:

```powershell
npm run python -- -m pytest app/back/tests/indexing/test_run_indexing_cli.py app/back/tests/indexing/test_platform_dual_mode.py -v
```

Expected: FAIL because the legacy CLI still proceeds into the PostgreSQL document lane, treats a missing/invalid sidecar as "not platform-owned", and a synthetic fixture that puts `platform_identity` into `inventory.json` would not cover the real normalized metadata shape.

**The agent MUST NOT execute this command. Stop and ask the operator to run it and paste the output.**

- [x] **Step 3: Write the minimal implementation**

```python
class Ownership(enum.Enum):
    PLATFORM = "platform"
    LEGACY = "legacy"
    UNVERIFIABLE = "unverifiable"
```

```python
def _classify_documents_ownership(
    normalized_root: Path,
    records: Sequence[dict[str, object]],
) -> Ownership:
    # Fail closed:
    # missing, unreadable, invalid, or structurally unverifiable metadata
    # must never degrade to LEGACY.
    saw_unverifiable = False

    for record in records:
        try:
            paths = ArtifactPaths.for_source(
                str(record.get("source_relpath") or "")
            )
            metadata_path = normalized_root / Path(paths.metadata)

            if not metadata_path.exists():
                saw_unverifiable = True
                continue

            metadata = MetadataArtifact.model_validate_json(
                metadata_path.read_text(encoding="utf-8")
            )
        except (ValueError, OSError):
            saw_unverifiable = True
            continue

        if (
            metadata.platform_identity
            and metadata.platform_identity.project_id
        ):
            return Ownership.PLATFORM

    if saw_unverifiable:
        return Ownership.UNVERIFIABLE

    return Ownership.LEGACY
```

Guard the PostgreSQL lane before opening the database connection:

```python
if store == "postgres":
    ownership = _classify_documents_ownership(
        normalized_root,
        approved,
    )

    if ownership is Ownership.PLATFORM:
        return {
            "status": "blocked",
            "reason": "legacy_postgres_document_lane_blocked",
            "replacement_command": (
                "npm run python -- scripts/rag_platform/rebuild_platform.py "
                "--project-id <proj_...> --rag-variant-id <ragv_...>"
            ),
        }

    if ownership is Ownership.UNVERIFIABLE:
        return {
            "status": "blocked",
            "reason": "document_ownership_unverifiable",
        }

    # Ownership.LEGACY continues through the legacy lane.
```

`PLATFORM` dominates classification. Otherwise, any unverified selected record makes the set `UNVERIFIABLE`.

- [x] **Step 4: Operator verification handoff — confirm the tests pass**

Command:

```powershell
npm run python -- -m pytest app/back/tests/indexing/test_run_indexing_cli.py app/back/tests/indexing/test_platform_dual_mode.py -v
```

Expected: PASS. Memory/test flows remain allowed; PostgreSQL blocking uses the actual ownership signal from normalized metadata sidecars; missing/invalid ownership blocks with `document_ownership_unverifiable` instead of entering the legacy PostgreSQL lane.

**The agent MUST NOT execute this command. Stop and ask the operator to run it and paste the output.**

Operator evidence (2026-08-18): PASS, **13 passed**. The verified implementation is in `scripts/indexing/run_indexing.py`, `app/back/tests/indexing/test_run_indexing_cli.py`, `app/back/tests/indexing/test_platform_dual_mode.py`, and `docs/backend/gaps-and-debt.md`.

---

### Task 6: Harden Vector SQL and Add Pre-Phase 7 Health Checker

**Files:**

- Modify: `app/back/src/indexing/infrastructure/postgres/vector_repository.py`
- Modify: `app/back/src/indexing/infrastructure/postgres/profile_registry.py`
- Modify: `app/back/src/indexing/infrastructure/postgres/sql.py`
- Create: `app/back/tests/indexing/infrastructure/postgres/test_vector_repository_sql_safety.py`
- Modify: `app/back/tests/indexing/infrastructure/postgres/test_sql.py`
- Create: `app/back/tests/rag_platform/test_rag_platform_migrations.py`
- Create: `scripts/rag_platform/check_pre_phase7_health.py`
- Create: `app/back/tests/rag_platform/test_pre_phase7_health.py`
- Modify: `docs/runbooks/pre-phase7-readiness.md`

**Interfaces:**

Consumes:

- `ResolvedIndexingProfile.vector_table`;
- `IndexingTarget.postgres_schema`;
- `IndexingTarget.vector_table`;
- durable `indexing_profiles` catalog;
- durable `indexing_targets` catalog.

Produces:

- `safe_vector_table_identifier(profile_id: str, indexing_target_id: str) -> sql.Identifier`;
- health report categories:
  - `ownership`;
  - `orphans`;
  - `releases`;
  - `runs`;
  - `materializations`;
  - `vectors`;
  - `project_mismatches`;
- migration gate `upgrade_from_liveish_seed_to_head`.

> `docs/runbooks/pre-phase7-readiness.md` was created by Gate 0. Task 6 only updates its health-check section.

- [x] **Step 1: Write the failing tests**

Test the real legacy repository path, not a test-only query builder:

```python
def test_replace_document_vectors_executes_composed_sql_without_fstrings() -> None:
    conn = RecordingConnection()
    repo = PostgresVectorRepository(connection=conn)

    repo.replace_document_vectors(
        document_id="doc-1",
        profile=_resolved_profile(
            vector_table="idx_vec_local_bge_m3_v1"
        ),
        nodes=[...],
        embeddings=[...],
    )

    assert isinstance(conn.executed[0].query, sql.Composed)

    rendered = conn.executed[0].query.as_string(
        _fake_connection()
    )

    assert (
        'DELETE FROM "idx_vec_local_bge_m3_v1"'
        in rendered
    )
```

Freeze the new DDL contract:

```python
def test_create_vector_table_sql_renders_qualified_table_and_unqualified_index() -> None:
    rendered = create_vector_table_sql(
        profile=_resolved_profile(
            vector_table="idx_vec_llama_bge_m3_v1"
        ),
        target=_indexing_target(
            schema="public",
            vector_table="idx_vec_llama_bge_m3_v1",
        ),
    ).as_string(_fake_connection())

    assert (
        'CREATE TABLE IF NOT EXISTS '
        '"public"."idx_vec_llama_bge_m3_v1"'
        in rendered
    )
    assert (
        'CREATE INDEX IF NOT EXISTS '
        '"idx_vec_llama_bge_m3_v1_document_id"'
        in rendered
    )
    assert (
        '"public"."idx_vec_llama_bge_m3_v1_document_id"'
        not in rendered
    )
```

Health checker:

```python
def test_health_checker_blocks_on_orphans_or_mismatches() -> None:
    report = run_pre_phase7_health_checks(
        connection=_connection_with_orphans()
    )

    assert report["status"] == "blocked"
    assert "orphans" in report["checks"]
```

- [x] **Step 2: Operator verification handoff — confirm the tests fail** — **N/A / renunciado conscientemente.** Implementación directa verificada en verde por el operador (Step 4); sin snapshot rojo previo. Comando conservado abajo como referencia; el agente no lo ejecutó.

Command:

```powershell
npm run python -- -m pytest app/back/tests/indexing/infrastructure/postgres/test_vector_repository_sql_safety.py app/back/tests/indexing/infrastructure/postgres/test_sql.py app/back/tests/rag_platform/test_pre_phase7_health.py app/back/tests/rag_platform/test_rag_platform_migrations.py -v
```

Expected: FAIL because table names are still directly interpolated across DELETE/append/activate/count/rollback and DDL helpers; `create_vector_table_sql()` still returns a f-string `str`; no dedicated health checker exists; no upgrade test covers pre-existing target bindings and releases.

**The agent MUST NOT execute this command. Stop and ask the operator to run it and paste the output.**

- [x] **Step 3: Write the minimal implementation**

Change the DDL helper contract:

```python
from psycopg2 import sql


def create_vector_table_sql(
    *,
    profile: ResolvedIndexingProfile,
    target: IndexingTarget,
) -> sql.Composed:
    if target.vector_table != profile.vector_table:
        raise VectorStoreWriteError(
            "indexing target/catalog table mismatch"
        )

    ...
```

The table is schema-qualified from the authoritative target, while the index name is not schema-qualified:

```python
table_identifier = sql.Identifier(
    target.postgres_schema,
    target.vector_table,
)
index_identifier = sql.Identifier(index_name)

query = sql.SQL(
    "CREATE INDEX IF NOT EXISTS {} ON {} (document_id)"
).format(
    index_identifier,
    table_identifier,
)
```

Target-authoritative helper:

```python
def safe_vector_table_identifier(
    profile_id: str,
    indexing_target_id: str,
    registry: PostgresProfileRegistry,
    targets: PostgresIndexingTargetRepository,
) -> sql.Identifier:
    profile = registry.get(profile_id)
    target = targets.get(indexing_target_id)

    if target.vector_table != profile.vector_table:
        raise VectorStoreWriteError(
            "indexing target/catalog table mismatch"
        )

    return sql.Identifier(
        target.postgres_schema,
        target.vector_table,
    )
```

> **Two lanes, different authority rules — do not force the legacy interface to accept an artificial target.**
>
> **Bundle-first / platform lane**
>
> Methods that already receive `indexing_target_id`:
>
> - `append_bundle_vectors`;
> - `activate_bundle`;
> - `count_active_rows`;
> - `rollback_to_bundle`.
>
> They use:
>
> `safe_vector_table_identifier(...)`
>
> and therefore:
>
> `sql.Identifier(target.postgres_schema, target.vector_table)`.
>
> DDL in `sql.py` uses:
>
> - `sql.Identifier(index_name)` for the index name;
> - `sql.Identifier(target.postgres_schema, target.vector_table)` for the target relation.
>
> The index name itself is **not** schema-qualified.
>
> **Legacy replace-document lane**
>
> `replace_document_vectors(*, document_id, profile, nodes, embeddings)` has no `indexing_target_id` in its contract.
>
> Do not add an artificial target parameter only to fit the platform helper.
>
> This lane uses the server-resolved, validated `ResolvedIndexingProfile` and:
>
> `sql.Identifier(profile.vector_table)`.
>
> Never interpolate `profile.vector_table` with f-strings.
>
> The safety test observes the real `cursor.execute()` through `RecordingConnection`; do not create a production query-builder solely for testing.
>
> `ResolvedIndexingProfile.vector_table` is already restricted by the domain validation pattern, and Task 5 prevents platform-owned documents from entering this legacy PostgreSQL lane.
>
> The security DoD is therefore satisfied in both lanes: every dynamic identifier is composed through `Identifier`; the difference is the authority source (qualified target catalog for platform vs validated profile for legacy).

Health checker:

```python
def run_pre_phase7_health_checks(
    connection,
) -> dict[str, object]:
    return {
        "status": "blocked" if failures else "passed",
        "checks": {
            "ownership": ownership_failures,
            "orphans": orphan_failures,
            "releases": release_failures,
            "runs": run_failures,
            "materializations": materialization_failures,
            "vectors": vector_failures,
            "project_mismatches": project_mismatches,
        },
    }
```

The health checker must be read-only. It must not repair, delete, backfill, or mutate rows.

The migration tests must cover both:

- clean-schema upgrade;
- "live-ish" seeded data from before `_01/_02/_03`, including target bindings and releases.

- [x] **Step 4: Operator verification handoff — confirm the tests pass**

Command:

```powershell
npm run python -- -m pytest app/back/tests/indexing/infrastructure/postgres/test_vector_repository_sql_safety.py app/back/tests/indexing/infrastructure/postgres/test_sql.py app/back/tests/rag_platform/test_pre_phase7_health.py app/back/tests/rag_platform/test_rag_platform_migrations.py -v
```

Expected: PASS. Dynamic DML/DDL identifiers are composed from trusted catalog/profile authority; `create_vector_table_sql()` is frozen as `sql.Composed` with target-authoritative qualified tables and non-qualified index names; one health checker exists for pre-Phase 7 readiness; migration tests cover both clean schema and previous data.

**The agent MUST NOT execute this command. Stop and ask the operator to run it and paste the output.**

Operator evidence (2026-08-18): PASS, **17 passed**. The verified implementation is in `app/back/src/indexing/infrastructure/postgres/profile_registry.py` (`safe_vector_table_identifier`), `app/back/src/indexing/infrastructure/postgres/sql.py` (`create_vector_table_sql` returning `sql.Composed`), `app/back/src/indexing/infrastructure/postgres/vector_repository.py` (Identifier-based DML in both lanes), `scripts/rag_platform/check_pre_phase7_health.py` (read-only checker), and `docs/runbooks/pre-phase7-readiness.md` (health-check handoff/runbook).

---

### Task 7: Minimal Legacy UI Boundary Plus Canonical Docs Sync

**Files:**

- Modify: `app/front/src/features/dashboard/DashboardApp.tsx`
- Modify: `app/front/src/features/dashboard/dashboardNavigation.ts`
- Modify: `app/front/src/features/dashboard/dashboardTypes.ts`
- Modify: `app/front/src/features/dashboard/dashboardPersistence.ts`
- Modify: `app/front/src/dashboardPersistence.test.mjs`
- Create: `app/front/src/dashboardLegacyBoundary.test.mjs`
- Modify: `docs/api/BUNDLE_FIRST_FRONTEND_HANDOFF.md`
- Modify: `docs/backend/gaps-and-debt.md`
- Modify: `docs/superpowers/plans/Plan_Ajustado_Plataforma_RAG_MultiProyecto(3).md`

**Interfaces:**

Consumes:

- current dashboard legacy views;
- persisted dashboard state.

Produces:

- explicit `Legacy pipeline` labeling;
- legacy-only storage semantics;
- explicit documentation that `platformApi.ts` and `platformTypes.ts` begin in Phase 8, not before.

- [x] **Step 1: Write the failing tests**

```javascript
test("dashboard labels the current surface as legacy pipeline", () => {
  assert.equal(
    viewTitles.operations.includes("Legacy"),
    true,
  );
});
```

```javascript
test("dashboard persistence continues to store legacy state only", () => {
  const stored = JSON.parse(
    writePayloadForTest(
      createDefaultDashboardPreferences(),
    ),
  );

  assert.equal(
    "selectedProjectId" in stored,
    false,
  );
  assert.equal(
    "selectedRagReleaseId" in stored,
    false,
  );
});
```

- [x] **Step 2: Operator verification handoff — confirm the tests fail** — **N/A / renunciado conscientemente.** Implementación directa verificada en verde por el operador (Step 4); sin snapshot rojo previo. Comando conservado abajo como referencia; el agente no lo ejecutó.

Command:

```powershell
npm --prefix app/front run test
```

Expected: FAIL because the UI still presents the current dashboard as the default surface and the docs do not yet clearly separate pre-Phase 7 work from Phase 8.

**The agent MUST NOT execute this command. Stop and ask the operator to run it and paste the output.**

- [x] **Step 3: Write the minimal implementation**

```ts
export const viewTitles: Record<AppView, string> = {
  operations: "Legacy pipeline - Ingestion operations",
  review: "Legacy pipeline - Document review",
  inventory: "Legacy pipeline - Document inventory",
  chunking: "Legacy pipeline - Local chunking",
  "embedding-indexing": "Legacy pipeline - Embedding and Indexing",
};
```

Documentation:

```md
## Explicitly deferred to Phase 8

- `app/front/src/features/platform/platformApi.ts`
- `app/front/src/features/platform/platformTypes.ts`
- any frontend contract for `/api/platform/*` before real OpenAPI export exists
```

Do not add platform-selection fields to current dashboard persistence during this task.

- [x] **Step 4: Operator verification handoff — confirm the tests pass**

Command:

```powershell
npm --prefix app/front run test
```

Expected: PASS. The current UI remains behaviorally legacy but no longer presents itself as the future platform surface.

**The agent MUST NOT execute this command. Stop and ask the operator to run it and paste the output.**

Operator evidence (2026-08-18): PASS. `npm --prefix app/front run test` quedÃ³ verde con los
checks nuevos de frontera legacy en `app/front/src/dashboardLegacyBoundary.test.mjs` y el guard de
persistencia legacy-only en `app/front/src/dashboardPersistence.test.mjs`. La implementaciÃ³n
verificada estÃ¡ en `app/front/src/features/dashboard/dashboardTypes.ts`,
`app/front/src/features/dashboard/DashboardApp.tsx`,
`app/front/src/features/dashboard/dashboardPersistence.ts`,
`docs/api/BUNDLE_FIRST_FRONTEND_HANDOFF.md`,
`docs/backend/gaps-and-debt.md` y
`docs/superpowers/plans/Plan_Ajustado_Plataforma_RAG_MultiProyecto(3).md`.

---

## Final Verification Gates

Run these gates **only after all tasks have been implemented**.

These commands are operator-owned. The agent MUST print them and request pasted output; it MUST NOT execute them.

```powershell
npm run python -- -m pytest app/back/tests/rag_platform/test_project_ingestion_normalize.py app/back/tests/ingestion/test_platform_metadata_in_pipeline.py app/back/tests/rag_platform/test_platform_cli_wrappers.py -v

npm run python -- -m pytest app/back/tests/rag_platform/test_release_build_resolver.py app/back/tests/rag_platform/test_seed_project.py app/back/tests/chunking/unit/test_section_context_profile.py app/back/tests/indexing/test_section_context_nodes.py -v

npm run python -- -m pytest app/back/tests/rag_platform/test_projects.py app/back/tests/rag_platform/test_project_queries.py app/back/tests/rag_platform/test_project_configuration_versions.py app/back/tests/core/test_pipeline_composition.py -v

npm run python -- -m pytest app/back/tests/rag_platform/test_variant_matrix.py app/back/tests/rag_platform/test_variant_creation.py app/back/tests/rag_platform/test_release_queries.py app/back/tests/rag_platform/test_release_retirement.py app/back/tests/rag_platform/test_platform_actor_provider.py app/back/tests/rag_platform/test_release_lifecycle.py app/back/tests/rag_platform/test_release_configuration_pinning.py app/back/tests/rag_platform/test_publication_neutrality.py app/back/tests/rag_platform/test_corpus_snapshots.py -v

npm run python -- -m pytest app/back/tests/indexing/test_run_indexing_cli.py app/back/tests/indexing/test_platform_dual_mode.py app/back/tests/indexing/infrastructure/postgres/test_vector_repository_sql_safety.py app/back/tests/indexing/infrastructure/postgres/test_sql.py app/back/tests/rag_platform/test_pre_phase7_health.py app/back/tests/rag_platform/test_rag_platform_migrations.py -v

npm run python -- scripts/rag_platform/check_pre_phase7_health.py --json

npm run python -- -m pip check

npm --prefix app/front run test

npm --prefix app/front run build
```

Operator evidence (2026-08-18): PASS. **Todos** los comandos anteriores quedaron verdes en la
validaciÃ³n final del operador, incluyendo:

- las cinco corridas backend de pytest de Tasks 1â€“6;
- `npm run python -- scripts/rag_platform/check_pre_phase7_health.py --json`;
- `npm run python -- -m pip check`;
- `npm --prefix app/front run test`;
- `npm --prefix app/front run build`.

La evidencia de implementaciÃ³n que sustenta esos gates queda registrada en:

- `app/back/src/ingestion/application/platform_metadata.py`,
  `app/back/src/ingestion/pipeline.py`,
  `scripts/rag_platform/run_project_ingestion.py`;
- `app/back/src/rag_platform/infrastructure/runtime_chunking_profiles.py`,
  `app/back/src/rag_platform/domain/models.py`,
  `app/back/src/rag_platform/application/release_build_resolver.py`;
- `app/back/src/rag_platform/application/services.py`,
  `app/back/src/api/dependencies.py`,
  `migrations/20260818_01_version_project_target_bindings.sql`,
  `migrations/20260818_02_pin_release_configuration_version.sql`,
  `migrations/20260818_03_enforce_release_configuration_pin.sql`;
- `app/back/src/indexing/infrastructure/postgres/profile_registry.py`,
  `app/back/src/indexing/infrastructure/postgres/sql.py`,
  `app/back/src/indexing/infrastructure/postgres/vector_repository.py`,
  `scripts/rag_platform/check_pre_phase7_health.py`,
  `docs/runbooks/pre-phase7-readiness.md`;
- `app/front/src/features/dashboard/dashboardTypes.ts`,
  `app/front/src/features/dashboard/DashboardApp.tsx`,
  `app/front/src/features/dashboard/dashboardPersistence.ts`,
  `app/front/src/dashboardLegacyBoundary.test.mjs`,
  `app/front/src/dashboardPersistence.test.mjs`.

## Risks and Mitigations

- **Identity bug masquerading as `needs_review`:** mitigated by Task 1 preflight outside the per-document processing `try`.
- **Silent semantic drift in release build:** mitigated by Task 2 runtime recipe resolution, canonical fingerprinting, immutable v1/v2 profile IDs, and regression tests.
- **Seeder silently hiding a different chunking recipe behind an existing ID:** mitigated by deriving v1/v2 slugs deterministically and failing with `ChunkingProfileSeedConflict` on recipe mismatch.
- **Router becoming the application layer:** mitigated by Tasks 3–4 typed services and read models before any `/api/platform/*` route is created.
- **DRAFT release drifting across project configurations:** mitigated by Task 3 versioned bindings plus Task 4 pinned `configuration_version` in `rag_releases`, with a composite FK to the exact versioned binding. The target is derived from that immutable binding; no duplicated `resolved_indexing_target_id` exists to drift.
- **Unsafe operational fallback:** mitigated by Task 5 quarantine of the legacy PostgreSQL document lane.
- **Unverifiable ownership being treated as legacy:** mitigated by explicit `UNVERIFIABLE` classification and fail-closed blocking.
- **Catalog-trusted table names still being interpolated unsafely:** mitigated by Task 6 `Identifier`-based SQL generation for every dynamic identifier in DML/DDL.
- **Schema-qualified index-name misuse:** mitigated by schema-qualifying only the target relation and leaving the index name unqualified in `CREATE INDEX`.
- **Frontend inventing future contracts too early:** mitigated by Task 7 explicit legacy labeling and Phase 8 deferral.

## Self-Review

### Spec Coverage

The following pre-Phase 7 findings are covered by Tasks 1–7 and Gate 0:

- platform identity fail-closed;
- runtime chunking recipe correctness;
- application-contract readiness;
- real `has_documents()`;
- versioned target bindings;
- pinned release configuration;
- server-side trusted actor boundary;
- vector SQL safety;
- legacy PostgreSQL-lane quarantine;
- operational readiness evidence.

`platformApi.ts`, `platformTypes.ts`, general refactoring, and retrieval-quality debt remain in Deferred Work rather than being disguised as readiness blockers.

### Placeholder Scan

Each task lists:

- concrete file paths;
- concrete tests;
- exact operator verification commands;
- concrete interface names;
- explicit failure reasons.

No `TODO`, `TBD`, "same as Task N", wildcard file paths, or unspecified migration strategy should remain.

### Type Consistency

- The application boundary uses one typed `RagPlatformServices` container.
- The target composition surface is `PipelineServices.rag_platform: RagPlatformServices | None`, not a second parallel surface split by use case.
- Stable proposed errors/reasons remain:
  - `platform_identity_incomplete`;
  - `legacy_postgres_document_lane_blocked`;
  - `document_ownership_unverifiable`;
  - `UnsupportedRuntimeChunkingRecipe`;
  - `ChunkingProfileSeedConflict`;
  - `StaleVariantMatrixCell`.

## Execution Handoff

This plan is the **frozen implementation plan** once saved at:

`docs/superpowers/plans/2026-08-18-cierre-gaps-pre-fase7-plataforma-rag-v2.md`

### First execution step: Gate 0 only

Do **not** start Tasks 1–7 in the first execution session.

The implementing agent must:

1. read the repository instruction files and specs listed at the top of this plan;
2. inspect the real commit, worktree, migrations, feature flags, PostgreSQL schema/catalog state, project seed state, release/configuration history, target-binding history, inbound FKs, data policy, and git policy;
3. create `docs/runbooks/pre-phase7-readiness.md`;
4. report each Gate 0 item as `PASS`, `BLOCKED`, or `NOT PROVEN`, with concrete evidence;
5. if historical release/configuration or binding/configuration mapping is not provable, stop and request the operator's reset/rebuild vs evidence-backed-migration decision;
6. do not execute tests, builds, pip checks, or the health checker;
7. do not modify `data/docs_raw`;
8. do not commit or push;
9. stop after presenting the Gate 0 readiness report.

Only after the operator reviews Gate 0 and explicitly continues should implementation proceed to **Task 1**.

Subsequent tasks are executed one at a time, with the operator verification handoff after each test-writing and implementation checkpoint defined above.
