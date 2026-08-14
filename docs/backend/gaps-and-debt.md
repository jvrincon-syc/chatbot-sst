# Gaps y deuda visible

## Propósito

Este documento consolida la deuda estructural y las inconsistencias que hoy se
pueden verificar desde el código comprometido y la documentación versionada. No
es una lista teórica de mejoras: cada punto debe estar respaldado por la rama
actual.

## Concentraciones de complejidad

### Ingesta

- [pipeline.py](../../app/back/src/ingestion/pipeline.py)
  concentra inventario, selección de documentos, ejecución de lectura,
  construcción de metadata, validación, logging y promoción. Aunque hay módulos
  auxiliares, sigue siendo un punto de acoplamiento fuerte para la Fase 1.
- Diagnóstico actual de `pipeline.py`:
  - El archivo actúa como orquestador de punta a punta de Fase 1: arranca con
    `scan_docs_raw`, filtra `only_sources`, decide `skip/reuse`, ejecuta lectura
    con readers locales o Llama, escribe artefactos, arma `inventory.json`,
    `needs_review.json`, `errors.json`, corre `validate_normalized_tree` y, si
    aplica, ejecuta `promote_candidate`.
  - La dependencia fan-in es alta: en el mismo módulo conviven OCR, readers PDF,
    clasificación, extracción de control documental, Llama adapters,
    fingerprinting, schemas de artefactos, manifests y promoción. Eso hace que
    una decisión de infraestructura termine tocando el mismo archivo que una
    regla documental o una política de observabilidad.
  - El `run_pipeline` vigente mezcla tres niveles de responsabilidad en un mismo
    flujo: coordinación de corrida, reglas por documento y persistencia de
    salidas/manifests. El resultado es que la Fase 1 es auditable, pero no
    especialmente modular para evolucionar.
  - Hay deuda visible y concreta: `_run_pipeline_legacy` conserva una copia
    muerta del flujo antiguo detrás de un `raise RuntimeError("legacy pipeline helper removed")`.
    Ese bloque no se ejecuta, pero sí aumenta el costo de lectura y confunde qué
    parte del archivo es autoridad real hoy.
  - Riesgo operativo: cualquier ajuste de thresholds, warnings materiales,
    clasificación, promotion gate o formato de manifests tiene radio de impacto
    amplio porque ocurre dentro del mismo entrypoint.
  - Qué separación ayudaría más: extraer un planner de corrida
    (inventario/selección), un executor por documento
    (read -> normalize -> classify -> extract -> validate local), un writer de
    manifests agregados y un coordinador de validación/promoción final.
- [server.py](../../app/back/src/ingestion/gui/server.py)
  mezcla composición backend, endpoints HTTP heredados, settings operativos,
  bridge hacia chunking y wiring del backend bundle-first.
- Diagnóstico actual de `server.py`:
  - El archivo no solo sirve la GUI de ingesta: también hace bootstrap del
    proceso backend, carga `secrets.env`, configura logging, crea el bridge de
    chunking, construye `PipelineServices`, corre reconciliación de indexing y
    embedding, monta `FastAPI` vía `AsgiBridge` y luego expone todo con
    `ThreadingHTTPServer`.
  - El routing HTTP es manual. `do_GET` y `do_POST` discriminan rutas con
    `path == ...` y `startswith(...)`, y el mismo handler implementa al menos
    nueve operaciones distintas: upload, review, pipeline run, settings,
    validate, promote, chunking GET/POST y forward de embedding/indexing/retrieval.
  - También centraliza detalles que podrían vivir aparte: CORS manual, parsing
    JSON, parsing multipart, lectura/escritura de `review_decisions.json`,
    lectura/escritura de `gui_settings.json`, construcción del status payload y
    formateo de respuestas HTTP.
  - El archivo hoy cumple dos roles tensos entre sí: shell operativa de Fase 1
    y gateway local hacia las capacidades bundle-first. Funciona, pero obliga a
    entender dos modelos HTTP distintos en el mismo proceso: uno basado en
    `BaseHTTPRequestHandler` y otro en `FastAPI`.
  - Riesgo operativo: agregar una política horizontal nueva
    (auth, rate limiting, tracing, CORS más amplio, headers comunes, errores
    uniformes) implicaría tocar el server heredado y revisar el bridge hacia la
    API moderna para no dejar comportamientos divergentes.
  - Qué separación ayudaría más: aislar `main()` y la composición de proceso,
    mover settings/review/status a módulos dedicados y reducir el handler a una
    capa de dispatch o, idealmente, decidir explícitamente si esta GUI seguirá
    siendo gateway principal o solo shell local de Fase 1.

### Composición bundle-first

