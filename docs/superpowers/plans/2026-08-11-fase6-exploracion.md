# Fase 6 — Exploración: Publicación de catálogo y coexistencia legacy

- **Fecha**: 2026-08-11
- **Tipo**: exploración previa (ponytail) antes de escribir código
- **Alcance**: solo Fase 6 del plan maestro (líneas 544-583)

> Objetivo ponytail: publicación es una **transición de estado** más el wiring del
> composition root y observabilidad. El grafo de lifecycle y `PUBLISHED` ya existen
> (Fase 5). Fase 6 no añade artefactos ni toca la lane legacy; solo cablea, autoriza
> y emite eventos. Reusar al máximo, no reescribir.

---

## 1. Qué ya existe (reusar)

| Necesidad Fase 6 | Ya implementado | Ubicación |
| --- | --- | --- |
| Estado `PUBLISHED` + transición `VALIDATED→PUBLISHED` | `ReleaseState`, `ensure_transition_allowed` | `domain/lifecycle.py` |
| `RagRelease` con manifiesto congelado + actor/reason | `RagRelease`, `is_manifest_frozen` | `domain/lifecycle.py` |
| Persistencia de release + `update_state` | `RagReleaseRepository` | `application/release_service.py` |
| Autorización de operador (fail-closed) | `PlatformAccessPolicy.require_operator(actor_id)` | `application/context.py:34` |
| Feature flags con patrón `SST_FEATURE_*` | `FeatureFlags`, `_flag` | `core/feature_flags.py` |
| Composition root (registra servicios) | `PipelineServices`, `build_pipeline_services` | `api/dependencies.py:136,170` |
| Emisión de eventos estructurados + redacción de secretos | `emit_observability_event`, `ObservabilityEvent` | `core/logging/observability.py:177` |
| Logger estructurado | `get_logger` | `core/logging/logger.py:71` |

**Consecuencia:** `PublishRagReleaseUseCase` es un caso de uso de ~15 líneas
(autoriza → carga release → `ensure_transition_allowed(VALIDATED→PUBLISHED)` →
verifica manifiesto congelado → `update_state(PUBLISHED)` → emite evento).

## 2. Qué falta (crear, mínimo)

1. **`application/publication_service.py`** (nuevo):
   - `PublishRagReleaseUseCase.execute(rag_release_id, actor_id)`: transición
     transaccional `VALIDATED→PUBLISHED`, verifica `release_manifest_hash` presente
     (una DRAFT sin validar no se publica), autoriza vía `PlatformAccessPolicy`.
   - No importa `ConsumerScope`, `RetrievalProfile`, `ActivateIndexedBundleUseCase`
     ni escribe `is_active` (el test negativo lo verifica).

2. **`application/platform_access.py`** (nuevo, mínimo):
   - `PlatformActor` (dataclass: actor_id + project scope) y
     `PlatformAccessPolicy.require_project_operator(actor, project_id)`.
   - **Desajuste plan↔código:** ya existe `PlatformAccessPolicy` en `context.py` con
     `require_operator(actor_id)`. Ponytail: **no duplicar el Protocol**. Añado
     `PlatformActor` + una función de guarda `require_project_operator` en el módulo
     nuevo que se apoya en el policy existente; no creo un segundo Protocol con el
     mismo nombre. (Ver decisión D1.)

3. **Eventos de release** (`publication_service.py` + donde ya viven los casos):
   - `rag_release_created`, `rag_release_build_step_completed`,
     `rag_release_validated`, `rag_release_published`, `rag_release_retired`.
   - Ponytail: un helper `emit_release_event(logger, name, release)` que arma el
     `ObservabilityEvent` con `rag_release_id`/`project_id`/`state` en el contexto y
     delega en `emit_observability_event` (redacción de secretos ya incluida). No
     reimplementar logging.

4. **`core/feature_flags.py`** (modificar): añadir `rag_platform_v1: bool = False`
   leído de `SST_FEATURE_RAG_PLATFORM_V1`, **default off**, separado de los flags
   bundle-first. Una línea en `from_env` + un campo.

