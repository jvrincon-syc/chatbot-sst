# Plan — Rework de GUIs de Platform reutilizando la lane legacy (multi-proyecto)

- **Fecha**: 2026-08-21
- **Rama**: main
- **Área**: front (+ ajustes puntuales de back para defectos bloqueantes)
- **Estado**: EXPLORACIÓN CERRADA / LISTO PARA EJECUCIÓN
- **Predecesor**: `docs/superpowers/plans/2026-08-20-fase8-gui-plataforma-plan.md` (Fase 8, CERRADA)

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convertir Platform en la superficie multi-proyecto limpia y auditable para operar el ciclo RAG completo (`documents -> corpus snapshots -> variants -> releases`) reutilizando la lógica visual y operativa madura de legacy, que ya funciona para un corpus, pero parametrizada por `project_id` para soportar proyectos con corpus distintos y releases verificables por `rag_release_id`.

**Architecture:** FastAPI sigue siendo la autoridad de scope, idempotencia, permisos, build y compatibilidad; React solo dispara comandos Platform y consume read-models tipados. El build de release pasa a job durable server-owned con estado consultable bajo demanda y refresh controlado solo cuando la release visible esté `queued`/`running`. La UI de Platform consume adapters propios sobre componentes, flujo y patrones legacy: el patrón probado de legacy para un corpus se reutiliza por `project_id`, sin acoplar Legacy a Platform ni duplicar una segunda orquestación.

**Tech Stack:** Python 3.12, FastAPI, Pydantic 2, PostgreSQL/in-memory repositories, React, TypeScript strict mode, `platformApi`, shared API client, legacy `pipelineState`/`pipelineFlow`/panel primitives, pytest, Vitest, production frontend build.

**Spec:** Este plan reemplaza y consolida `docs/superpowers/plans/2026-08-21-platform-gui-rework-continuation.md`, y deriva de `docs/superpowers/plans/Plan_Ajustado_Plataforma_RAG_MultiProyecto(3).md`.

## Global Constraints

- No borrar ni sustituir documentos fuente; este archivo es el plan definitivo de ejecución.
- No reabrir contratos de Fase 7 ni exponer `actor_id`, `indexing_target_id`, rutas físicas, secretos, chunks raw o vectores al frontend.
- Fail-closed siempre visible: nada de fallbacks silenciosos, listas vacías falsas o success envelopes inventados.
- Platform y Legacy permanecen superficies hermanas; Platform puede reutilizar piezas, pero Legacy no importa tipos Platform.
- Backend owns build authority: el browser nunca orquesta chunking, embedding, indexing ni selección física de target.
- Evitar consulta agresiva para estado de build Platform; usar status bajo demanda y, si hay auto-refresh, que sea adaptativo con backoff, pausa por pestaña oculta, timeout y refresh manual.
- TDD obligatorio por tarea: prueba fallida, implementación mínima correcta, pruebas focalizadas, regresión afectada y cierre documentado.

---

## Idea Central

Platform no debe ser una UI paralela improvisada. Debe reutilizar la lógica visual
y operativa madura de la lane legacy, pero aplicada por `project_id`.

Legacy pipeline ya demuestra que el flujo RAG funciona para un corpus. Platform
debe reciclar esas vistas, estados y patrones para operar muchos proyectos, donde
cada proyecto puede tener un corpus distinto, snapshots distintos, variantes
distintas y releases distintas.

La Platform debe permitir operar el ciclo RAG multi-proyecto completo:
documentos, corpus snapshots, variantes y releases. Ese reuso no puede debilitar
auditoría, aislamiento, trazabilidad ni contratos de Fase 7.

El E2E objetivo no es que Platform pinte una UI bonita aparte: es que desde
Platform se pueda llegar a una release RAG auditada y operable, identificada por
`rag_release_id`, usando el backend y los contratos de Platform.

## Objetivo del plan

- Reusar componentes y patrones legacy donde ya funcionan bien.
- Parametrizar el pipeline visual/operativo legacy por `project_id`, no por un
  corpus global único.
