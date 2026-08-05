# Plan de trabajo ajustado — Observabilidad del backend `chatbot-sst`

> Estado: propuesta para revisión antes de implementación  
> Alcance: observabilidad operativa, auditoría durable, correlación, errores y métricas  
> Restricción principal: no cambiar la lógica funcional del backend

## 1. Objetivo

> Estado de ejecucion: implementado y validado en codigo.
> Evidencia principal: `docs/observability/current-contracts.md` y
> `docs/runbooks/backend-observability.md`.

Eliminar los procesos silenciosos del backend y permitir que un operador pueda supervisar en la terminal:

- arranque y apagado del servidor;
- solicitudes HTTP;
- ejecución de ingesta;
- extracción local y Llama-first;
- fallbacks;
- normalización;
- validación;
- revisión humana;
- promoción;
- chunking;
- embeddings;
- indexación;
- persistencia;
- rollback;
- cambios de estado;
- errores controlados e inesperados;
- métricas de duración y conteos.

La superficie operativa principal debe ser la terminal durante la ejecución del backend, especialmente con:

```bash
npm run gui:api
```

El trabajo no reemplazará los mecanismos existentes de auditoría, no eliminará los manifests y no modificará la lógica de negocio.

---

## 2. Evidencia del repositorio que gobierna este plan

La auditoría confirmó que el repositorio ya dispone de:

1. Un logger estructurado central en `app/back/src/core/logging/logger.py`.
   - Emite `INFO+` como JSON a stdout.
   - Emite `WARNING+` a un archivo rotativo.
   - Usa `propagate = False`.
   - Evita parcialmente handlers duplicados.
   - Tiene pruebas existentes.

2. Un `JsonlLogger` en `app/back/src/ingestion/logging/jsonl.py`.
   - Persiste el detalle de las corridas en `_details.log`.
   - Registra campos como `stage`, `event`, `status`, `warning_count` y `warning_code`.
   - Es consumido por pruebas de integración.
   - Cumple una función mixta de traza operativa y evidencia durable.

3. Manifests y contratos persistidos.
   - `RunManifest`.
   - `ReviewManifest`.
   - `ErrorManifest`.
   - Reportes de validación.
   - Manifests de chunking.
   - Repositorios JSONL de jobs de proveedor.
   - Estados documentales y decisiones humanas.

4. Observabilidad ya existente en varias zonas.
   - El pipeline registra selección, omisión, inicio, finalización y fallo por documento.
   - `LlamaOrchestrator` registra Parse, Classify y Extract.
   - Chunking ya registra gran parte del lifecycle, idempotencia, reutilización, conteos y persistencia de bundles.
   - Los CLI de indexación ya muestran parte de los bloqueos, dry-run, rollback y finalización.

Por tanto, este plan **extiende y unifica el motor existente**. No crea un sistema de logging paralelo.

---

## 3. Decisiones arquitectónicas

### 3.1 Conservar los tres canales actuales

```text
Logger central
    → observabilidad operativa en terminal

JsonlLogger / ledgers JSONL
    → traza durable de una ejecución

Manifests y estados persistidos
    → resultado oficial, reproducibilidad y auditoría
```

No se permitirá que stdout sustituya los manifests o JSONL.

### 3.2 No reemplazar el logger central

Se reutilizarán:

- `get_logger()`;
- `StructuredJsonFormatter`;
- handlers existentes;
- política actual de `propagate = False`.

Solo se ampliarán de forma compatible.

### 3.3 No eliminar ni convertir `JsonlLogger` en un sink exclusivo de stdout

`JsonlLogger` debe seguir persistiendo `_details.log`.

Podrá recibir eventos producidos por un contrato común, pero no debe perder su responsabilidad durable.

### 3.4 Introducir un contrato tipado mínimo antes de modificar GUI y CLI

Se creará un envelope pequeño, provisionalmente llamado `ObservabilityEvent`, para validar eventos nuevos y reducir payloads libres.

No será un motor nuevo ni una clase con decenas de parámetros opcionales.

Responsabilidades mínimas:

```text
schema_version
event
domain
status
message
context
metrics
attributes
```