5. **`api/dependencies.py` / `api/app.py`** (modificar): registrar los servicios de
   plataforma en el composition root **solo cuando el flag está on**, sin tocar el
   wiring legacy de retrieval. El flag off = comportamiento actual byte-idéntico.

## 3. Decisiones (D)

### D1 — `PlatformAccessPolicy`: extender vs duplicar

- **Elegida: extender.** Ya existe el Protocol `require_operator(actor_id)`. Añado
  `PlatformActor` y una guarda `require_project_operator(*, policy, actor, project_id)`
  en `platform_access.py` que reusa el policy existente (autoriza operador y, si el
  actor trae scope de proyecto, valida que coincida). No creo un Protocol nuevo con
  el mismo nombre (rompería los 4 consumidores actuales). El plan lista el archivo;
  lo creo con contenido aditivo, no un duplicado.

### D2 — Publicación transaccional

- `update_state` ya aplica la transición; envolver en `transaction()` (el
  `TransactionManager` que usa el resto de la plataforma). Fail-closed: si el
  manifiesto no está congelado (`release_manifest_hash is None`) o el estado no es
  `VALIDATED`, se rechaza antes de tocar la BD.

### D3 — Eventos: helper vs inline

- **Elegida: un helper** `emit_release_event`. Los 5 eventos comparten forma
  (nombre + release + status). Un helper evita repetir el armado de `ObservabilityEvent`
  cinco veces (DRY). `rag_release_created/validated` se emiten desde los servicios
  de Fase 5 (extensión mínima); `published/retired` desde Fase 6;
  `build_step_completed` desde el planner.

## 4. Principios / restricciones duras

- **Separación de semánticas:** `PUBLISHED` = catálogo acepta; **no** toca
  `is_active` ni `retrieval_profiles` ni el scope `chatbot/sst-default`. Test
  negativo obligatorio (inciso 4 + exit criteria).
- **Coexistencia legacy:** flag off ⇒ el runtime legacy no cambia. `Activate/Rollback`
  y `/api/retrieval` intactos. Se documenta que "seleccionar otra release publicada"
  NO es rollback de vector rows y queda fuera de este plan.
- **Fail-closed:** publicar sin validar, sin manifiesto o sin autorización se rechaza.
- **Sin secretos en eventos:** `emit_observability_event` ya redacta; el contexto de
  release solo lleva ids y estado, nunca contenido ni credenciales.

## 5. Tests a crear (pendientes de ejecución)

- `tests/rag_platform/test_publication_neutrality.py`: publicar transiciona a
  `PUBLISHED`; **no** escribe `is_active`, no crea `retrieval_profiles`, no usa el
  scope legacy; publicar sin validar/sin manifiesto/sin permiso falla cerrado; test
  negativo de imports (el módulo no importa `ConsumerScope`/`RetrievalProfile`/
  `ActivateIndexedBundleUseCase`).
- `tests/core/test_pipeline_composition.py`: flag off ⇒ servicios plataforma no
  registrados y wiring legacy intacto; flag on ⇒ servicios plataforma disponibles y
  retrieval legacy sin cambios.
- `tests/retrieval/test_pipeline_api.py`: `/api/retrieval` legacy responde igual con
  el flag on/off (comportamiento, no SQL byte-idéntico).

## 6. Orden de trabajo (dominio → app → infra/wiring)

1. Feature flag `rag_platform_v1` (core/feature_flags.py) + test de composición.
2. `platform_access.py` (`PlatformActor` + `require_project_operator`).
3. `publication_service.py` (`PublishRagReleaseUseCase`) + helper de eventos.
4. Wiring en `api/dependencies.py`/`app.py` gated por el flag.
5. Tests de neutralidad, composición y API legacy.
6. `docs/backend/phase-handoffs.md`: nota de coexistencia legacy.

## 7. Riesgos / deuda

- Migración `20260810_07` (Fase 5) sin aplicar en la BD de dev → aplicar antes de
  correr los `postgres_live`.
- El adaptador real de `RevisionArtifactResolver` (Fase 5) sigue pendiente; no
  bloquea Fase 6 (publicación opera sobre release ya construida/validada).
- Evento `build_step_completed`: se emite desde el planner de Fase 5; requiere pasar
  el logger al servicio (extensión mínima, sin cambiar su contrato de dominio).