- Mantener Platform y Legacy como superficies separadas.
- Evitar duplicación de UI, hooks, estados, tablas y lógica de flujo.
- Corregir bloqueos reales: build síncrono, listas incompletas, selección masiva
  y UX inconsistente.
- Preservar fail-closed: si algo falta, falla, está bloqueado o requiere revisión,
  se muestra como tal.

## Método de acción

1. Cerrar Fase A primero: job asíncrono durable para `releases/{id}/build`, estado
   consultable y tests backend de contrato.
2. Generalizar carga completa/paginada para `variants` y `releases`, igual que ya
   se hizo en `documents` y `corpus`.
3. Extraer/reusar de legacy la capa de estado, flujo, paneles, tablas y navegación
   que ya está probada.
4. Recomponer las vistas Platform sobre esa capa compartida.
5. Pulir accesibilidad, responsive, estados de error, runbook y verificación final.

## Resultado final esperado

Platform queda como una superficie multi-proyecto limpia, auditable y operable,
con la misma calidad de flujo que legacy, pero sin mezclar contratos ni
responsabilidades.

El operador podrá seleccionar proyecto, revisar documentos, crear snapshots,
crear variantes, construir releases, validar y publicar sin caídas de socket, sin
listas truncadas, sin selección riesgosa y sin sobrecargar el sistema con refresh
innecesario.

La prueba E2E debe demostrar que un proyecto con su corpus propio puede completar
el flujo hasta una release RAG identificada por `rag_release_id`, sin depender del
corpus único de legacy ni de una orquestación frontend paralela.

## 0. Cierre de exploración (2026-08-21)

La exploración ya no está “en abstracto”: este branch deja resueltos los
prerrequisitos mínimos para ejecutar el rework sin volver a redescubrir los
mismos bugs.

### Evidencia cerrada en código

- **D-1 parcial, ya aterrizado en la UI real**:
  - `app/front/src/features/platform/platformApi.ts`
    añade `collectAllPages`, `listAllDocuments` y `listAllCorpusSnapshots`.
  - `app/front/src/features/platform/documents/useDocumentIntakeWorkspace.ts`
    carga el corpus documental completo.
  - `app/front/src/features/platform/corpus/useCorpusSnapshotWorkspace.ts`
    carga todas las revisiones candidatas y todo el historial de snapshots.
- **D-2 parcial, ya aterrizado con política fail-closed**:
  - Intake documental: `Seleccionar todos` ya no auto-incluye revisiones
    `needs_review`; esas quedan para selección explícita del operador.
  - Snapshot builder: ya existe selección masiva (`Seleccionar todas las
    elegibles`) y tampoco auto-incluye `needs_review`.
- **D-3a, desbloqueo de transporte verificado**:
  - `app/back/src/ingestion/gui/server.py` ya convierte excepciones del bridge en
    `500` con envelope (`PIPELINE_BRIDGE_ERROR`) en vez de cortar el socket.
  - `app/back/tests/ingestion/test_gui_server.py` fija la regresión con test
    explícito del caso de excepción.

### Verificación ejecutada en este branch

- Backend: `C:\venvs\chatbot-sst\Scripts\python.exe -m pytest app/back/tests/ingestion/test_gui_server.py -q`
- Frontend focalizado: Vitest de `documents`, `corpus` y `PlatformWorkspace`
- Frontend completo: `npm --prefix app/front run test`
- Frontend build: `npm --prefix app/front run build`

### Qué NO quedó cerrado aún

- **D-3b sigue pendiente**: `releases/{id}/build` continúa siendo síncrono en el
  backend; el endurecimiento del bridge evita el *socket hang up* silencioso, pero
  no reemplaza aún la necesidad de build asíncrono/encolado con estado observable.
- **La recomposición grande de Platform sobre la lane legacy no empezó aún**:
  este cierre prepara el terreno, no ejecuta las Fases C/D/E.