El contrato debe poder mapearse tanto al logger central como a `JsonlLogger`.

### 3.5 Reutilizar los estados existentes

No se creará una nueva máquina de estados transversal.

Los eventos de transición usarán los estados ya definidos en:

- `DocumentStatus`;
- `RunDisposition`;
- `ProviderJobStatus`;
- `ReviewDecision`;
- `ChunkingRunState`;
- elegibilidad de indexación;
- servicios de reanudación.

### 3.6 Correlación incremental

Primera iteración:

- mantener `run_id`;
- mantener `document_id`;
- mantener `job_id`;
- mantener `upstream_job_id`;
- mantener `configuration_hash`, `profile_id` y proveedor cuando apliquen;
- generar `request_id` en el boundary HTTP;
- propagar `request_id` explícitamente en el flujo inmediato de la solicitud y en cualquier trabajo diferido que salga del request path, incluyendo tareas enviadas a `ThreadPoolExecutor`, jobs en segundo plano o workers asociados.

No se introducirán todavía:

- `trace_id` end-to-end;
- `contextvars`;
- filtros globales de contexto;
- propagación automática entre threads y tareas async.

La correlación automática transversal sigue fuera de alcance; la primera iteración solo garantiza handoff explícito del `request_id`.

Una correlación transversal automática requiere un ADR separado.

### 3.7 Versionado aditivo del esquema

Los eventos nuevos incluirán:

```text
schema_version = "1.0"
```

El campo se añadirá de forma compatible.

No se reescribirán archivos históricos ni se romperán lectores existentes.

Antes de añadir el campo a todos los eventos JSONL existentes, se verificará que sus consumidores toleren campos adicionales.

### 3.8 Salida de los CLI

Para CLI de indexación y chunking:

- stdout se reservará para el resultado final machine-readable del comando;
- stderr contendrá logs operativos estructurados en JSON;
- se eliminará progresivamente el texto humano improvisado de `basicConfig`;
- ambos canales usarán la misma taxonomía y schema;
- los códigos de salida se conservarán.

Para `npm run gui:api`, los logs operativos seguirán visibles en stdout mediante el logger central.

---

## 4. Alcance negativo

Este plan no incluye:

- reemplazar Python `logging`;
- introducir `structlog`;
- introducir OpenTelemetry;
- introducir Prometheus;
- introducir un stack externo de logs;
- cambiar estados de dominio;
- modificar la lógica de ingesta, chunking, embedding o indexación;
- eliminar `_details.log`;
- eliminar manifests;
- convertir todos los builders puros en emisores de logs;
- registrar texto completo de documentos, chunks, prompts o respuestas de proveedor;
- renombrar masivamente eventos existentes sin estrategia de compatibilidad;
- introducir `contextvars` sin ADR;
- convertir el backend actual a Uvicorn o FastAPI.

---

# 5. Fase 0 — Baseline y contrato de compatibilidad

## Objetivo

Congelar el comportamiento observable actual antes de modificarlo y evitar que la implementación rompa auditoría, tests o consumidores.

## Archivos a revisar

- `app/back/src/core/logging/logger.py`
- `app/back/src/ingestion/logging/jsonl.py`
- `app/back/src/ingestion/pipeline.py`
- `app/back/src/ingestion/application/services/llama_orchestrator.py`
- `app/back/src/chunking/application/run_service.py`
- `app/back/src/chunking/application/chunking_orchestrator.py`
- `scripts/chunking/run_chunking.py`
- `scripts/indexing/run_indexing.py`
- `scripts/indexing/validate_index.py`
- `scripts/indexing/prepare_postgres_indexing.py`
- `scripts/ingestion/run_inventory.py`
- `scripts/ingestion/validate_normalized.py`
- `scripts/ingestion/export_schemas.py`
- `scripts/ingestion/doctor_ocr.py`
- `scripts/evaluation/run_llama_first_benchmark.py`
- `scripts/experiments/check_llama_dependencies.py`
- `scripts/experiments/llama_cloud_smoke.py`
- pruebas asociadas.

## Tareas

