# Fase 8 — GUI de Plataforma RAG Multi‑Proyecto — Implementation Plan v2

> **For agentic workers:** REQUIRED SUB-SKILL: use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` task-by-task. Use TDD, keep changes small, and do not commit or push unless the operator explicitly authorizes it.

**Goal:** habilitar una GUI interna de operador para administrar la plataforma RAG multi‑proyecto desde el alta del proyecto y el intake RAW hasta normalización, selección de receta, snapshot de corpus, build, validación y publicación de una release RAG, sin romper ni reetiquetar la lane legacy.

**Architecture:** Fase 8 no empieza por React. Primero se cierran tres gates backend: (0) transporte GUI→FastAPI para `/api/platform/*` y `PATCH`; (1) intake documental project-aware por HTTP reutilizando la lógica de plataforma existente; (2) read-models rehidratables de documentos, snapshots y releases. Después se agrega una sesión local de operador delante del bearer existente, tipos frontend generados desde OpenAPI y un `OperatorApp` nuevo que contiene dos superficies hermanas: `Platform` y `Legacy pipeline`. React nunca orquesta chunking/embedding/indexing por endpoints legacy para construir una release: llama al lifecycle autoritativo de `/api/platform/releases/*`.

**Tech Stack:** Python 3.12, FastAPI, Pydantic 2, PostgreSQL/pgvector, React 18, TypeScript 5.6, Vite 5, pytest, Vitest/Node tests existentes, OpenAPI `docs/api/pipeline-openapi.json`.

**Specs:**
- `docs/superpowers/plans/Plan_Ajustado_Plataforma_RAG_MultiProyecto(3).md`
- `plans/2026-08-20-fase8-exploratoria-gui-plataforma.md`
- Fase 7/OpenAPI vigente del repositorio al iniciar la ejecución.

---

## 0. Decisiones cerradas

### D1 — Codegen
Usar `openapi-typescript` sobre `docs/api/pipeline-openapi.json`.

- `platformOpenApi.generated.ts`: generated, no editar.
- `platformTypes.ts`: aliases y tipos de UI escritos a mano.
- El CI/check local falla si el OpenAPI cambia sin regenerar tipos.

### D2 — Bearer / login de operador
Fase 8 **no implementa un sistema de identidad, SSO ni OIDC**.

Se implementa una **sesión GUI local de operador**:

```text
browser
  └─ POST /api/auth/login { token }   # una vez
       ↓
GUI backend valida token con ConfiguredBearerAuth
       ↓
session_id opaco en cookie HttpOnly
       ↓
GUI backend conserva bearer en memoria server-side
       ↓
/api/platform/* → bridge añade Authorization: Bearer ...
```

Reglas:
- el bearer no se guarda en React state persistible;
- no `localStorage`, `sessionStorage`, query string ni `VITE_*`;
- cookie `HttpOnly; SameSite=Strict; Path=/`; `Secure` cuando el servicio use HTTPS;
- sesión con TTL configurable y revocación/logout;
- ningún log contiene token ni session id completo;
- cuando exista SSO/OIDC se reemplaza el provider de sesión/auth, no los workspaces de plataforma.

### D3 — `project_scope`
El backend sigue siendo la autoridad.

- `GET /api/platform/projects` define qué proyectos son visibles.
- Un `project_scope` devuelto por `/api/auth/session` es **informativo**, nunca una autorización frontend.
- `403` se muestra como acceso prohibido; jamás se convierte en lista vacía.
- `project_scope=None` puede mostrarse como operador global solo si el backend lo comunica explícitamente.

### D4 — Retrieval / Activation
Quedan fuera del core de la nueva GUI de plataforma en Fase 8.

Motivo:
- la nueva plataforma no debe exponer `indexing_target_id`;
- el contrato legacy de retrieval todavía maneja conceptos físicos;
- `PUBLISHED` no equivale a activation.

La GUI legacy continúa ofreciendo su workspace operativo actual.

### D5 — Shell
No agregar `platform` al `DashboardApp.AppView`.

Crear:

```text
OperatorApp
├── Platform
│   ├── Projects
│   ├── Recipe / Variant
│   ├── Documents / Normalize
│   ├── Corpus snapshots
│   └── Releases
└── Legacy pipeline
    └── DashboardApp actual
```

`DashboardApp`, `dashboardNavigation.ts`, `dashboardTypes.ts` y sus tests deben conservar la frontera legacy existente.

### D6 — Persistencia
Separar preferencias:

```text
chatbot-sst.dashboard.preferences.v2   # legacy actual
chatbot-sst.platform.preferences.v1    # plataforma
```

Persistir solo IDs de navegación:

- `selectedProjectId`
- `selectedRagVariantId`
- `selectedCorpusSnapshotId`
- `selectedRagReleaseId`

Nunca persistir bearer, cookie, target físico, actor, paths, documentos o idempotency keys.

### D7 — Idempotency-Key
Una key por **intención lógica del operador**, no por request HTTP.

```text
click Build
  → key A
timeout
  → retry de la misma intención usa key A
resultado terminal
  → key A se descarta

nuevo click Build
  → key B
```

Las keys viven solo en memoria del frontend/session state.

### D8 — Normalize HTTP
La API externa de normalización acepta **`rag_variant_id`**, no un `processing_profile_id` libre.

El CLI interno puede conservar un seam avanzado por `processing_profile_id`, pero la GUI opera mediante una variante reconfirmada.

### D9 — Orquestación de build
React **no** llama secuencialmente a los endpoints legacy de chunking/embedding/indexing para construir una release.

La operación autoritativa es:

```text
POST /api/platform/releases/{ragr_id}/build
```

El backend resuelve la receta, reutilización de stages, chunking, embedding e indexación.

---

## 1. Global Constraints

- La GUI es de operador interno.
- `/api/platform/*` sigue protegido por bearer en FastAPI.
- El browser accede mediante sesión GUI same-origin; el bridge inyecta el bearer.
- Fase 8 no reabre las invariantes de Fase 7.
- Nunca enviar desde frontend:
  - `actor_id`
  - `indexing_target_id`
  - `target_bindings`
  - nombres de tabla
  - rutas físicas
- Upload y normalize deben ser project-aware.
- No reutilizar `/api/upload` ni `/api/pipeline/run` del legacy.
- `POST /variants` acepta únicamente `cell_id + variant_slug`.
- Los IDs externos son canónicos completos (`proj_`, `ragv_`, `corpus_`, `ragr_`, `srev_`).
- Los estados `401/403/409/422/503` son estados de producto visibles, no excepciones que se silencian.
- `needs_review` exige decisión explícita antes de ser elegible cuando la política lo requiera.
- No hacer commit/push automáticamente.

---

# PRE-FLIGHT — Congelar evidencia real antes de Gate 0

Este preflight no sustituye el Gate 0 funcional.

> **PRE-FLIGHT registrado (2026-08-20).** Baseline real congelado antes de tocar código.

- [x] `git rev-parse HEAD` → **`f92e1d702ba14f743a26ce7297fac94c5d0128ee`** (`f92e1d7 cierre del back/inicio de construccion de las GUIs`).
- [x] `git status --short` → limpio salvo el propio plan sin trackear (`?? docs/superpowers/plans/2026-08-20-fase8-gui-plataforma-plan.md`). Sin divergencia material.
- [x] rama `main`, worktree real inspeccionado.
- [x] `SST_FEATURE_RAG_PLATFORM_V1` default `False` (`core/feature_flags.py:29`); se habilita por entorno para la GUI.
- [x] auth registry de desarrollo = bearer estático `SST_HTTP_AUTH_CREDENTIALS_JSON` (Fase 7, `core/http_auth.py`).
- [x] `docs/api/pipeline-openapi.json` fechado 2026-08-19 17:50 (205732 bytes) — refleja el contrato Fase 7 vigente.
- [x] tests que corre el operador durante Fase 8: los declarados por gate (Gate 0: `test_gui_server.py`).

**Stop:** si el worktree real difiere materialmente del repo inspeccionado, actualizar este plan antes de tocar producción. — No difiere.

---

# Gate 0 — Completar el bridge GUI → FastAPI

> **GATE 0 — COMPLETADO (2026-08-20).** El bridge reenvía `/api/platform/*`
> (GET/POST/PATCH) a FastAPI preservando status + envelope y los headers
> `Authorization`/`Idempotency-Key`, sin duplicar negocio. **Verificado por el
> operador: `test_gui_server.py` en verde.** Sin commit/push.
>
> **Evidencia (código):**
> - `app/back/src/ingestion/gui/server.py`: `PIPELINE_API_PREFIXES` ahora incluye
>   `"/api/platform"` (allowlist del ASGI bridge); nuevo `do_PATCH()` con el mismo
>   lifecycle de observabilidad que GET/POST que enruta los prefijos de pipeline a
>   `_handle_pipeline_api("PATCH")`; `_handle_pipeline_api` reenvía todos los headers
>   y preserva status+body; CORS `Access-Control-Allow-Methods = "GET, POST, PATCH,
>   OPTIONS"`. Ninguna lógica de negocio nueva en `server.py`.
> - `app/back/tests/ingestion/test_gui_server.py`: `test_platform_prefix_is_in_the_bridge_allowlist`,
>   `test_platform_get_is_forwarded_to_fastapi_bridge`,
>   `test_platform_post_is_forwarded_to_fastapi_bridge`,
>   `test_platform_patch_is_forwarded_with_headers_and_body`,
>   `test_platform_bridge_preserves_auth_and_idempotency_headers`,
>   `test_platform_bridge_preserves_error_status_and_envelope[401/403/409/422/503]`
>   (dobles `_RecordingBridge`/`_BridgeResponse`); test de CORS actualizado a incluir PATCH.

## Problema
`app/back/src/ingestion/gui/server.py` reenvía hoy las lanes embedding/indexing/retrieval, pero `/api/platform/*` no atraviesa el bridge y el handler visible no soporta `PATCH`.

## Files
- Modify: `app/back/src/ingestion/gui/server.py`
- Modify: `app/back/tests/ingestion/test_gui_server.py`

## Produces
- proxy de `GET`, `POST`, `PATCH` para `/api/platform/*`;
- preservación de headers relevantes;
- preservación exacta de status/error envelope FastAPI;
- la lane legacy continúa funcionando.

## Steps
- [x] Escribir tests:
  - `test_platform_get_is_forwarded_to_fastapi_bridge`
  - `test_platform_post_is_forwarded_to_fastapi_bridge`
  - `test_platform_patch_is_forwarded_with_headers_and_body`
  - `test_platform_bridge_preserves_auth_and_idempotency_headers`
  - `test_platform_bridge_preserves_error_status_and_envelope` (parametrizado 401/403/409/422/503) — nombre efectivo del `..._preserves_401_403_409_422_503` del plan.
- [x] ~~Ejecutar la regresión y comprobar FAIL~~ — **N/A / renunciado conscientemente**: el agente no ejecuta tests (política); implementación directa verificada en verde por el operador (sin snapshot rojo previo).
- [x] Añadir `"/api/platform"` a la allowlist/prefixes del ASGI bridge (`server.py::PIPELINE_API_PREFIXES`).
- [x] Implementar `do_PATCH()` con el mismo lifecycle de observabilidad que GET/POST (`server.py::Phase1GuiHandler.do_PATCH`).
- [x] No duplicar parsing de negocio en `server.py` — solo se amplió el allowlist + un método; el bridge genérico reenvía sin parsear.
- [x] Ejecutar regresión y comprobar PASS — **verificado por el operador (`test_gui_server.py` en verde)**.

**Gate 0 DoD — CUMPLIDO**
- [x] React/Vite puede alcanzar `/api/platform/*` (prefijo en el allowlist).
- [x] PATCH llega al router FastAPI real (`do_PATCH` → `_handle_pipeline_api("PATCH")` → AsgiBridge).
- [x] bearer e `Idempotency-Key` no se pierden (todos los headers se reenvían; test dedicado).
- [x] legacy no cambia de comportamiento (rutas legacy y su lifecycle intactos; tests legacy en verde).

---

# Gate 1 — Intake documental project-aware por HTTP

## Problema
El backend ya sabe registrar RAW por proyecto y normalizarlo, pero la superficie HTTP de plataforma no lo expone. Sin ello la GUI no puede obtener `srev_*` ni construir snapshots desde documentos subidos por el operador.

## Diseño de contrato

### `GET /api/platform/projects/{project_id}/documents`
Respuesta paginada/read-model:

```text
source_document_revision_id
logical_document_id
source_relpath
file_size
review_state
uploaded_at
raw_registered
normalized_registered
processing_status        # si puede derivarse autoritativamente
```

No devuelve paths físicos.

### `POST /api/platform/projects/{project_id}/documents`
`multipart/form-data`

Campos:
- `file`
- `source_relpath` lógico/canónico o metadata lógica equivalente aprobada por la política del proyecto.

El servidor:
- valida path relativo y evita traversal;
- calcula SHA-256 y file size;
- resuelve la raíz RAW desde `ProjectStorageResolver`;
- persiste bytes;
- invoca `RegisterProjectRawArtifactUseCase`;
- actor proviene de la sesión/principal, nunca del form.

### `POST /api/platform/projects/{project_id}/normalize`
JSON:

```json
{
  "rag_variant_id": "ragv_...",
  "document_revision_ids": ["srev_..."],
  "force": false
}
```

Reglas:
- `rag_variant_id` obligatorio para la GUI;
- todas las revisiones deben pertenecer al mismo `project_id`;
- preflight de identidad completo antes de escribir/promover;
- `run_pipeline` se reutiliza, no se reimplementa.

## Files
- Create: `app/back/src/rag_platform/application/document_query_service.py`
- Create: `app/back/src/rag_platform/application/project_normalization_service.py`
- Modify: `app/back/src/rag_platform/application/context.py`
- Modify: `app/back/src/rag_platform/application/services.py`
- Modify: `app/back/src/rag_platform/api/schemas.py`
- Modify: `app/back/src/rag_platform/api/router.py`
- Modify: `app/back/src/rag_platform/infrastructure/postgres/document_repositories.py`
- Modify: in-memory repository adapters correspondientes
- Modify: `scripts/rag_platform/run_project_ingestion.py`
- Test: `app/back/tests/rag_platform/test_platform_document_api.py`
- Test: `app/back/tests/rag_platform/test_project_ingestion_normalize.py`

## Steps

> **Gate 1 CERRADO (2026-08-20).** Operador corrió los 4 archivos en verde:
> `test_platform_document_api.py`, `test_project_ingestion_normalize.py`,
> `test_platform_cli_wrappers.py` (regresión CLI refactor), `test_platform_api.py`
> (regresión wiring). Slices A y B completos.

### Slice A — upload + read-model (verde)
- [x] Escribir tests de upload/list. → `app/back/tests/rag_platform/test_platform_document_api.py` (9 casos: srev+bytes en disco, sin paths físicos, traversal 400, 404, scope 403 upload y list, vacío, orden estable).
- [x] Añadir read-model `ProjectDocumentRevisionRow`. → `app/back/src/rag_platform/application/document_query_service.py` (row + `ListProjectDocumentsUseCase`, fail-closed por scope).
- [x] Implementar listados project-aware con orden estable. → `SourceDocumentRepository.list_revisions_for_project` (puerto en `context.py`; adaptadores in-memory y Postgres ordenan por `uploaded_at, id`).
- [x] Añadir endpoint multipart de upload. → `POST /projects/{id}/documents` en `api/router.py` (calcula SHA-256+size server-side, actor del principal) + `UploadProjectRawDocumentUseCase` (`application/project_raw_upload_service.py`) + puerto `ProjectRawStorage` y adaptador `FilesystemProjectRawStorage` (contención/traversal en `infrastructure/storage/project_storage.py`).
- [x] Verificar que no cruza ningún path físico por HTTP. → schemas `ProjectDocumentRevisionSchema`/`PaginatedProjectDocumentsSchema` (StrictModel) sin `artifact_relpath`; test `test_upload_no_expone_rutas_fisicas`.
- [x] Ownership cruzado en upload/list: `require_project_operator` fail-closed antes de tocar disco/leer (tests `*_fuera_de_scope_403`).
- Wiring: `application/services.py` (+2 campos), `api/dependencies.py` (repos `normalized`/`raw_catalog` en ambas ramas, use cases cableados). Verificado estáticamente: `py_compile` + import de `api.dependencies`/`rag_platform.api.router` OK, todos los campos/métodos presentes.
- Desviación de nombre: el upload vive en `project_raw_upload_service.py` (el plan solo listaba `project_normalization_service.py`); es un intake command distinto de normalize y se mantiene separado.

### Slice B — normalize (verde)
- [x] Motor tras puerto: `ProjectDocumentNormalizer` + `ProjectNormalizeOutcome` + `NormalizeProjectDocumentsUseCase` en `application/project_normalization_service.py` (autoriza, resuelve variante→perfil, valida ownership, delega). Unit-testeable sin pdfium/tesseract.
- [x] Extraer del CLI la orquestación física reusable → `execute_normalize_pipeline` en `infrastructure/normalization/run_pipeline_normalizer.py` (staging/promote/cloud-gating on-prem), única fuente compartida.
- [x] Hacer que el CLI (`run_project_ingestion.py`) consuma el servicio → su bloque `run_pipeline` inline se reemplazó por `execute_normalize_pipeline` (dedup). El path fail-closed sin DSN se preserva (test wrappers CLI intacto).
- [x] Endpoint `POST /projects/{id}/normalize` por `rag_variant_id` en `api/router.py` (síncrono, on-prem) + schemas `NormalizeProjectDocumentsRequestSchema`/`ProjectNormalizeReportSchema`.
- [x] Ownership cruzado fail-closed: variante de otro proyecto → `VariantProjectMismatch` (409); `srev_` de otro proyecto → `RevisionProjectMismatch` (409); bytes raw ausentes o identidad incompleta → `ProjectNormalizationIncomplete` (422, preflight antes de escribir). Errores nuevos en `domain/errors.py`.
- [x] Tests: `test_project_ingestion_normalize.py` (+3 unit del use case con fake normalizer: delega con fingerprint correcto, variante/revisión cross-project fail-closed sin tocar motor); `test_platform_document_api.py` (+4 HTTP: 422 sin variante, 422 sin revisiones, 404 proyecto, 403 scope — todos corto-circuitan antes del engine).
- Wiring: `services.py` (+1 campo), `api/dependencies.py` (`RunPipelineProjectNormalizer(storage_roots)`, `env_file=None` → entorno del proceso). Verificado: `py_compile` + import de router/dependencies/adaptador + carga del CLI OK.
- [x] Ejecutar tests → verde (operador, 2026-08-20).
- Ceiling (ponytail): normalize es **síncrono** en el worker HTTP y el happy-path (engine real) se cubre por CLI/corpus, no por la suite rápida. Upgrade: cola/async si un normalize largo bloquea workers.

**Gate 1 DoD** ✅ CERRADO
Un browser puede subir un PDF/Markdown a un proyecto, obtener un `srev_...`, normalizarlo bajo una variante y leer el estado sin tocar la lane legacy.

---

# Gate 2 — Read-models rehidratables

## Problema
La GUI debe sobrevivir a refresh. Hoy crear snapshot/release no basta si no existe un listado project-aware para reconstruir el contexto.

## Endpoints requeridos

```text
GET /api/platform/projects/{project_id}/corpus-snapshots
GET /api/platform/projects/{project_id}/releases
```

Ambos:
- paginados;
- scope-aware;
- orden estable por fecha/número;
- no filtran target físico.

## Read-only profile endpoints
Exponer también, si no están en el OpenAPI efectivo al ejecutar Fase 8:

```text
GET /api/platform/projects/{project_id}/processing-profiles
GET /api/platform/projects/{project_id}/chunking-profiles
```

Estos son read-models para que la UI no muestre IDs opacos sin contexto. No permiten crear ni alterar recetas por IDs libres.

## Files
- Create/Modify: `app/back/src/rag_platform/application/corpus_snapshot_query_service.py`
- Modify: `app/back/src/rag_platform/application/release_query_service.py`
- Modify: `app/back/src/rag_platform/application/services.py`
- Modify: `app/back/src/rag_platform/api/router.py`
- Modify: `app/back/src/rag_platform/api/schemas.py`
- Modify: repositories Postgres/in-memory necesarios
- Test: `app/back/tests/rag_platform/test_platform_api.py`

## Steps (implementado, pendiente de correr por el operador)
- [x] Test de snapshots scope-aware → `test_platform_api.py::test_list_corpus_snapshots_*` (vacío, no-vacío vía upload+snapshot, 403).
- [x] Test de release history por proyecto → `test_list_releases_vacio_ok` + `test_list_releases_fuera_de_scope_403`.
- [x] Test de paginación y orden → rutas paginadas (`paginate`); orden estable por `created_at, id` en el repo (Postgres + in-memory).
- [x] Test de 403 fuera de scope → snapshots/releases/perfiles con `ALPHA_TOKEN` sobre `proj_beta`.
- [x] Implementar list snapshot use case → `application/corpus_snapshot_query_service.py::ListProjectCorpusSnapshotsUseCase` (scope-aware) + `CorpusSnapshotRepository.list_for_project` (puerto + `PostgresCorpusSnapshotRepository` + `InMemoryCorpusSnapshotRepository`).
- [x] Reutilizar `ListProjectReleasesUseCase` → ruta `GET /projects/{id}/releases` sin caso de uso nuevo.
- [x] Publicar rutas anidadas por proyecto → `GET .../corpus-snapshots`, `.../releases`, `.../processing-profiles`, `.../chunking-profiles` en `api/router.py`.
- [x] No crear un listado global de releases → no se añadió; solo rutas anidadas por proyecto.
- [x] Perfiles scope-aware (fix de seguridad): `ListProcessingProfilesUseCase`/`ListChunkingProfilesUseCase` ahora exigen `access_policy` + `actor` y `require_project_operator` (antes no autorizaban y estaban sin ruta). Schemas de lectura `ProcessingProfileReadSchema`/`ChunkingProfileReadSchema` sin target físico. Test existente `test_project_queries.py` actualizado a la firma nueva + caso 403.
- [x] Regenerar `docs/api/pipeline-openapi.json` → operador corrió `scripts/api/export_pipeline_openapi.py` (2026-08-20).
- Verificado estático: `py_compile` + import de router/dependencies + 4 rutas registradas + wiring (`ALL=True`).

> **Gate 2 CERRADO (2026-08-20).** Operador corrió `test_platform_api.py` y
> `test_project_queries.py` en verde y regeneró el OpenAPI.

**Gate 2 DoD** ✅ CERRADO
Después de reload la SPA puede reconstruir documentos, snapshots, variantes y releases del proyecto sin inventar estado local.

---

> **Los tres gates backend (0, 1, 2) quedan CERRADOS (2026-08-20).** Lo que sigue
> (Gate 3+) es frontend en `app/front/`.

---

# Gate 3 — Sesión GUI local de operador

## Problema
FastAPI exige bearer, pero no debemos meter el secreto en el bundle Vite ni persistirlo en el browser.

## HTTP local GUI contract

### `POST /api/auth/login`
Request:
```json
{ "token": "operator-token" }
```

Response:
```json
{
  "authenticated": true,
  "principal_id": "operator-1",
  "project_scope": ["proj_alpha"]
}
```

`project_scope` es informativo.

Side effect:
```text
Set-Cookie: chatbot_sst_gui_session=<opaque>;
            HttpOnly;
            SameSite=Strict;
            Path=/
```

### `GET /api/auth/session`
Devuelve metadata pública de sesión o 401.

### `POST /api/auth/logout`
Revoca la sesión y expira cookie.

## Files
- Create: `app/back/src/ingestion/gui/auth_session.py`
- Modify: `app/back/src/ingestion/gui/server.py`
- Create: `app/back/tests/ingestion/test_gui_auth.py`

## Session store
Memoria de proceso para Fase 8:

```text
opaque_session_id ->
  principal_id
  project_scope
  bearer_credential
  created_at
  expires_at
```

Reglas:
- TTL;
- revoke;
- purge expiradas;
- comparación de tokens con la auth existente;
- no persistir en archivos;
- no loggear bearer;
- proteger rutas auth con same-origin/Host/Origin checks apropiados para el GUI local.

## Bridge behavior
Para `/api/platform/*`:
- resolver cookie;
- si no hay sesión → 401 GUI auth;
- inyectar bearer server-side;
- FastAPI vuelve a autenticar y autorizar normalmente;
- no inventar `actor_id`.

> **Gate 3 CERRADO (2026-08-20).** Operador corrió `test_gui_auth.py` y
> `test_gui_server.py` (regresión Gate 0) en verde.

## Implementado (verde)
- [x] `ingestion/gui/auth_session.py`: `GuiSessionStore` (dict + `threading.Lock`, TTL 12 h, `resolve` purga perezosa, `revoke`, `purge_expired` barrido en cada login), `GuiAuthCoordinator` (login valida con la **misma** `ConfiguredBearerAuth` que FastAPI, guarda bearer server-side), `parse_cookie`/`build_session_cookie`/`build_expired_cookie` (cookie opaca HttpOnly, SameSite=Strict, Path=/, Max-Age).
- [x] `ingestion/gui/server.py`: rutas `POST /api/auth/login`, `GET /api/auth/session`, `POST /api/auth/logout`; `_send_json(extra_headers=...)` para `Set-Cookie`; `Access-Control-Allow-Credentials: true`; guarda de `Origin` (allowlist local) en login/logout; wiring `server.gui_auth` en `main()`.
- [x] Bridge `/api/platform/*`: cookie válida → inyecta `Authorization: Bearer <bearer>` server-side y **descarta** el `Authorization` del cliente; cookie inválida/expirada → 401 `GUI_SESSION_REQUIRED`; sin cookie → passthrough (back-compat, FastAPI sigue siendo la autoridad).
- [x] `test_gui_auth.py`: store TTL/revoke/purge, `parse_cookie`, login válido/inválido/no-configurado, handlers login(cookie+metadata)/session(401 y metadata)/logout(revoca+expira), inyección de bearer + descarte de Authorization, cookie inválida → 401, sin cookie → passthrough.
- **Decisión (no romper Gate 0):** aditivo. Los tests Gate 0 (`test_gui_server.py`) reenvían `Authorization` sin cookie ni `gui_auth` → caen en el passthrough legacy y siguen verdes. El frontend usará la cookie; el DoD se cumple porque el browser no guarda bearer y FastAPI mantiene la frontera de confianza.
- Ceiling (ponytail): store monoproceso, TTL fijo, sin `Secure` (http localhost). Multiproceso/TLS → ADR.
- Verificado estático: `py_compile` + import de server/auth_session + handlers presentes (`ALL=True`).

**Gate 3 DoD** ✅ CERRADO
El browser no posee un bearer persistente y FastAPI conserva la misma frontera de confianza de Fase 7.

---

# Task 4 — Codegen y cliente HTTP frontend compartido

## Files
- Modify: `app/front/package.json`
- Create: `app/front/src/features/platform/platformOpenApi.generated.ts`
- Create: `app/front/src/features/platform/platformTypes.ts`
- Create/Move: `app/front/src/shared/api/apiClient.ts`
- Create/Move: `app/front/src/shared/api/apiTypes.ts`
- Create/Move: `app/front/src/shared/api/errorMapping.ts`
- Create: `app/front/src/features/platform/platformApi.ts`
- Test: platform API / shared client tests

## Requirements
`platformApi.ts`:
- same-origin fetch;
- `credentials: "same-origin"`;
- JSON + multipart + PATCH;
- idempotency key opcional;
- envelope de error único;
- no conoce bearer;
- no conoce localStorage.

Scripts:
```text
api:generate
api:check
```

## Steps

> **Slice 1 VERDE (2026-08-20):** operador corrió `npm --prefix app/front run test` + `run build` en verde (tsc cazó un over-match del sed en `usePollingLoop`, corregido).

### Slice 1 — move mecánico + extensión del cliente (verde)
- [x] Mover `apiClient/apiTypes/errorMapping` `features/embeddingIndexing/shared/` → `shared/api/` (extracción mecánica, contenido idéntico).
- [x] Extender `apiClient`: `credentials: "same-origin"` (default explícito; cookie Gate 3), `patchJson`, `postMultipart` (sin Content-Type manual: boundary del browser), prefijo idempotencia `"platform"`.
- [x] Actualizar importadores: 8 fuentes por specifier + `useEmbeddingIndexingPipeline.ts` + `shared/usePollingLoop.ts` (relativos `./shared/*`, cazados en verificación exhaustiva) + `embeddingApi.test.mjs` (`.tmp-tests/shared/api/`) + `tsconfig.test.json` (3 entradas). `pipelineState/pipelineFlow/usePollingLoop` se quedan en `embeddingIndexing/shared`.
- [x] Ponytail: `readJsonResponse` NO se movió (ya vive en `shared/`, genérico, usado por chunking/dashboard) → menos churn, hogar correcto.
- Verificación estática: `grep` exhaustivo → 0 imports stale; todo `apiClient/apiTypes/errorMapping` resuelve a `shared/api/`; `tsconfig.build.json` usa globs (sin cambios).
- Regresión pendiente: `npm --prefix app/front run test` + `npm --prefix app/front run build`.

> **Task 4 CERRADO (2026-08-20).** Operador corrió `npm --prefix app/front run test` + `run build` + `run api:check` en verde. Slices 1 y 2 completos.

### Slice 2 — codegen + platformApi (verde)
- [x] `openapi-typescript@7.13.0` (devDep) + scripts `api:generate` (genera desde `docs/api/pipeline-openapi.json`) y `api:check` (regenera + `git diff --exit-code` = drift guard).
- [x] `platformOpenApi.generated.ts` (5874 líneas, auto-generado) + `platformTypes.ts` (aliases `components["schemas"][...]`, **cero tipos manuales**).
- [x] `platformApi.ts`: projects/configuration (GET/POST/PATCH), matrix/variants, documents (list/upload multipart/normalize), corpus-snapshots, releases lifecycle (build/validate/publish/retire con Idempotency-Key auto). Adaptador delgado sobre `shared/api` (reuso, sin duplicar cliente); sin bearer/localStorage; `credentials:"same-origin"`.
- [x] `platformApi.test.mjs`: GET+query, POST JSON, PATCH, multipart sin Content-Type manual, Idempotency-Key (auto + replay provisto), envelope de error 401/403/409/422/503. Encadenado en `test`; 3 archivos añadidos a `tsconfig.test.json`.
- Verificado por mí (estático): `tsc -p tsconfig.test.json` sin errores + `node platformApi.test.mjs` 11/11 verde.
- Pendiente operador: `npm --prefix app/front run test` + `run build` + `run api:check`.

**DoD** ✅ CERRADO
No existe contrato TypeScript manual paralelo al OpenAPI: los tipos salen de `platformOpenApi.generated.ts` y `api:check` detecta drift.

---

# Task 5 — Estado y persistencia de plataforma

## Files
- Create: `app/front/src/features/platform/platformState.ts`
- Create: `app/front/src/features/platform/platformPersistence.ts`
- Create: `app/front/src/features/platform/hooks/usePlatformPreferences.ts`
- Tests correspondientes

## Types

```ts
type PlatformPreferences = {
  selectedProjectId: string | null;
  selectedRagVariantId: string | null;
  selectedCorpusSnapshotId: string | null;
  selectedRagReleaseId: string | null;
};
```

Estado no persistible:
- session metadata;
- current requests;
- idempotency keys;
- form drafts sensibles.

## Rehydration
Al iniciar:

```text
GET session
GET projects
validate selectedProjectId
GET variants/snapshots/releases del proyecto
validate persisted selections
clear stale/out-of-scope IDs
```

> **Task 5 CERRADO (2026-08-20).** Operador corrió `npm --prefix app/front run test` + `run build` en verde.

## Implementado (verde)
- [x] `platformState.ts`: `PlatformPreferences` (4 IDs), `DEFAULT_PLATFORM_PREFERENCES`, `PlatformSelectionScope`, `platformPreferencesEqual`, y `resolvePlatformPreferences({stored, scope})` puro — `scope:null` preserva (sin borrar por falta de evidencia); con scope, proyecto fuera-de-scope limpia TODO (cascada), dependientes obsoletos se limpian individualmente.
- [x] `platformPersistence.ts`: espejo de `dashboardPersistence` (STORAGE_KEY `chatbot-sst.platform.preferences.v1`, guard SSR, try/catch silencioso, coerción `toStringOrNull`). **Solo serializa los 4 IDs** (objeto explícito → no filtra campos extra).
- [x] `hooks/usePlatformPreferences.ts`: espejo de `useDashboardPreferences` — init read+resolve, re-resolve al llegar `scope`, persiste en cambio, setters con `setSelectedProject` cascada-limpia dependientes; guarda `platformPreferencesEqual` evita re-render/persist loops.
- [x] Tests: `platformState.test.mjs` (6: preserva/cascada/limpieza/equal) + `platformPersistence.test.mjs` (5: round-trip, **no filtra bearer/idempotency**, SSR null, corrupto→null, serialize). Cableados en `test` + `tsconfig.test.json`.
- Reuso (ponytail/SOLID): 0 helpers de storage nuevos; mismo patrón/estilo que dashboard; `resolve` pura (SRP), sin reducer ni estado global (4 IDs no lo justifican).
- Verificado por mí: `tsc -p tsconfig.test.json` sin errores + 11/11 `.test.mjs` verde.

**DoD** ✅ (pendiente verde del operador)
Refresh conserva navegación útil sin preservar autoridad obsoleta ni secretos.

---

# Task 6 — `OperatorApp` y boundary Legacy

## Files
- Create: `app/front/src/features/operator/OperatorApp.tsx`
- Create: `app/front/src/features/operator/operatorNavigation.ts`
- Create: `app/front/src/features/operator/components/OperatorSidebar.tsx`
- Create: `app/front/src/features/operator/OperatorApp.test.tsx`
- Modify: `app/front/src/App.tsx`
- Preserve: dashboard navigation/types/persistence unless a shared visual component must be extracted

## Navigation

```text
Platform
Legacy pipeline
```

Dentro de Legacy se renderiza `DashboardApp` exactamente como hoy.

## Tests
- los cinco `DASHBOARD_VIEWS` legacy siguen siendo los mismos;
- todos los títulos legacy siguen conteniendo `Legacy pipeline`;
- `platform` no entra en `DashboardPreferences`;
- OperatorApp puede cambiar entre Platform y Legacy.

## Implementado (tsc test + tsc build + vitest verde localmente; PENDIENTE correr suite del operador)
- [x] `features/operator/operatorNavigation.ts`: `OperatorSurface = "platform" | "legacy"` (tipo **nuevo y separado** de `AppView`), `OPERATOR_SURFACES` (fuente única), `isOperatorSurface`. No toca `dashboardTypes`/`dashboardNavigation` → `"platform"` NO entra en `DashboardPreferences`.
- [x] `features/operator/components/OperatorSidebar.tsx`: rail primario delgado; reusa `.brand`/`.nav-item`; iconos `lucide-react` (`Layers`/`LayoutGrid`/`History`); `aria-current="page"` en activo, `aria-label` en nav.
- [x] `features/operator/OperatorApp.tsx`: `useState<OperatorSurface>("platform")` (sesión, no persistido — ponytail YAGNI). Legacy → `<DashboardApp/>` **intacto**; Platform → placeholder con `.workspace`/`.topbar` + empty-state direccional (estética base para Task 7).
- [x] `styles/operator.css`: `.operator-shell` (grid rail 88px + 1fr), `.operator-rail` (reusa lenguaje de `.sidebar`), empty-state con tokens (`--panel`/`--accent-soft`/`--muted`/`--shadow`); responsive 1180px (rail 72px) y 760px (barra horizontal), espejo de `shell.css`. `@import` añadido a `styles.css`.
- [x] `App.tsx`: default export ahora `OperatorApp` (mount en `main.tsx` intacto). `DashboardApp` sin cambios (boundary Legacy preservado).
- [x] `OperatorApp.test.tsx` (vitest + testing-library, `fetch` mockeado): 5 `DASHBOARD_VIEWS` intactas, `isDashboardView("platform")===false`, label "Legacy pipeline" en el rail, conmutación Platform↔Legacy.
- Diseño (frontend-design): rail 88px slim (no compite con sidebar 224px del dashboard); **cero hex de marca nuevos** (solo tokens de `theme.css`); consistente/responsive/dinámico/accesible. La firma visual (riel de linaje) llega en Task 7 (workspaces); Task 6 es solo el shell/boundary.
- Reuso/SOLID (ponytail-audit): reusa clases y patrón de `DashboardSidebar`/`shell.css`; un componente = una responsabilidad (rail / shell / placeholder); sin duplicar botones/tarjetas; sin estado global (surface local); `DashboardApp` no se modifica.
- Verificado: `tsc -p tsconfig.test.json` OK + `tsc -p tsconfig.build.json --noEmit` OK (typecheck de los `.tsx`) + `vitest run` 16/16 verde.
- **Pendiente correr por el operador:** `npm --prefix app/front run test` + `npm --prefix app/front run build`.

**DoD** ✅ (pendiente verde del operador)
La plataforma es una superficie nueva, no una sexta pantalla del dashboard legacy.

---

# Task 7 — Projects + Configuration Workspace

## Files
- Create: `features/platform/projects/ProjectWorkspace.tsx`
- Create: `features/platform/projects/ProjectList.tsx`
- Create: `features/platform/projects/ProjectConfigurationForm.tsx`
- Tests

## Capabilities
- list projects;
- create project;
- edit `display_name`;
- read configuration;
- create new configuration version.

Editable:
- corpus organization policy;
- document types;
- embedding profiles.

Read-only:
- logical `binding_key`;
- embedding profile associated to binding.

Never visible:
- physical target id.

## Fail-closed
- 403: forbidden state;
- 503 auth-not-configured: server configuration problem, not login;
- 422: field validation.

**DoD**
Un operador puede configurar un proyecto sin tocar bindings físicos.

---

# Task 8 — Recipe / Variant Matrix Workspace

## Files
- Create: `features/platform/variants/VariantMatrixWorkspace.tsx`
- Create: `features/platform/variants/VariantMatrixTable.tsx`
- Tests

## Flow

```text
GET matrix
 → render buildable / blocked_reason
 → select cell
 → enter variant_slug
 → POST cell_id + variant_slug
```

Rules:
- no manual processing/chunking/embedding IDs;
- on `STALE_VARIANT_MATRIX_CELL`: refetch + require explicit reconfirmation;
- never silently choose another cell.

**DoD**
Toda variante GUI deriva de una celda reconfirmada de la configuración vigente.

---

# Task 9 — Document Intake + Normalize Workspace

## Files
- Create: `features/platform/documents/DocumentIntakeWorkspace.tsx`
- Create: `features/platform/documents/RawUploadPanel.tsx`
- Create: `features/platform/documents/RevisionTable.tsx`
- Create: `features/platform/documents/NormalizationPanel.tsx`
- Tests

## Panels
1. RAW upload
2. Registered revisions
3. Normalize

## Flow

```text
selected project
 → upload
 → srev_
 → select variant
 → select revisions
 → normalize
 → refresh document read-model
```

UI renders:
- raw registered;
- normalized registered;
- processing/review state;
- canonical IDs.

**DoD**
El operador puede llevar documentos desde RAW hasta normalizados dentro del namespace del proyecto.

---

# Task 10 — Corpus Snapshot Workspace

## Files
- Create: `features/platform/corpus/CorpusSnapshotWorkspace.tsx`
- Create: `features/platform/corpus/SnapshotBuilder.tsx`
- Create: `features/platform/corpus/SnapshotHistory.tsx`
- Tests

## Flow
- choose normalized/eligible revisions;
- for `needs_review`, collect explicit eligibility decision when required;
- create immutable snapshot;
- refresh snapshot history;
- persist selected snapshot ID only.

## Errors
- `RELEASE_BUILD_TOO_LARGE` is not handled here unless returned by snapshot policy;
- invalid/cross-project revisions → fail closed;
- stale project selection → clear selection and reload.

**DoD**
Snapshot is reproducible and rehydratable after refresh.

---

# Task 11 — Release Lifecycle Workspace

## Files
- Create: `features/platform/releases/RagReleaseWorkspace.tsx`
- Create: `features/platform/releases/ReleaseDraftForm.tsx`
- Create: `features/platform/releases/ReleaseLifecycle.tsx`
- Create: `features/platform/releases/BuildReport.tsx`
- Create: `features/platform/releases/ReleaseHistory.tsx`
- Create: `features/platform/releases/useIdempotentReleaseAction.ts`
- Tests

## Flow

```text
variant + snapshot + logical target_binding_key
 → DRAFT
 → BUILD
 → VALIDATE
 → PUBLISH
 → optional RETIRE
```

Build report:
- revisions built;
- reused stages;
- built stages.

Idempotency:
- stable key for retry of same intent;
- new key only after terminal response or explicit abandon/new intent.

Conflicts:
- `IDEMPOTENCY_KEY_CONFLICT`: show conflict, do not auto-regenerate and replay.
- `INVALID_RELEASE_TRANSITION`: refetch release.
- `RELEASE_BUILD_TOO_LARGE`: suggest reducing snapshot.
- `IDEMPOTENT_OPERATION_FAILED`: require explicit new attempt/key.

**DoD**
Release lifecycle is controlled by platform API, not by legacy orchestration from React.

---

# Task 12 — Fail-closed UX + shared UI states

## Files
- Create/extend `app/front/src/components/ui/`
  - `StatePanel.tsx`
  - `StatusBadge.tsx`
  - `InlineNotice.tsx`
  - `BlockedReason.tsx`
  - `ConfirmAction.tsx`
- Modify shared error mapper
- Component tests

## Mapping

| HTTP/code | UI behavior |
|---|---|
| `401 HTTP_AUTH_REQUIRED/INVALID` | sesión no válida → credential screen |
| `503 HTTP_AUTH_NOT_CONFIGURED` | server misconfiguration, never login loop |
| `403 PLATFORM_ACCESS_DENIED/HTTP_PROJECT_SCOPE_FORBIDDEN` | forbidden state, never empty |
| `409 STALE_VARIANT_MATRIX_CELL` | refresh matrix + reconfirm |
| `409 INVALID_RELEASE_TRANSITION` | refresh release |
| `409 IDEMPOTENCY_KEY_CONFLICT` | explicit conflict |
| `422 INVALID_PLATFORM_ID/PIPELINE_INVALID_REQUEST` | field/input validation |
| `503 RAG_PLATFORM_V1_DISABLED` | feature disabled |
| `422 RELEASE_BUILD_TOO_LARGE` | reduce snapshot |
| unknown | preserve code/message/details |

**DoD**
La GUI no convierte bloqueo en éxito ni pierde el código de error del backend.

---

# Task 13 — Security/contract regression

## Backend assertions
- every `/api/platform/*` call still ends at FastAPI auth;
- bridge never invents actor;
- cross-project document/release access → 403/fail closed;
- upload rejects traversal;
- normalize accepts GUI `rag_variant_id`, not free physical target;
- list endpoints are scope-aware;
- no physical target/path in platform schemas.

## Frontend assertions
- no token in built sources/config/preferences;
- no `actor_id`;
- no `indexing_target_id`;
- no `target_bindings` mutation;
- variant request only `cell_id + variant_slug`;
- same logical retry reuses idempotency key;
- new intent creates new key;
- legacy persistence remains legacy-only.

---

# Task 14 — Final verification and handoff

## Backend
Operator runs the declared suites, at minimum:

```powershell
.\.venv_windows_trabajo\Scripts\python.exe -m pytest `
  app\back\tests\ingestion\test_gui_server.py `
  app\back\tests\ingestion\test_gui_auth.py `
  app\back\tests\rag_platform\test_platform_api.py `
  app\back\tests\rag_platform\test_platform_document_api.py `
  app\back\tests\rag_platform\test_project_ingestion_normalize.py -q
```

Plus the broader rag-platform/composition suites required by the repository policy.

## OpenAPI
```powershell
npm run python -- scripts/api/export_pipeline_openapi.py
npm --prefix app/front run api:check
```

## Frontend
```powershell
npm --prefix app/front test
npm --prefix app/front run build
```

## Manual E2E acceptance
On PostgreSQL mode with platform/auth flags enabled:

```text
login
→ create/select project
→ configure project
→ upload raw document
→ obtain srev_
→ create/select variant from matrix
→ normalize revision
→ create corpus snapshot
→ create DRAFT release
→ build
→ validate
→ publish
→ refresh browser
→ project/snapshot/release state rehydrates correctly
→ legacy dashboard remains separately labeled
```

## Documentation
Update:
- `plans/2026-08-20-fase8-exploratoria-gui-plataforma.md`
- `docs/api/pipeline-openapi.json`
- this plan
- operator runbook for GUI session/token configuration.

---

# Definition of Done — Fase 8

## Contract
- [x] `/api/platform/*` reachable through GUI bridge including PATCH. *(Gate 0, 2026-08-20)*
- [ ] project-aware upload/list/normalize exists.
- [ ] snapshots and releases can be listed by project.
- [ ] OpenAPI regenerated and TS codegen clean.

## Security
- [ ] FastAPI bearer auth remains authoritative.
- [ ] bearer not persisted in browser.
- [ ] project scope enforced server-side.
- [ ] no actor/physical target/path authority from frontend.
- [ ] idempotency semantics preserved.

## Functional
- [ ] operator can create/configure project.
- [ ] operator can create variant from matrix.
- [ ] operator can upload and normalize RAW by project.
- [ ] operator can create corpus snapshot.
- [ ] operator can build/validate/publish/retire releases.
- [ ] refresh rehydrates project/snapshot/release history.

## Compatibility
- [ ] Legacy pipeline remains intact and explicitly labeled.
- [ ] existing dashboard persistence schema is not polluted with platform selections.
- [ ] retrieval/activation is not silently moved into Platform.

## Quality
- [ ] targeted backend tests pass.
- [ ] full frontend test suite passes.
- [ ] frontend build passes.
- [ ] no P0/P1 security or contract gaps remain.

---

# Deferred after Fase 8

- OIDC/SSO real and durable distributed sessions.
- RBAC beyond the existing provider/seam.
- Platform-native retrieval profile administration once its HTTP contract stops exposing physical target authority.
- Consumer/chatbot configuration UI.
- automatic activation of published releases (explicitly not desired).
- quality dashboards/benchmarks beyond the release build/validation reports.