- **La paginación completa todavía no se generalizó a todas las listas
  project-aware** (`variants`, `releases`, y cualquier otra vista que hoy consuma
  solo la primera página).

## 1. Problema

Fase 8 construyó las superficies de Platform (Projects, Variants, Documents,
Corpus, Releases) **desde cero**. La lane **Legacy pipeline** ya resuelve bien la
gestión del pipeline RAG de un corpus (ingesta → normalize → chunk → embed →
index → retrieval), con vistas maduras: shell con `view-switcher`, orquestación
por máquina de estados, refresh de runs, paneles de run/estado/catálogo, tablas y
tokens consistentes. Platform reinventó esas piezas peor, en vez de reciclarlas.

La consecuencia práctica (con datos reales de `sst-general`, 55 documentos):

- **Intake lista solo 25 de 55** documentos (`page_size` por defecto = 25; la
  vista no pagina ni sube el tamaño).
- **No hay "seleccionar todos"** en intake ni en snapshot: marcar 55 revisiones a
  mano es inviable.
- **`GET variant-matrix` y `POST releases/{id}/build` responden *socket hang
  up*** — el backend GUI cierra la conexión sin responder.
- Las vistas de Platform "se ven horribles" y no siguen el lenguaje de la lane
  legacy.

La idea rectora del operador: **lo que el legacy hace para un corpus, Platform
debe hacerlo por `project_id`, reutilizando las mismas vistas** — no una segunda
implementación paralela.

## 2. Objetivo

Reutilizar los componentes/máquina-de-estados probados de la lane legacy,
parametrizados por proyecto y alimentados por `platformApi` (contrato de Fase 7),
de modo que Platform ofrezca la misma gestión de pipeline RAG que el legacy, pero
multi-proyecto, con UX y estética consistentes. Cerrar de paso los defectos
bloqueantes que impiden operar con un corpus real.

### No-objetivos

- No reabrir el contrato backend de Fase 7 (auth, scope, sin fuga de target
  físico, idempotencia).
- No fusionar las dos superficies: `Legacy pipeline` sigue existiendo y
  etiquetada; Platform es la superficie multi-proyecto.
- No implementar SSO/OIDC, chat, ni administración de retrieval de producción.
- No reescribir el backend de plataforma salvo los arreglos puntuales del §5.

## 3. Inventario de reutilización (auditoría previa)

Qué ya existe y es reutilizable (evitar duplicación):

| Legacy / compartido | Qué aporta | Reuso en Platform |
| --- | --- | --- |
| `features/embeddingIndexing/shared/{pipelineState,pipelineFlow,usePollingLoop}` | Máquina de estados del pipeline + patrones de refresh/visibilidad legacy | Reusar estados, transiciones y disciplina de abort/visibilidad; Platform no copia polling agresivo ni orquesta etapas legacy |
| `features/{embedding,indexing,retrieval,chunking}/components/*` | Paneles de run, estado, catálogo, tablas densas | Vistas por etapa del pipeline, alimentadas con datos scope-aware |
| `features/dashboard/{DashboardApp,components/DashboardChrome}` | Shell, `DashboardNotice`, `view-switcher`, `user-chip` | Lenguaje de shell ya adoptado por `OperatorApp` |
| `components/ui/{MetricCard,StatePanel,StatusBadge}` | Estados y badges compartidos (extraídos en Task 12) | Ya en uso; ampliar adopción |
| `shared/api/*` + `platformApi.ts` | Cliente HTTP tipado, envelope único, cookie same-origin | Fuente de datos de todas las vistas |

Qué reinventó Platform y hay que **reemplazar por lo anterior**: tablas y formularios
propios en `platform/{documents,corpus,variants,releases}` que no siguen el patrón
de run-panels/tablas del legacy.

## 4. Estrategia

1. **Generalizar, no duplicar.** Extraer de la lane legacy los componentes de
   etapa (chunk/embed/index/retrieval) y la orquestación a una capa reutilizable
   que acepte un **contexto de proyecto** (`project_id` + scope) en vez de asumir
   el corpus legacy único. Donde el componente hoy asume la lane global, se le
   inyecta el contexto por props/hook.