- [dependencies.py](../../app/back/src/api/dependencies.py)
  es un composition root razonable, pero ya concentra wiring de `embedding`,
  `indexing`, `retrieval`, transacciones, search ports y observabilidad de
  startup.
- Diagnóstico actual de `dependencies.py`:
  - Como composition root, el archivo está bien orientado: resuelve flags,
    `ConsumerScope`, persistence mode y mantiene la política `fail-closed`
    cuando PostgreSQL es requerido. El problema no es su existencia, sino el
    volumen de wiring que ya acumuló.
  - `build_pipeline_services()` decide dos lanes completos
    (`memory` y `postgres`) dentro del mismo bloque y construye repositorios,
    transactions, vector search, lexical search, parent expansion, builders,
    readiness evaluators, executors, activadores y validadores para tres
    dominios a la vez.
  - `PipelineServices` es práctico para el HTTP layer, pero también funciona
    como "service bag" transversal: expone casos de uso, read services,
    executors, reconciler, activation/rollback, retrieval lifecycle y conexión
    abierta en una sola estructura.
  - `build_pipeline_services_from_env()` agrega otra capa de concentración:
    resuelve entorno, abre la conexión psycopg, decide si la app arranca o falla
    cerrada y emite observabilidad de startup. Es decir, composición, política
    de arranque y side effects de infraestructura viven en el mismo módulo.
  - Riesgo operativo: cualquier nueva capacidad bundle-first o nuevo backend
    storage path tocará el mismo archivo y obligará a revisar dos ramas
    completas (`memory`/`postgres`), más la telemetría de startup.
  - Qué separación ayudaría más: composition roots por capacidad
    (`embedding`, `indexing`, `retrieval`) o por lane (`memory`, `postgres`), y
    un bootstrapper aparte para entorno/conexión/observabilidad. Eso preservaría
    el fail-closed sin volver el wiring central todavía más denso.

### CLIs y orquestación durable

- [run_indexing.py](../../scripts/indexing/run_indexing.py)
  mezcla parsing CLI, guards productivos, construcción de componentes
  PostgreSQL, emisión de eventos, filtrado de elegibilidad y el loop de
  indexación.
- Diagnóstico actual de `run_indexing.py`:
  - El script no es un wrapper fino. Empieza resolviendo `sys.path`, parsea
    argumentos, lee entorno, bloquea escrituras PostgreSQL si falta
    `--persist-confirmed`, valida DSN, lee `inventory.json`, carga
    `review_decisions.json`, aplica `IndexingEligibilityService`, resuelve
    perfiles, abre conexión psycopg, decide guards de provider live, indexa,
    emite observabilidad y finalmente hace commit/rollback.
  - Hay un acoplamiento transversal visible: el CLI de indexing depende de
    `ingestion.gui.review_store` para leer decisiones humanas de revisión. Eso
    revela que parte del contrato operativo de indexación sigue viviendo en un
    módulo de GUI/ingesta y no en un puerto o repositorio neutral.
  - También hay mezcla de niveles: control operatorio (`--dry-run`,
    `--persist-confirmed`), política productiva
    (`unsupported_live_embedding_provider`, `voyage_api_key_missing`),
    preparación de infraestructura PostgreSQL y loop de negocio con
    `LlamaIndexingPort` conviven en el mismo entrypoint.
  - Riesgo operativo: si la lógica de elegibilidad, perfil o persistencia cambia
    en la API bundle-first y no se extrae a un servicio compartido, este CLI
    puede derivar en drift funcional respecto al camino HTTP.
  - Otro síntoma de deuda es el bootstrap manual con `sys.path.insert(...)`,
    típico de scripts que todavía cargan demasiada responsabilidad de
    integración y necesitan "armarse" el runtime a mano.
  - Follow-up pendiente de bajo riesgo: extraer la lectura de
    `review_decisions.json` fuera de `ingestion.gui.review_store` hacia un
    módulo o repositorio neutral consumible tanto por la GUI como por los CLIs
    de indexing.
  - Qué separación ayudaría más: dejar el script como adaptador CLI puro y mover
    guards, elegibilidad agregada, orquestación transaccional y resolución de
    perfiles a una capa application reutilizable por CLI y por servicios
    backend.

## Desbalance documental actual

- `ingestion`, `llama_first`, `observability` y parte de `chunking` ya tenían
  documentación útil antes de esta iniciativa.
- `embedding`, `indexing` y `retrieval` dependen mucho más del código y de un
  handoff API puntual que de READMEs operativos propios.
- parte de la navegación documental del repo sigue repartida entre `README.md`,
  `docs/README.md`, `CLAUDE.md`, `memory/`, `plans/` y notas históricas.

## Superficies HTTP aún fragmentadas

- La GUI de ingesta mantiene un servidor propio con `ThreadingHTTPServer` y
  bridge ASGI.