- [ ] Inventariar todos los nombres de eventos existentes.
- [ ] Identificar cuáles eventos son contratos verificados por tests.
- [ ] Identificar consumidores de `_details.log`.
- [ ] Identificar consumidores de stdout JSON de los CLI.
- [ ] Registrar el formato actual de `logs/app.log`.
- [ ] Ejecutar pruebas focalizadas del logger, pipeline, chunking e indexación.
- [ ] Ejecutar una corrida controlada y guardar una muestra sanitizada de cada canal.
- [ ] Crear una tabla de compatibilidad:

| Contrato | Productor | Consumidor | Puede añadir campos | Puede cambiar nombre | Puede cambiar destino |
|---|---|---|---:|---:|---:|
| stdout logger | | | | | |
| `_details.log` | | | | | |
| manifests | | | | | |
| CLI stdout | | | | | |
| CLI stderr | | | | | |

## Entregable

`docs/observability/current-contracts.md`

## Criterio de salida

No iniciar la instrumentación hasta conocer qué eventos, archivos y formatos no pueden modificarse sin migración.

---

# 6. Fase 1 — Contrato estructurado mínimo y seguridad

## Objetivo

Formalizar eventos nuevos sobre el motor actual, añadir redacción central y evitar payloads arbitrarios.

## Archivos candidatos

- Crear: `app/back/src/core/logging/observability.py`
- Modificar: `app/back/src/core/logging/logger.py`
- Modificar condicionalmente: `app/back/src/ingestion/logging/jsonl.py`
- Crear: `app/back/tests/core/test_observability.py`
- Modificar: `app/back/tests/core/test_logging.py`
- Modificar o añadir pruebas de compatibilidad de JSONL.

## Contratos propuestos

```python
class ObservabilityEvent(BaseModel):
    schema_version: Literal["1.0"]
    event: str
    domain: ObservabilityDomain
    status: EventStatus
    message: str
    context: EventContext
    metrics: dict[str, int | float]
    attributes: dict[str, JsonScalar]
```

```python
class EventContext(BaseModel):
    request_id: str | None = None
    run_id: str | None = None
    document_id: str | None = None
    job_id: str | None = None
    upstream_job_id: str | None = None
    provider: str | None = None
    capability: str | None = None
    profile_id: str | None = None
    configuration_hash: str | None = None
```

La forma final debe ajustarse a los tipos y convenciones ya existentes en el repositorio.

## Tareas

- [ ] Definir `ObservabilityDomain`, `EventStatus` y tipos escalares JSON.
- [ ] Implementar un adaptador que convierta `ObservabilityEvent` a `logger.*(..., extra=...)`.
- [ ] Implementar un adaptador opcional hacia `JsonlLogger.event()` sin cambiar su persistencia.
- [ ] Añadir `schema_version` de forma aditiva y compatible.
- [ ] Crear una política central de redacción.
- [ ] Usar una allowlist de campos cuando sea viable.
- [ ] Redactar como mínimo:
  - `api_key`;
  - `token`;
  - `authorization`;
  - `secret`;
  - `signed_url`;
  - URLs firmadas;
  - prompts completos;
  - contenido de documentos;
  - texto de chunks;
  - payloads crudos.
- [ ] Añadir truncamiento defensivo para strings y colecciones.
- [ ] Mantener `exception_type` y stack trace solo donde corresponda.
- [ ] Añadir un helper de medición basado en `time.perf_counter()`.
- [ ] Confirmar que la configuración del logger sigue siendo idempotente.
- [ ] No crear un `ErrorContext` nuevo en esta fase.
- [ ] No crear una clase de dominio `StateTransition`.

## Pruebas mínimas

- [ ] Evento válido se serializa correctamente.
- [ ] Evento inválido falla antes de emitirse.
- [ ] Secretos se redactan.
- [ ] Contenido documental no se serializa.
- [ ] Strings largos se truncan.
- [ ] Configurar el mismo logger dos veces no duplica eventos.
- [ ] Excepciones preservan `exception_type`.
- [ ] `JsonlLogger` continúa escribiendo `_details.log`.
- [ ] Los lectores existentes aceptan `schema_version`.
- [ ] Los tests actuales del pipeline siguen pasando.

## Criterio de salida

El nuevo contrato debe reutilizar el motor actual y no cambiar el comportamiento funcional ni durable.