2. **Platform compone.** Los workspaces de Platform pasan a **componer** esos
   componentes generalizados, alimentándolos con `platformApi` (datos
   project-aware). Se eliminan las tablas/formularios ad-hoc de Fase 8 que no
   aportan.
3. **Arreglar el data-layer una vez.** Paginación real + "seleccionar todos" +
   estados vacíos/carga viven en los componentes compartidos de lista/tabla, así
   ambos lanes se benefician.
4. **Desbloquear el backend** (§5) antes de confiar la UI de variante/release: sin
   eso, la vista se rehace sobre una API que se cae.

## 5. Defectos a resolver (raíz, no síntoma)

### D-1 · Paginación del read-model (25 de 55)
- Causa: `listDocuments(pid, undefined)` usa `DEFAULT_PAGE_SIZE=25`; la UI no
  pagina ni sube `page_size` (máx `MAX_PAGE_SIZE=100`).
- Arreglo: read-model paginado en la vista (controles página/tamaño) **o** carga
  incremental hasta agotar `total_pages`. Aplica a Documents, Corpus, Releases,
  Variants (cualquier lista scope-aware). Corpus > 100 exige paginación real, no
  solo subir el tamaño.

### D-2 · "Seleccionar todos" / selección masiva
- Falta en intake (normalize) y snapshot builder.
- Arreglo: acción de selección masiva sobre el conjunto **cargado** (respetando
  paginación: "seleccionar todos en esta página" vs "todos los N"), en el
  componente de tabla compartido. Mantener el gate fail-closed de `needs_review`
  (una revisión que exige decisión no se auto-incluye en "todos").

### D-3 · `variant-matrix` y `releases/build` → *socket hang up*
- Síntoma: el bridge GUI (`ThreadingHTTPServer` → `AsgiBridge` → FastAPI) cierra
  la conexión sin responder.
- Hipótesis a diagnosticar (backend):
  - `GET variant-matrix`: excepción no manejada en el `AsgiBridge` o en la
    serialización de celdas para el proyecto real (p. ej. binding/perfil ausente,
    o el bridge no traduce una excepción a envelope y muere el handler).
  - `POST releases/{id}/build`: el build corre el **motor real de forma
    síncrona** dentro del request HTTP de un servidor de un solo hilo → bloquea
    hasta timeout/caída del socket.
- Arreglo decidido: (a) mantener el `AsgiBridge` endurecido para que toda
  excepción se convierta en respuesta con envelope (nunca cerrar el socket);
  (b) ejecutar el build **asíncrono/encolado** con estado durable; (c) exponer
  `GET build-status` para consulta bajo demanda; (d) si la UI necesita
  auto-refresh, hacerlo solo mientras la release visible esté `queued`/`running`,
  con backoff, pausa al ocultar pestaña, timeout, cancelación al cambiar de
  release/proyecto y botón manual de refresh. Esto evita consulta agresiva y no
  exige WebSockets/SSE real, que hoy no encaja bien porque `AsgiBridge` bufferiza
  las respuestas ASGI.
- **Este defecto es prerrequisito**: la UI de Variants/Releases no se puede
  rehacer con confianza mientras la API se cae.

### D-4 · Estética/UX de las vistas Platform
- Se resuelve estructuralmente al reusar los componentes legacy (§4), no con
  parches cosméticos.

## 6. Decisiones Técnicas Grandes

La versión definitiva combina este plan con
`2026-08-21-platform-gui-rework-continuation.md`, pero corrige la decisión de
progreso del build: **no se implementa consulta agresiva de 1s para Platform**.

La arquitectura final es:

1. `POST /api/platform/releases/{id}/build` no ejecuta el build en el request:
   reserva o reusa un job idempotente, valida permisos/scope server-side y
   responde `202 Accepted` con un snapshot de job.
2. El backend ejecuta el build en un runner server-owned. El navegador nunca
   orquesta chunking, embedding, indexing, targets físicos ni etapas internas.
