# Contrato HTTP de chunking local

## Proposito y alcance

`/api/chunking` permite ejecutar e inspeccionar el chunking local parent-child
sobre documentos ya normalizados e inventariados. Es una API de operacion e
inspeccion: no recibe archivos, no normaliza documentos y no genera embeddings,
indexacion, retrieval ni respuestas de chat.

La fuente de entrada es el inventario controlado de `docs_normalized`. Los
resultados exponen IDs, spans, paginas cuando estan disponibles, relaciones
parent-child, conteos de tokens, overlap, advertencias y enlaces relativos. Los
errores no exponen trazas, secretos ni rutas absolutas.

**No acepta rutas arbitrarias del filesystem.** Para ejecutar una corrida el
cliente solo puede enviar `document_ids` existentes en el inventario. La API no
tiene un campo de ruta de archivo ni un endpoint que lo reciba.

## Perfil soportado

`GET /api/chunking/profiles` devuelve los perfiles locales habilitados. En la
implementacion actual solo existe `local-structural-v1`:

| Campo | Valor |
|---|---:|
| `child_min_tokens` | 250 |
| `child_target_tokens` | 350 |
| `child_max_tokens` | 450 |
| `overlap_ratio` | 0.12 |
| `overlap_min_tokens` | 30 |
| `overlap_max_tokens` | 60 |

El tamano final de cada child incluye el overlap. Las excepciones de overlap
cero se reportan en `zero_overlap_reasons`; el contexto adicional, cuando
exista, se expone en `context_prefix`.

## Endpoints

| Metodo y ruta | Resultado |
|---|---|
| `GET /api/chunking/profiles` | Lista perfiles y sus limites de tokens y overlap. |
| `POST /api/chunking/runs` | Crea o reutiliza una corrida y responde `202 Accepted`. |
| `GET /api/chunking/runs/{run_id}` | Estado, progreso, advertencias y enlaces de inspeccion. |
| `GET /api/chunking/runs/{run_id}/documents` | Resultado por documento, paginado. |
| `GET /api/chunking/runs/{run_id}/validation` | Resumen de la validacion de la corrida. |
| `GET /api/chunking/documents/{document_id}/parents` | Parents del documento. |
| `GET /api/chunking/parents/{parent_id}/children` | Children ordenados de un parent. |

### Crear corrida

`POST /api/chunking/runs` requiere el header `Idempotency-Key` y recibe:

```json
{
  "scope": "documents",
  "document_ids": ["doc_123"],
  "profile_id": "local-structural-v1",
  "force": false
}
```

- `scope` admite `documents` o `corpus`.
- Con `documents`, `document_ids` no puede estar vacio y todos los IDs deben
  existir en el inventario.
- Con `corpus`, `document_ids` debe estar vacio; la corrida toma los IDs del
  inventario ordenados.
- `profile_id` debe ser un perfil expuesto por `/profiles`.
- `force` forma parte de la identidad de la solicitud.

La respuesta `202` contiene `run_id`, `status`, `profile_id`,
`requested_documents`, `completed_documents`, `warnings` y `links` relativos a
la corrida, sus documentos y su validacion. Los estados observables actuales son
`queued`, `running`, `completed`, `completed_with_warnings` y `failed`.

### Inspeccion de resultados

`GET /runs/{run_id}` devuelve el mismo resumen de corrida, incluido el progreso
por conteos. `GET /runs/{run_id}/documents` devuelve:

```json
{
  "items": [
    {
      "document_id": "doc_123",
      "status": "completed",
      "reused": false,
      "run_id": "...",
      "normalized_relpath": "..."
    }
  ],
  "page": 1,
  "page_size": 25,
  "total_items": 1,
  "total_pages": 1
}
```

`GET /runs/{run_id}/validation` informa `documents_checked`, `errors`,
`warnings` y `checks`.