---

# 7. Fase 2 — Observabilidad del servidor GUI y boundary HTTP

## Objetivo

Eliminar `print()` del servidor operativo y permitir seguir cada request en la terminal.

## Archivos candidatos

- `app/back/src/ingestion/gui/server.py`
- pruebas nuevas en `app/back/tests/ingestion/test_server_observability.py`
- `package.json`
- `README.md`

## Eventos mínimos

```text
backend_process_started
backend_configuration_loaded
backend_ready
backend_shutdown_started
backend_shutdown_completed

http_request_started
http_request_completed
http_request_rejected
http_request_failed
```

La taxonomía definitiva debe mantener compatibilidad con los nombres existentes.

## Contexto HTTP

Cada request recibirá un `request_id`.

Campos mínimos:

```text
request_id
method
route
status_code
duration_ms
client_address_redacted
```

No registrar:

- body completo;
- headers completos;
- tokens;
- rutas con parámetros sensibles;
- archivos cargados;
- contenido documental.

## Tareas

- [ ] Reemplazar el banner de `print()` por un evento estructurado.
- [ ] Reemplazar `log_message()` basado en `print()` por el logger central.
- [ ] Generar `request_id` al entrar al handler.
- [ ] Propagarlo explícitamente a los métodos del handler que emiten logs.
- [ ] Propagar `request_id` a cualquier trabajo en segundo plano disparado por el handler, incluyendo tareas enviadas a `ThreadPoolExecutor`.
- [ ] Registrar duración de request.
- [ ] Registrar validaciones rechazadas como `WARNING`.
- [ ] Registrar fallos inesperados como `ERROR` con stack trace.
- [ ] Registrar shutdown limpio.
- [ ] Excluir o reducir ruido de health checks si existen.
- [ ] Mantener respuestas HTTP y códigos de estado sin cambios.
- [ ] Documentar que `gui:api` sigue siendo el comando real y que este plan no introduce un alias `api`.

## Edge cases mínimos

- JSON inválido.
- Body ausente.
- Tipo inválido.
- Ruta inexistente.
- Archivo rechazado.
- Decisión de revisión inválida.
- Fallo del bridge de chunking.
- Excepción inesperada.

## Criterio de salida

`npm run gui:api` debe mostrar inicio, requests, errores y apagado en formato estructurado sin crear una segunda infraestructura de logging.

---

# 8. Fase 3 — Gaps reales de ingesta, normalización y revisión

## Objetivo

Añadir únicamente los eventos ausentes identificados por la auditoría, sin duplicar eventos ya existentes.

## Archivos candidatos

- `app/back/src/ingestion/pipeline.py`
- `app/back/src/ingestion/application/services/llama_orchestrator.py`
- readers o adapters solo si el boundary actual no dispone del contexto necesario.
- `app/back/src/ingestion/gui/review_store.py` o servicio que persista decisiones, si corresponde.
- pruebas de integración de ingesta.

## Eventos existentes que deben conservarse

- `document_selected`
- `document_skipped`
- `document_start`
- `document_finished`
- `document_failed`
- eventos `llama_parse_*`
- eventos `llama_classify_*`
- eventos `llama_extract_*`

No duplicarlos con nombres alternativos.

## Eventos o resúmenes a añadir

```text
pipeline_run_started
pipeline_inventory_completed
document_fallback_activated
document_normalization_completed
document_validation_completed
document_review_required
review_decision_recorded
document_promotion_started
document_promotion_completed
pipeline_run_completed
pipeline_run_failed
```

## Tareas

- [ ] Añadir evento de inicio de run.
- [ ] Añadir conteo de inventario.
- [ ] Emitir evento explícito cuando cloud cae a local.
- [ ] Registrar ruta principal y ruta efectiva.
- [ ] Registrar el código del fallback, sin contenido sensible.
- [ ] Registrar parse parcial y OCR de baja confianza como warnings materiales.
- [ ] Registrar resumen de normalización.
- [ ] Registrar validación con conteos de findings.
- [ ] Registrar transición a `needs_review` usando estados existentes.
- [ ] Registrar decisión humana `approved` o `rejected`.
- [ ] Registrar promoción y resultado.
- [ ] Añadir resumen final del run.