3. `GET /api/platform/releases/{id}/build-status` devuelve el último snapshot
   durable para recarga, diagnóstico y pruebas.
4. El estado del job es consultable bajo demanda. Si se habilita auto-refresh, es
   adaptativo: solo para la release visible en `queued`/`running`, con backoff,
   pausa al ocultar pestaña, timeout, abort al cambiar de contexto y botón manual
   de refresh.
5. El frontend nunca envía `indexing_target_id`, paths físicos, `actor_id`,
   secretos ni autoridad física. El backend deriva proyecto, variante, snapshot,
   binding lógico, target real y permisos.
6. La UI no orquesta chunking, embedding ni indexing legacy; solo dispara comandos
   de Platform y muestra estado.
7. La paginación se resuelve correctamente para documents, corpus, variants y
   releases.
8. `needs_review` nunca entra por selección masiva automática.
9. Se reusa la lane legacy para estados, paneles, tablas, navegación, tokens,
   errores y disciplina de abort/visibilidad; **no** se copia una segunda lógica
   paralela de flujo.

Esta decisión es la opción más conservadora para el estado actual del repo:
evita bloquear el servidor, evita sobrecargar con refresh innecesario, no requiere
WebSockets, no fuerza SSE sobre un `AsgiBridge` que hoy bufferiza respuestas, y
conserva un contrato auditable e idempotente.

## 7. Estructura de archivos definitiva

### Backend

- Crear `app/back/src/rag_platform/domain/release_build_job.py`: entidad/DTO de
  job, estado, versión, timestamps, error y reporte.
- Crear `app/back/src/rag_platform/application/release_build_job_service.py`:
  casos de uso `StartReleaseBuildJobUseCase` y `GetReleaseBuildJobStatusUseCase`.
- Modificar `app/back/src/rag_platform/application/release_build_service.py`:
  conservar la lógica durable por revisión; mover la invocación al runner.
- Modificar `app/back/src/rag_platform/application/services.py`: exponer los
  nuevos casos de uso en `RagPlatformServices`.
- Modificar `app/back/src/api/dependencies.py`: cablear repositorios/runners en
  modo in-memory y Postgres.
- Crear `app/back/src/rag_platform/infrastructure/in_memory/release_build_jobs.py`:
  repo determinístico y runner drenable para tests.
- Crear `app/back/src/rag_platform/infrastructure/postgres/release_build_jobs.py`:
  persistencia durable de job, versión y latest-by-release.
- Modificar `app/back/src/rag_platform/api/schemas.py`: agregar
  `ReleaseBuildJobSchema` y mapper desde snapshot.
- Modificar `app/back/src/rag_platform/api/router.py`: cambiar `POST /build` a
  `202` y agregar `GET /build-status`. Agregar `GET /build-status/wait` solo si
  la implementación demuestra que reduce carga frente a refresh adaptativo simple.
- Modificar `app/back/tests/rag_platform/test_platform_api.py`: contratos HTTP
  de enqueue, replay, status, refresh controlado si aplica, error y scope.
- Crear `app/back/tests/rag_platform/test_release_build_jobs.py`: contrato de
  dominio/aplicación del job.
- Modificar `app/back/tests/ingestion/test_gui_server.py`: regresión del bridge
  para que errores sigan llegando como envelope, no socket cortado.

### Frontend

- Modificar `app/front/src/features/platform/platformApi.ts`: agregar
  `listAllVariants`, `listAllReleases`, `startReleaseBuild`,
  `getReleaseBuildStatus` y, solo si existe endpoint wait, `waitReleaseBuildStatus`.
- Modificar `app/front/src/features/platform/platformTypes.ts`: exponer los
  aliases generados del nuevo schema de job.
- Crear `app/front/src/features/platform/shared/useAdaptiveBuildStatusRefresh.ts`:
  hook de refresh controlado, abortable, visibility-aware, con backoff, timeout y
  botón manual. Puede usar `GET build-status` o `GET build-status/wait` si ese
  endpoint se implementa.
