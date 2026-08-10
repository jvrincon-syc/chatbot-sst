# Variables críticas y composición

## Propósito

Esta matriz resume las variables con impacto operacional real en la rama actual.
No reemplaza `secrets.example.env`, pero sí distingue qué configura cada lane y
qué riesgo trae un valor incorrecto.

## Reglas generales

- Las variables se leen en los bordes de composición; dominio y application no
  deberían leer entorno directamente.
- Un valor vacío no debe inventar compatibilidad ni habilitar un proveedor.
- Producción no debe degradar silenciosamente de PostgreSQL a memoria cuando el
  modo durable es requerido.
- Las claves y secretos nunca deben documentarse con valores reales.

## Matriz principal

| Grupo | Variables | Uso principal | Default observable | Riesgo operativo |
| --- | --- | --- | --- | --- |
| Persistencia | `SST_PERSISTENCE_MODE`, `SST_POSTGRES_DSN` | elegir lane `memory` o `postgres` para la composición bundle-first | `postgres` si hay DSN, si no `memory` | arrancar en un lane distinto al esperado o bloquear startup fail-closed |
| Consumer scope | `SST_CONSUMER_SCOPE_TYPE`, `SST_CONSUMER_SCOPE_ID` | scope controlado por servidor para activación/rollback | `chatbot` / `sst-default` | activar o desactivar perfiles para el scope equivocado |
| Feature flags | `SST_FEATURE_EMBEDDING_V2`, `SST_FEATURE_INDEXING_BUNDLE_FIRST`, `SST_FEATURE_RETRIEVAL_V1` | habilitar superficie bundle-first por capacidad | `false` | exponer rutas no listas o diagnosticar mal un `503` |
| Ingesta/OCR | `OCR_*`, `TESSERACT_*`, `OCRMYPDF_CMD`, `GHOSTSCRIPT_CMD` | pipeline local y OCR reforzado | varios defaults en `secrets.example.env` | clasificar mal PDFs escaneados o dejar estados ambiguos |
| Llama-first | `LLAMA_*` | lane cloud/experimental de parse, classify y extract | cloud desactivado por defecto | costos, orden inválido de stops o subida no autorizada |
| Embeddings runtime | `EMBEDDING_*`, `BGE_*`, `HF_*`, `VOYAGE_API_KEY` | motor y semántica del embedding engine | provider `mock` | perfil incompatible, latencias/costos o bloqueo de readiness |
| PostgreSQL base | `POSTGRES_*`, `DATABASE_URL`, `SST_POSTGRES_DSN` | construcción o resolución del DSN para migraciones y lanes durables | sin fallback inventado | scripts con DSN divergente o composición inconsistente |
| Redis | `REDIS_*` | reservado para caché/coordinación futura | definidos en plantilla | asumir una dependencia operativa que hoy no es central en el backend versionado |

## Variables clave por fase

### Ingesta local

- `OCR_LOW_CONFIDENCE_THRESHOLD`
- `OCR_TIMEOUT_SECONDS`
- `OCR_ENABLE_OCRMYPDF`
- `TESSERACT_CMD`
- `TESSERACT_LANGUAGE`
- `LLAMA_CLOUD_ENABLED`
- `LLAMA_CALL_ORDER`

## Chunking

Chunking hoy depende más de parámetros internos y del contrato de documentos
normalizados que de muchas env vars propias. Su composición efectiva se apoya
en:

- `docs_normalized` como input controlado
- perfiles locales de chunking y tokenizer canónico
- request headers como `Idempotency-Key` y correlación HTTP cuando aplica

## Embedding e indexación

- `SST_FEATURE_EMBEDDING_V2`
- `SST_FEATURE_INDEXING_BUNDLE_FIRST`
- `EMBEDDING_PROVIDER`
- `EMBEDDING_MODEL`
- `EMBEDDING_DIMENSION`
- `EMBEDDING_DISTANCE_METRIC`
- `EMBEDDING_BATCH_SIZE`
- `EMBEDDING_TIMEOUT_SECONDS`
- `EMBEDDING_RETRIES`
- `HF_TOKEN`
- `HF_HUB_CACHE`
- `VOYAGE_API_KEY`
- `SST_POSTGRES_DSN`
- `SST_PERSISTENCE_MODE`

## Retrieval

- `SST_FEATURE_RETRIEVAL_V1`
- `SST_CONSUMER_SCOPE_TYPE`
- `SST_CONSUMER_SCOPE_ID`

Retrieval hereda también la compatibilidad del perfil de embeddings y del
indexing target activo; no se gobierna solo con sus propias variables.

## Validaciones embebidas en código

Validaciones relevantes observables hoy:

- `LLAMA_CLOUD_API_KEY` es obligatoria cuando `LLAMA_CLOUD_ENABLED=true`.
- `LLAMA_CALL_ORDER` debe contener exactamente un `parse` y no puede repetir
  stops.
- `extract` no puede ir antes de `parse`.
- `classify` debe ir antes de `extract` cuando ambos están habilitados.
- `SST_PERSISTENCE_MODE` solo acepta `memory` o `postgres`.
- PostgreSQL durable falla cerrado si el DSN requerido no existe.
- `VOYAGE_API_KEY` es obligatoria cuando el provider live de PostgreSQL usa
  `voyage`.

## Riesgos e inconsistencias visibles

- `secrets.example.env` expone `REDIS_*`, pero Redis no aparece como pieza
  central de la composición bundle-first actual.
- Hay dos formas de resolver DSN en scripts: `SST_POSTGRES_DSN` directo o
  construcción desde `POSTGRES_*` / `DATABASE_URL`; eso es útil, pero conviene
  documentarlo como flexibilidad explícita y no como una sola ruta.
- `LLAMA_PARSE_VERSION=latest` sigue apareciendo en la plantilla y en docs como
  valor exploratorio; no debe confundirse con pin productivo.