## Métricas mínimas

```text
duration_ms
document_count
processed_count
needs_review_count
skipped_count
failed_count
warning_count
page_count cuando aplique
```

## Edge cases mínimos

- documento vacío;
- archivo sin extensión;
- PDF corrupto;
- MIME inválido;
- OCR requerido;
- OCR de baja confianza;
- parse parcial;
- fallback cloud/local;
- hash duplicado;
- documento ya procesado;
- campo crítico sin soporte;
- promoción fallida.

## LlamaOrchestrator

- [ ] No reescribir sus eventos.
- [ ] Añadir duración solo donde falte.
- [ ] Añadir un resumen final de la lane únicamente si aporta información no duplicada.
- [ ] Mantener `job_id`, `upstream_job_id`, `provider`, `capability` y `configuration_hash`.

## Criterio de salida

Un operador debe poder saber qué ruta siguió cada documento, por qué terminó procesado, en revisión o fallido, y cuánto tardó.

---

# 9. Fase 4 — Embeddings, indexación y persistencia

## Objetivo

Cerrar la zona más silenciosa del backend sin introducir logging en el dominio puro.

## Archivos candidatos

- `app/back/src/indexing/application/use_cases/index_document.py`
- `app/back/src/indexing/application/profile_orchestrator.py`
- `app/back/src/indexing/infrastructure/llama_index/pipeline_factory.py`
- factory concreto de embeddings.
- adapters concretos de embeddings.
- boundaries transaccionales de PostgreSQL.
- `scripts/indexing/run_indexing.py`
- `scripts/indexing/validate_index.py`
- `scripts/indexing/prepare_postgres_indexing.py`
- pruebas de indexación.

No instrumentar automáticamente cada método de repositorio si el boundary transaccional ya puede emitir un resumen completo.

## Eventos mínimos

```text
indexing_document_started
indexing_document_rejected
indexing_profile_resolved
indexing_profile_rejected
embedding_provider_selected
embedding_batch_started
embedding_batch_retrying
embedding_batch_completed
embedding_batch_failed
indexing_bundle_validated
indexing_nodes_built
indexing_persistence_started
indexing_persistence_committed
indexing_persistence_rolled_back
indexing_document_completed
indexing_document_failed
```

## Contexto mínimo

```text
run_id
document_id
profile_id
ingestion_origin
chunking_version
bundle_id o fingerprint disponible
embedding_provider
embedding_model
embedding_dimension
distance_metric
vector_table o colección lógica
```

## Métricas mínimas

```text
duration_ms
provider_latency_ms
batch_size
batch_index
embedding_count
parent_node_count
child_node_count
inserted_count
updated_count
deleted_count
stale_node_count
retry_count
```

## Tareas de embeddings

- [ ] Registrar proveedor y perfil seleccionado.
- [ ] Registrar modelo, dimensión y métrica.
- [ ] Registrar inicio y fin de cada batch, no cada vector.
- [ ] Registrar retry, timeout, rate limit y fallo.
- [ ] No registrar vectores.
- [ ] No registrar texto enviado al proveedor.
- [ ] Registrar respuesta malformada o dimensión incompatible.

## Tareas de indexación

- [ ] Registrar elegibilidad del documento.
- [ ] Registrar rechazo por `needs_review` u otro estado no permitido.
- [ ] Registrar perfil inactivo o lane incompatible.
- [ ] Registrar validación del bundle.
- [ ] Registrar fingerprint o versión esperada/recibida cuando aplique.
- [ ] Registrar creación de nodos.
- [ ] Registrar inicio de transacción.
- [ ] Registrar commit.
- [ ] Registrar rollback.
- [ ] Registrar conteos finales.
- [ ] Registrar validación posterior a persistencia cuando exista.

## Política de errores

Las excepciones deben registrarse una sola vez en el boundary donde se toma la decisión operativa final.

- Error esperado o bloqueo de negocio: `WARNING`.
- Unidad de trabajo no completada: `ERROR`.
- Fallo inesperado: `ERROR` con stack trace.
- Rollback exitoso: evento separado.
- No registrar el mismo stack trace en repositorio, caso de uso y CLI.