- Crear `app/front/src/features/platform/shared/platformPipelineState.ts`: adapter
  de documentos/corpus/variants/releases/job a estado de pipeline compartido.
- Crear `app/front/src/features/platform/shared/platformPipelinePanels.tsx`:
  composición de paneles/tokens legacy con datos Platform.
- Modificar `app/front/src/features/platform/releases/useRagReleaseWorkspace.ts`:
  cambiar build síncrono por enqueue + status visible + refresh terminal
  controlado; cargar releases, variants y snapshots completos.
- Modificar `app/front/src/features/platform/releases/BuildReport.tsx` y
  `ReleaseLifecycle.tsx`: renderizar `queued/running/succeeded/failed` sin fingir
  que el build muta directamente el lifecycle.
- Modificar `app/front/src/features/platform/variants/useVariantMatrixWorkspace.ts`:
  dejar de depender de página 1 para variants.
- Modificar `app/front/src/features/platform/documents/DocumentIntakeWorkspace.tsx`,
  `corpus/CorpusSnapshotWorkspace.tsx`, `variants/VariantMatrixWorkspace.tsx`,
  `releases/RagReleaseWorkspace.tsx` y `PlatformWorkspace.tsx`: recomponer con
  paneles compartidos donde reduzca duplicación real.
- Modificar `app/front/src/styles/platform.css`: solo tokens/ajustes compartidos;
  sin parches visuales por pantalla que dupliquen legacy.

### Documentación

- Crear o modificar `docs/runbooks/platform-release-build.md`: flujo operativo,
  estados, errores, reintentos, recuperación y verificación.
- Mantener este archivo como plan fuente; no crear planes paralelos para la misma
  ejecución.

## 8. Tareas ejecutables

> **For agentic workers:** REQUIRED SUB-SKILL: usar
> `superpowers:subagent-driven-development` o `superpowers:executing-plans`.
> Cada tarea exige TDD: prueba fallida, implementación mínima, prueba focalizada,
> regresión afectada y revisión de seguridad/trazabilidad.

### Task 1: Fase A backend, contrato de job asíncrono durable

**Archivos:** `release_build_job.py`, `release_build_job_service.py`,
`test_release_build_jobs.py`, `test_platform_api.py`.

**Interfaces producidas:**

```python
class ReleaseBuildJobState(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
```

```python
@dataclass(frozen=True)
class ReleaseBuildJobSnapshot:
    job_id: str
    rag_release_id: str
    project_id: str
    state: ReleaseBuildJobState
    version: int
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    report: dict[str, object] | None
    error: dict[str, object] | None
```

- [ ] Escribir tests de aplicación: start deja job `queued`, replay con misma
  idempotency key devuelve el mismo job, otra intención con misma key falla
  fail-closed, runner marca `running/succeeded/failed` incrementando `version`.
- [ ] Escribir tests HTTP: `POST /build` responde `202`, `GET /build-status`
  devuelve latest, errores se devuelven como envelope/snapshot estructurado y
  reintentos idempotentes no duplican trabajo.
- [ ] Implementar repo in-memory con versión monotónica, latest-by-release y
  runner drenable para tests determinísticos.
- [ ] Ejecutar:

```bash
npm run python -- -m pytest app/back/tests/rag_platform/test_release_build_jobs.py app/back/tests/rag_platform/test_platform_api.py -q
```

### Task 2: Runner, wiring y persistencia durable

**Archivos:** `dependencies.py`, `services.py`, `router.py`,
`release_build_service.py`, repos Postgres/in-memory.

- [ ] Escribir test de wiring de `RagPlatformServices` para los tres casos de uso
  de job.
- [ ] Cambiar `POST /api/platform/releases/{rag_release_id}/build` a `202` y
  response model `ReleaseBuildJobSchema`.
- [ ] Agregar `GET /build-status`. Si se decide añadir `GET /build-status/wait`,
  validar `wait_ms` con cota dura (por ejemplo 1_000 a 30_000 ms) y
  `after_version >= 0`; si no se añade, documentar que el refresh adaptativo usa
  únicamente status bajo demanda.