Cada parent expone `chunk_id`, `document_id`, `profile_id`, `ordinal`, `text`,
`source_span` y `block_ids`. Cada child anade `parent_id`, `context_prefix`,
rangos y conteos de tokens, spans de overlap anterior y siguiente,
`zero_overlap_reasons` y `warnings`.

## Idempotencia y ejecucion

La clave `Idempotency-Key` identifica el payload efectivo: `scope`, IDs de
documento resueltos, perfil y `force`. La misma clave con el mismo payload
devuelve el mismo `run_id` y mantiene `202`; reutilizarla con un payload
distinto produce `409` con `CHUNKING_IDEMPOTENCY_CONFLICT`. La ausencia del
header produce `422` con envelope uniforme.

El estado se registra antes de enviar el trabajo. La ejecucion queda fuera de la
solicitud HTTP en un `ThreadPoolExecutor` con `max_workers=1`, por lo que una
sola corrida se procesa a la vez por instancia de aplicacion. El cliente debe
consultar `GET /runs/{run_id}` en vez de esperar el resultado de `POST`.

## Paginacion y limites

Solo el listado por corrida esta paginado: `page` tiene minimo `1`; `page_size`
tiene valor por defecto `25`, minimo `1` y maximo `100`. La respuesta informa
`total_items` y `total_pages`.

Los endpoints de parents y children devuelven listas completas: actualmente no
aceptan parametros de paginacion ni imponen un limite HTTP especifico de tamano
de respuesta. El request tampoco declara un maximo de IDs por corrida. Estos no
son limites garantizados por el contrato actual.

## Envelope de error uniforme

Los errores controlados usan este envelope:

```json
{
  "error": {
    "code": "CHUNKING_INVALID_REQUEST",
    "message": "request validation failed",
    "run_id": null,
    "details": {}
  }
}
```

`run_id` se informa cuando corresponde a una corrida conocida o solicitada.
`details.issues` contiene los errores de validacion para respuestas `422`.

| HTTP | Codigo | Condicion |
|---:|---|---|
| 400 | `CHUNKING_INVALID_REQUEST` | Combinacion semanticamente invalida de `scope` y `document_ids`. |
| 404 | `CHUNKING_DOCUMENT_NOT_FOUND` | `document_id` desconocido. |
| 404 | `CHUNKING_PROFILE_NOT_FOUND` | Perfil no soportado. |
| 404 | `CHUNKING_RUN_NOT_FOUND` | Corrida o reporte de validacion inexistente. |
| 404 | `CHUNKING_PARENT_NOT_FOUND` | Parent inexistente. |
| 404 | `CHUNKING_ROUTE_NOT_FOUND` | Ruta de chunking desconocida. |
| 409 | `CHUNKING_IDEMPOTENCY_CONFLICT` | Una clave representa otro payload. |
| 422 | `CHUNKING_INVALID_REQUEST` | Schema, rango o header invalido. |

Otros `HTTPException` se traducen a `CHUNKING_HTTP_EXCEPTION` con el mismo
envelope. Los endpoints tambien declaran el envelope para errores `500`, aunque
la implementacion no instala un manejador global para excepciones no
controladas.

## Diferencias relevantes frente al plan y DoD

- El DoD indica que los listados deben estar paginados. Solo
  `/runs/{run_id}/documents` lo esta; parents y children no tienen paginacion ni
  limite de respuesta.
- El estado se escribe como manifest antes de procesar, pero las consultas e
  indices de idempotencia viven en memoria. Tras reiniciar la aplicacion, el
  manifest no se recarga para `GET /runs/{run_id}` ni para reutilizar claves.
- La ruta `GET /documents/{document_id}/parents?run_id=...` valida que el
  `run_id` exista, pero no usa ese ID para seleccionar un resultado de esa
  corrida; lee el bundle asociado al documento.

El documento describe la implementacion actual. Las diferencias anteriores deben
resolverse en codigo antes de considerarlas garantias del DoD.