## Criterio de salida

Un operador debe poder diferenciar un documento rechazado, un embedding fallido, un perfil incompatible, un rollback y una indexación exitosa.

---

# 10. Fase 5 — Chunking: verificación y ajustes focalizados

## Objetivo

No reinstrumentar chunking. Confirmar visibilidad desde los entrypoints y cerrar únicamente gaps demostrados.

## Componentes ya cubiertos que deben conservarse

- conflictos de idempotencia;
- runs reutilizados;
- runs creados;
- runs iniciados;
- documentos completados;
- runs completados;
- runs fallidos;
- manifests omitidos;
- conteos de parsing estructural;
- conteos parent;
- conteos child;
- persistencia y reutilización de bundles;
- fallos del bridge GUI.

## Tareas

- [ ] Verificar que esos eventos aparecen al ejecutar chunking desde la GUI.
- [ ] Verificar que los campos se conservan al pasar por el logger central.
- [ ] Añadir `schema_version` de forma compatible.
- [ ] Añadir duración solo donde falte.
- [ ] Verificar estados `queued`, `running`, `completed`, `completed_with_warnings`, `interrupted` y `failed`.
- [ ] Añadir eventos solo para gaps confirmados, por ejemplo:
  - transición a `interrupted`;
  - validación final del bundle;
  - fingerprint incompatible;
  - page-trace no resuelto;
  - bundle corrupto.
- [ ] No registrar cada parent o child individual.
- [ ] No modificar builders puros si el orquestador puede registrar sus diagnósticos.

## Criterio de salida

Chunking conserva su contrato actual, evita duplicación y queda visible desde la superficie operativa principal.

---

# 11. Fase 6 — Normalización de CLI

## Objetivo

Eliminar la mezcla actual de `basicConfig`, texto humano y JSON, preservando la salida machine-readable de los comandos.

## Alcance

- `scripts/chunking/run_chunking.py`
- `scripts/indexing/run_indexing.py`
- `scripts/indexing/validate_index.py`
- `scripts/indexing/prepare_postgres_indexing.py`
- `scripts/ingestion/run_inventory.py`
- `scripts/ingestion/validate_normalized.py`
- `scripts/ingestion/export_schemas.py`
- `scripts/ingestion/doctor_ocr.py`
- `scripts/evaluation/run_llama_first_benchmark.py`
- `scripts/experiments/check_llama_dependencies.py`
- `scripts/experiments/llama_cloud_smoke.py`
- otros scripts solo si forman parte del flujo operativo principal.

## Decisión de canales

```text
stdout
    → resultado final JSON del comando

stderr
    → eventos operativos estructurados JSON
```

## Tareas

- [ ] Reemplazar `basicConfig()` ad hoc por configuración compartida.
- [ ] Mantener el JSON final de stdout.
- [ ] Transformar mensajes operativos de texto en eventos estructurados de stderr.
- [ ] Mantener códigos de salida.
- [ ] No mezclar varias líneas de logs con el objeto final de stdout.
- [ ] Añadir `run_id` cuando exista.
- [ ] Añadir `document_id`, `profile_id` y proveedor cuando apliquen.
- [ ] Añadir pruebas que capturen stdout y stderr por separado.
- [ ] Documentar el contrato para scripts y automatizaciones.

## Criterio de salida

Los CLI siguen siendo consumibles por scripts y al mismo tiempo muestran progreso estructurado en la terminal.

---

# 12. Fase 7 — Documentación, runbook y verificación final

## Archivos

- `README.md`
- Crear: `docs/runbooks/backend-observability.md`
- Crear o actualizar documentación de contratos.
- `package.json`

## Runbook mínimo

- cómo ejecutar `npm run gui:api`;
- cómo confirmar que `gui:api` es el entrypoint real del repo;
- cómo filtrar por `request_id`;
- cómo rastrear `request_id` también en trabajo diferido y en `ThreadPoolExecutor`;
- cómo seguir `run_id`;
- cómo seguir `document_id`;
- cómo seguir `job_id`;
- cómo reconocer fallback;
- cómo reconocer `needs_review`;
- cómo reconocer rollback;
- cómo activar nivel `DEBUG`;
- qué información nunca debe aparecer;
- diferencia entre stdout, stderr, `_details.log` y manifests;
- ejemplos sanitizados.