- [ ] Ejecutar el build real solo en el runner. El runner traduce excepciones a
  error estructurado; no guarda secretos, chunks raw ni vectores en el snapshot.
- [ ] En Postgres, persistir latest-by-release, idempotency key, estado, versión,
  timestamps, reporte resumido y error sanitizado.
- [ ] Ejecutar:

```bash
npm run python -- -m pytest app/back/tests/rag_platform -q
npm run python -- -m pytest app/back/tests/ingestion/test_gui_server.py -q
```

### Task 3: Carga completa/paginada para variants/releases y build UX controlada

**Archivos:** `platformApi.ts`, `platformTypes.ts`,
`useAdaptiveBuildStatusRefresh.ts`, `useRagReleaseWorkspace.ts`, tests de Platform.

- [ ] Escribir tests de API: `listAllVariants` y `listAllReleases` recorren todas
  las páginas; `startReleaseBuild/getReleaseBuildStatus` llaman endpoints
  correctos. Si existe endpoint wait, cubrir también `waitReleaseBuildStatus`.
- [ ] Implementar `useAdaptiveBuildStatusRefresh` con estas reglas: solo activo
  para release visible en `queued`/`running`, un request activo, abort al cambiar
  `resourceId`, pausa con `document.hidden`, backoff tras timeout, parada en
  `succeeded/failed`, botón manual, error visible y sin `setInterval` rígido.
- [ ] Cambiar `useRagReleaseWorkspace`: `build()` encola, guarda job, muestra
  estado, inicia refresh controlado si aplica, refresca la release al terminal y
  conserva idempotencia por intento.
- [ ] Reemplazar lecturas de página 1 por `listAllReleases/listAllVariants` en
  releases y variants.
- [ ] Ejecutar:

```bash
npm --prefix app/front run test
npm --prefix app/front run build
```

### Task 4: Reuso real de la lane legacy sin acoplarla a Platform

**Archivos:** `pipelineState.ts`, `pipelineFlow.ts`,
`platformPipelineState.ts`, `platformPipelinePanels.tsx`, workspaces Platform.

- [ ] Escribir regresión de legacy antes de tocar compartidos: embedding/indexing
  siguen renderizando y sus hooks siguen usando `usePollingLoop`.
- [ ] Extraer solo contratos neutrales: stages, badges, severidad, progreso,
  errores y paneles. No importar estado de Platform dentro de legacy.
- [ ] Implementar adapters Platform que consumen datos Platform y producen estado
  compartido. El adapter conserva `project_id`, `rag_release_id`, `job_id` y
  `version` para auditoría.
- [ ] Parametrizar el flujo reutilizado por `project_id`: no asumir corpus global
  único, no leer preferencias legacy de corpus, y no cruzar documentos/snapshots
  entre proyectos.
- [ ] Recomponer Documents, Corpus, Variants y Releases reemplazando bloques
  visuales duplicados por paneles compartidos. No tocar lógica que ya quedó verde
  salvo para conectar el adapter.
- [ ] Añadir o actualizar el E2E de Platform para probar el flujo con
  `rag_release_id`: seleccionar proyecto, usar su corpus/snapshot, crear variante,
  construir release y verificar que el estado/resultados pertenecen a esa release.
- [ ] Ejecutar:

```bash
npm --prefix app/front run test
npm --prefix app/front run build
```

### Task 5: Runbook, accesibilidad y cierre

**Archivos:** runbook, CSS Platform, tests UI.

- [ ] Documentar flujo operativo:
  `draft -> build queued/running -> succeeded -> validate -> publish`.
- [ ] Documentar recuperación: recargar página usa `GET build-status`; si el
  refresh controlado vence o falla, la UI muestra estado actual, permite refresh
  manual y no valida ni publica.
- [ ] Probar botones y estados con roles accesibles: busy deshabilita acciones,
  errores se anuncian, estados terminales quedan visibles.