- La API bundle-first vive en FastAPI y no reemplaza todavía toda la superficie
  operativa de la GUI.
- Esto es funcional, pero incrementa el costo mental de seguir el flujo
  completo y el contrato HTTP total del repo.

## Inconsistencias documentales detectadas

- parte de la documentación histórica menciona comandos o rutas de verificación
  que no siempre existen hoy; `CLAUDE.md` ya documenta algunos de esos desvíos.
- varios documentos mezclan estado actual con intención futura si no se leen en
  conjunto con ADRs, tests y código.
- hay mezcla de español e inglés, especialmente entre observabilidad y algunos
  contratos técnicos.

## Gaps funcionales explícitos

- no existe todavía una capa final de respuesta/chat SST documentada y
  versionada por encima de `retrieval`; el repo llega hasta evidencia
  recuperable, perfiles y readiness.
- Redis aparece como configuración disponible, pero no como superficie backend
  principal comparable a PostgreSQL o filesystem en la ruta versionada actual.
- la unificación completa entre GUI heredada y API bundle-first todavía no está
  lograda.
- la deuda de archivos grandes en orquestación sigue presente incluso cuando las
  capacidades ya están mejor separadas que en iteraciones anteriores.

## Duplicación o scattering visible

- el estado del pipeline se describe en múltiples lugares: READMEs, ADRs,
  runbooks, handoffs API y notas históricas.
- la resolución de configuración PostgreSQL aparece en más de un entrypoint,
  aunque con contratos compatibles.
- las reglas de eligibility, readiness y activación viven correctamente
  separadas por dominio, pero para seguir un caso real hay que saltar entre
  varios módulos y docs.

## Qué falta para llegar al objetivo operativo

- una capa documental uniforme por área, con la misma plantilla mínima.
- una separación más clara entre documentación canónica versionada y notas
  locales o históricas.
- reducir concentración de lógica en los entrypoints más grandes si el equipo
  decide atacar deuda de código, no solo deuda documental.
- completar la historia operativa que va desde retrieval hasta una respuesta
  verificable de chatbot SST si ese tramo ya existe fuera de esta rama o se va a
  construir después.

## Cómo interpretar esta deuda

Estos hallazgos no significan que el repo esté incoherente; significan que hoy
la arquitectura y la documentación no tienen el mismo grado de uniformidad en
todas las fases. La documentación canónica debe dejar eso explícito en vez de
suponer una homogeneidad que el código aún no tiene.

## Deuda registrada (2026-08-14) — calidad de chunking/retrieval y prueba de release

Detectada durante el end-to-end local de plataforma (`app/back/tests/rag_platform/
test_end_to_end_local_platform.py`). El retrieval rankea bien (BGE-M3 + cosine), pero
hay mejoras genéricas (multi-proyecto, no del test) diferidas **antes de Fase 7**:

1. **`section_title` + `section_path` desde chunking** (no solo indexing). El parser ya
   captura `StructuralBlock.heading_path`, pero no llega al `ChildChunk` ni al nodo:
   `indexing_nodes.section_title/section_path` quedan NULL. Propagar desde chunking →
   sealed bundle → `build_nodes`. **Prioridad alta**; enabler de #4.
2. **Dedup como diversidad del candidate set** en retrieval (no hard-delete físico). Hoy
   headers/boilerplate repetidos generan vectores idénticos que ocupan slots del top_k.
3. **`boilerplate_policy` configurable por perfil/proyecto** (refactor de capacidades
   existentes; no hardcode global). Excluir headers/código/campos de formulario del texto
   indexable según política del proyecto.
4. **Contexto estructural en el embedding**: prefijar la sección/heading al texto del child
   antes de embeder (reusar `ChildChunk.context_prefix`). **Más importante** — mejora la
   discriminación semántica del vector.
5. **Retrieval híbrido vector + lexical** (denso BGE + léxico/FTS con fusión). **Más
   importante** — robustez frente a consultas por término exacto/código.

**Prueba de release — CERRADA (2026-08-14).** El tramo de release
(corpus snapshot + `CreateRagReleaseDraft` + `BuildRagReleaseUseCase`) se corrió
end-to-end contra PostgreSQL limpio + BGE vivo y quedó verde:
`app/back/tests/rag_platform/test_end_to_end_release_build.py` verifica que
`embedding_runs.rag_release_id` **e** `indexing_runs.rag_release_id` se persisten con el
`rag_release_id` de la release construida. La corrida destapó y corrigió 5 bugs de
cableado de la lane de build (nunca ejecutada end-to-end); detalle en
`docs/superpowers/plans/Plan_Ajustado_Plataforma_RAG_MultiProyecto(3).md`
("Cierre de verificación — corrida real del build de release (2026-08-14)").