## Verificación automatizada

Ejecutar pruebas focalizadas de:

- logger;
- observability contract;
- redacción;
- pipeline;
- Llama;
- GUI server;
- chunking;
- embedding;
- indexing;
- CLI;
- manifests.

Después ejecutar la regresión backend afectada definida en `TESTING_AND_QUALITY.md`.

## Smoke tests manuales

### Caso 1 — Arranque

```bash
npm run gui:api
```

Debe mostrar:

- proceso iniciado;
- configuración cargada;
- servidor listo;
- host y puerto no sensibles.

### Caso 2 — Request inválido

Debe mostrar:

- `request_id`;
- warning de validación;
- status HTTP;
- duración.

### Caso 3 — Ingesta local exitosa

Debe mostrar:

- run;
- documento;
- fases;
- estado final;
- resumen.

### Caso 4 — Fallback Llama → local

Debe mostrar explícitamente:

- proveedor original;
- código del fallo;
- fallback seleccionado;
- estado final.

### Caso 5 — Documento a revisión

Debe mostrar:

- transición;
- reason code;
- warnings;
- resultado durable.

### Caso 6 — Chunking

Debe mostrar los eventos existentes sin duplicación.

### Caso 7 — Embedding e indexación exitosa

Debe mostrar:

- perfil;
- proveedor;
- batches;
- nodos;
- commit;
- resultado final.

### Caso 8 — Rollback

Debe mostrar:

- error original;
- rollback iniciado;
- rollback completado o fallido;
- estado final.

---

# 13. Política de niveles

## DEBUG

- decisiones internas detalladas;
- candidatos de configuración;
- cache lookup;
- conteos intermedios;
- diagnósticos de builders.

## INFO

- startup;
- inicio y fin de run;
- inicio y fin de fase;
- selección de proveedor;
- cambios de estado normales;
- batch completado;
- commit;
- finalización exitosa.

## WARNING

- fallback;
- `needs_review`;
- OCR de baja confianza;
- parse parcial;
- documento rechazado por estado;
- perfil inactivo;
- conflicto de idempotencia;
- retry;
- timeout recuperado;
- bundle reutilizado;
- validación de request fallida.

## ERROR

- documento no procesado;
- batch agotó retries;
- indexación fallida;
- transacción revertida;
- rollback fallido;
- request inesperadamente fallido;
- dependencia obligatoria indisponible.

## CRITICAL

Solo para un fallo que impida operar el backend con seguridad:

- configuración crítica inválida;
- corrupción de schema;
- dependencia oficial indisponible al arranque cuando no existe modo degradado.

---

# 14. Política de granularidad y ruido

Registrar por defecto:

- run;
- request;
- documento;
- fase;
- batch;
- transición;
- warning material;
- error;
- resumen.

No registrar por defecto:

- cada token;
- cada chunk;
- cada parent;
- cada child;
- cada vector;
- texto documental;
- prompt;
- respuesta cruda;
- cada query SQL.

Límites sugeridos, sujetos a configuración existente:

```text
max_attribute_string_length
max_exception_message_length
max_collection_preview
max_warning_examples
```

No introducir valores definitivos sin revisar la configuración actual.

---

# 15. Estrategia de commits

Cada fase debe dividirse en commits pequeños y reversibles.

Ejemplo:

```text
test(observability): lock current logging contracts
feat(observability): add typed event envelope
feat(logging): redact structured extra fields
feat(api): add structured request lifecycle logs
feat(ingestion): expose fallback and review transitions
feat(embedding): add batch lifecycle logs
feat(indexing): expose persistence and rollback events
refactor(cli): separate structured logs from JSON result
docs(observability): add backend runbook
```

No mezclar en un solo commit:

- schema;
- GUI;
- ingesta;
- embeddings;
- indexación;
- CLI;
- documentación.

---

# 16. Definition of Done

La tarea estará terminada cuando:

## Compatibilidad