- [ ] Ejecutar verificación mínima final:

```bash
npm run python -- -m pytest app/back/tests/ingestion/test_gui_server.py -q
npm run python -- -m pytest app/back/tests/rag_platform -q
npm --prefix app/front run test
npm --prefix app/front run build
```

## 9. Riesgos y mitigaciones

- **Sobrecarga por consulta periódica:** mitigado con refresh adaptativo, un
  request vivo como máximo, solo para release visible en `queued`/`running`, pausa
  por visibilidad, timeout y backoff. Prohibido usar `setInterval` rígido para
  Platform build status.
- **SSE/WebSockets prematuros:** descartados por ahora. `AsgiBridge` bufferiza
  ASGI; forzar streaming real sería más riesgoso que status bajo demanda +
  refresh adaptativo.
- **Acoplar legacy a Platform:** mitigado con adapters Platform-owned. Legacy no
  importa tipos Platform; Platform consume contratos compartidos.
- **Cambio de contrato de build:** mitigado con `202 + ReleaseBuildJobSchema`,
  idempotencia explícita, runbook y tests HTTP.
- **Persistencia inconsistente:** mitigado con `version` monotónica, latest
  by-release, replay idempotente y error sanitizado.
- **Corpus grande:** `collectAllPages` sirve para hasta miles con cota; selección
  masiva debe distinguir "página visible" de "todos los elegibles cargados".

## 10. Definition of Done

- Platform gestiona el pipeline RAG completo por `project_id` reutilizando piezas
  legacy sin duplicar tablas/formularios ad-hoc innecesarios.
- El flujo probado en legacy para un corpus queda soportado en Platform para
  múltiples proyectos con corpus distintos, sin depender del corpus global legacy.
- Documents, Corpus, Variants y Releases cargan todas las páginas requeridas o
  muestran paginación explícita; no vuelven a quedarse en los primeros 25.
- La selección masiva respeta `needs_review`: nunca auto-incluye revisiones que
  requieren decisión explícita.
- `variant-matrix` y `releases/build` responden siempre con envelope o snapshot
  estructurado; nunca socket cortado como comportamiento esperado.
- Build no bloquea el request HTTP; estado y errores son observables, auditables
  y recuperables tras recarga.
- No hay consulta agresiva de Platform build status; solo status bajo demanda,
  refresh manual y auto-refresh adaptativo mientras la release visible esté
  `queued`/`running`.
- La lane legacy queda intacta y sus tests siguen verdes.
- Contratos de Fase 7 siguen cerrados: sin fuga de `actor_id`,
  `indexing_target_id`, rutas físicas, secretos, chunks raw ni vectores.
- El E2E de Platform pasa con una release identificada por `rag_release_id`,
  demostrando que build/validate/publish operan sobre el proyecto y corpus
  correctos.
- Runbook actualizado y verificación focalizada + build frontend ejecutados.

## 11. Verificación final requerida

```bash
npm run python -- -m pytest app/back/tests/rag_platform -q
npm run python -- -m pytest app/back/tests/ingestion/test_gui_server.py -q
npm --prefix app/front run lint
npm --prefix app/front run test
npm --prefix app/front run build
```

E2E manual en modo Postgres con `sst-general` (55 documentos): listar completo,
seleccionar elegibles, normalizar, snapshot, variante, build, validate y publish
sin caída de socket, sin consulta agresiva y sin fuga de datos sensibles.

## 12. Self-review del plan

- Cobertura de `continuation.md`: se incorporan job asíncrono, status durable,
  full-data loading, reuso legacy, runbook y verificación final.
- Corrección frente a la preocupación de sobrecarga: el plan reemplaza consulta
  agresiva por status bajo demanda y refresh adaptativo.
- Cobertura de este plan original: se preservan D-1, D-2, D-3, D-4, no-objetivos,
  fail-closed, trazabilidad y separación Legacy/Platform.
- No quedan marcadores de conflicto ni planes paralelos requeridos para ejecutar.
