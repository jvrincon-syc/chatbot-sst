# Plan — Rework de GUIs de Platform reutilizando la lane legacy (multi-proyecto)

- **Fecha**: 2026-08-21
- **Rama**: main
- **Área**: front (+ ajustes puntuales de back para defectos bloqueantes)
- **Estado**: PROPUESTA (solo diseño; sin ejecución)
- **Predecesor**: `docs/superpowers/plans/2026-08-20-fase8-gui-plataforma-plan.md` (Fase 8, CERRADA)

## 1. Problema

Fase 8 construyó las superficies de Platform (Projects, Variants, Documents,
Corpus, Releases) **desde cero**. La lane **Legacy pipeline** ya resuelve bien la
gestión del pipeline RAG de un corpus (ingesta → normalize → chunk → embed →
index → retrieval), con vistas maduras: shell con `view-switcher`, orquestación
por máquina de estados, polling de runs, paneles de run/estado/catálogo, tablas y
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
| `features/embeddingIndexing/shared/{pipelineState,pipelineFlow,usePollingLoop}` | Máquina de estados del pipeline + polling de runs | Orquestación de build/validate/publish por `project_id`/release |
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
- Arreglo probable: (a) endurecer el `AsgiBridge` para que toda excepción se
  convierta en respuesta con envelope (nunca cerrar el socket); (b) ejecutar el
  build **asíncrono/encolado** con estado consultable por polling (reusando
  `usePollingLoop`/`pipelineState` del legacy) en vez de bloquear el request.
- **Este defecto es prerrequisito**: la UI de Variants/Releases no se puede
  rehacer con confianza mientras la API se cae.

### D-4 · Estética/UX de las vistas Platform
- Se resuelve estructuralmente al reusar los componentes legacy (§4), no con
  parches cosméticos.

## 6. Fases propuestas (ejecución futura; aquí solo el esqueleto)

> Cada fase cierra con verificación del operador (tests + build); sin commit/push
> automático. TDD donde aplique.

- **Fase A — Desbloqueo backend (D-3).** Diagnóstico reproducible del *socket
  hang up*; endurecer `AsgiBridge` (excepción → envelope); mover el build a
  ejecución asíncrona con estado por polling. Tests de contrato del bridge.
- **Fase B — Data-layer compartido (D-1, D-2).** Paginación + selección masiva en
  los componentes de lista/tabla compartidos; adoptar en Documents/Corpus. Tests
  de paginación, "seleccionar todos" y gate `needs_review`.
- **Fase C — Generalizar componentes de etapa legacy.** Extraer run/estado/catálogo
  de `embedding/indexing/retrieval/chunking` + orquestación a una capa que acepte
  contexto de proyecto. Sin cambiar el comportamiento del legacy (regresión verde).
- **Fase D — Recomponer Platform sobre lo generalizado.** Reemplazar las vistas
  ad-hoc de `platform/{documents,variants,corpus,releases}` por composición de los
  componentes generalizados, alimentados por `platformApi`. Eliminar el código
  muerto de Fase 8 que quede sin uso.
- **Fase E — Pulido y consistencia.** Un solo lenguaje visual (tokens, shell,
  estados) entre legacy y Platform; a11y y responsive; runbook actualizado.

## 7. Riesgos

- **Acoplar legacy a Platform**: al generalizar, no romper la lane legacy (tiene
  su propia suite). Mitigación: la generalización es aditiva (contexto por props
  con default = comportamiento legacy actual); regresión legacy verde antes de
  recomponer.
- **Build asíncrono** cambia el contrato de `releases/build` (de síncrono a
  encolado): requiere decidir estado/polling y posiblemente un endpoint de estado
  de build. Documentar como decisión (ADR) si toca el contrato.
- **Paginación de corpus grande**: definir si la selección masiva opera sobre la
  página o sobre el total (dos semánticas distintas); elegir explícitamente.
- **Alcance**: la tentación de fusionar lanes. Mantener no-objetivo: siguen siendo
  superficies hermanas.

## 8. Definition of Done (de la ejecución futura, no de este plan)

- Platform gestiona el pipeline RAG completo por `project_id` reutilizando los
  componentes de la lane legacy; no quedan tablas/formularios ad-hoc duplicados.
- Intake/Corpus muestran el corpus completo (paginado) y permiten selección
  masiva con el gate `needs_review` intacto.
- `variant-matrix` y `releases/build` responden siempre con envelope (nunca
  *socket hang up*); el build no bloquea el servidor.
- La lane legacy queda intacta y etiquetada; sus tests siguen verdes.
- Contratos de Fase 7 sin regresión (sin fuga de actor/target físico; scope
  server-side; idempotencia).

## 9. Verificación (cuando haya código; la corre el operador)

- `npm --prefix app/front test` y `npm --prefix app/front run build`.
- Backend: suites de `rag_platform` y del bridge GUI afectadas + reproducción del
  build asíncrono.
- E2E manual en modo Postgres con `sst-general` (55 documentos): listar completo,
  seleccionar todos, normalizar, snapshot, variante, build → validate → publish
  sin caídas de socket.