- El logger central sigue siendo el motor operativo.
- `JsonlLogger` sigue escribiendo `_details.log`.
- Los manifests siguen funcionando.
- Los estados persistidos no cambian.
- Los tests existentes no se modifican para aceptar comportamientos incorrectos.

## Visibilidad

- `npm run gui:api` muestra startup, requests, fallos y shutdown.
- El fallback cloud/local es visible.
- La transición a revisión es visible.
- Embeddings e indexación dejan de ser silenciosos.
- Commit y rollback son distinguibles.
- Chunking no duplica eventos.

## Correlación

- Cada request tiene `request_id`.
- Los jobs que salen del request path conservan `request_id` mediante handoff explícito.
- Los runs mantienen `run_id`.
- Los documentos mantienen `document_id`.
- Los jobs mantienen `job_id`.
- La correlación automática transversal queda documentada para un ADR posterior, incluyendo `trace_id`, `contextvars` y propagación automática entre threads, async y CLIs.

## Seguridad

- No aparecen secretos.
- No aparece contenido documental completo.
- No aparecen chunks o vectores.
- Existen pruebas de redacción y truncamiento.

## Métricas

- Las fases principales exponen `duration_ms`.
- Los runs exponen resúmenes.
- Embeddings exponen batches y conteos.
- Indexación expone nodos y filas afectadas.

## CLI

- stdout conserva el resultado JSON final.
- stderr contiene logs estructurados.
- Los códigos de salida se mantienen.

## Calidad

- Type checking y lint pasan.
- Pruebas focalizadas y regresión afectada pasan.
- Hay un runbook.
- No quedan procesos silenciosos conocidos ocultos dentro del alcance acordado.

---

# 17. Decisiones que requieren ADR posterior

## ADR — Correlación automática transversal

Evaluar:

- `request_id`;
- `trace_id`;
- `contextvars`;
- propagación entre `ThreadingHTTPServer`;
- propagación hacia tareas async;
- propagación en CLIs;
- filtros de logging;
- integración futura con OpenTelemetry.

No debe bloquear la primera implementación.

## ADR opcional — Evolución del contrato de eventos

Solo si el schema debe convertirse en un contrato público entre procesos o herramientas externas.

---

# 18. Orden recomendado de implementación

1. Fase 0 — Baseline.
2. Fase 1 — Contrato mínimo y seguridad.
3. Fase 2 — Servidor GUI y HTTP.
4. Fase 3 — Ingesta y revisión.
5. Fase 4 — Embeddings e indexación.
6. Fase 5 — Verificación focalizada de chunking.
7. Fase 6 — CLI.
8. Fase 7 — Runbook y verificación.

No comenzar por chunking, porque la auditoría demostró que ya es una de las áreas mejor instrumentadas.

---

# 19. Handoff para implementación

Este plan debe ejecutarse con `superpowers:subagent-driven-development`.

Roles sugeridos:

- `baseline-auditor`: congelar contratos, pruebas y evidencia actual antes de tocar código.
- `http-observability-implementer`: servidor GUI, boundary HTTP y correlación inmediata.
- `background-correlation-implementer`: handoff explícito de `request_id` a `ThreadPoolExecutor` y jobs diferidos.
- `cli-normalization-implementer`: stdout, stderr y scripts silenciosos.
- `docs-runbook-writer`: README, runbook y ejemplos operativos.
- `task-reviewer`: revisar cada fase con foco en contrato y calidad.

Antes de ejecutar este plan, el agente principal debe:

1. Leer las reglas jerárquicas.
2. Leer la auditoría que originó este documento.
3. Verificar nuevamente rutas y líneas, porque el repositorio puede haber cambiado.
4. Ejecutar la Fase 0.
5. Detenerse si encuentra incompatibilidades no contempladas.
6. No reemplazar componentes existentes sin evidencia y ADR.
7. Implementar por fases con pruebas primero.

debe leer C:\Users\jvrincon\Documents\chatbot_sst\chatbot-sst\README_REGLAS.md,C:\Users\jvrincon\Documents\chatbot_sst\chatbot-sst\AGENTS.md,C:\Users\jvrincon\Documents\chatbot_sst\chatbot-sst\app\back\AGENTS_back.md
