# Llama-first

Estado compacto del experimento para usar LlamaParse, LlamaClassify,
LlamaExtract y LlamaIndex sin perder trazabilidad local.

## Estado

Completado localmente:

- Puertos y modelos neutrales para parse, classify, extract, provider runs y
  ledger de uso.
- Adapters Llama Cloud para Parse/Classify/Extract con almacenamiento de
  resultados crudos.
- `LlamaOrchestrator` con paradas configurables.
- Extension compatible de Schema 2.0 para metadatos Llama.
- Indexacion local con LlamaIndex: document factory, parent/child nodes,
  metadata pipeline, embeddings, docstore/vector pipeline en memoria,
  migracion pgvector y CLI.
- Retrieval baseline: vector, PostgreSQL FTS query builder, RRF, reranking,
  parent expansion y evidence builder.
- Dataset y harness de evaluacion Llama-first.
- GUI con seleccion `local`/`llama_cloud`, toggles Classify/Extract y orden de
  llamadas.

## Bloqueos

- No subir documentos corporativos a Llama Cloud sin autorizacion explicita,
  region, retencion/eliminacion y presupuesto de creditos.
- `LLAMA_PARSE_VERSION=latest` sigue permitido solo para exploracion; produccion
  requiere una version fechada retornada por un job real o registrado.
- Escritura real en PostgreSQL/pgvector pendiente de conexion configurada.
- Benchmark A/B de adopcion pendiente de fixtures live autorizados o grabados.

## Configuracion

Variables principales:

```text
LLAMA_CLOUD_ENABLED
LLAMA_CLOUD_API_KEY
LLAMA_PARSE_TIER
LLAMA_PARSE_VERSION
LLAMA_PARSE_MAX_CREDITS_PER_RUN
LLAMA_CLASSIFY_ENABLED
LLAMA_EXTRACT_ENABLED
LLAMA_CALL_ORDER
LLAMA_LOCAL_FALLBACK_ENABLED
```

Parse es obligatorio en modo cloud y debe aparecer una vez en
`LLAMA_CALL_ORDER`. Classify y Extract son opcionales. Si ambos estan activos,
Classify debe correr antes de Extract para seleccionar el schema correcto antes
de extraer.

Ordenes validos comunes:

- `classify,parse,extract`.
- `parse,classify,extract`.
- `classify,parse`.
- `parse,classify`.
- `parse`.

## Politica de costo bajo

- Parse auditable mantiene `tier=cost_effective` cuando se necesitan `markdown`
  e `items`.
- Parse `fast` solo para probes text-only; el adapter quita expands
  incompatibles.
- Classify usa modo `FAST`.
- Extract usa `tier=cost_effective`, `parse_tier=fast` y limites de paginas.

## Verificacion reciente

- Backend completo: `npm run python -- -m pytest app/back/tests` -> 319 passed,
  3 skipped.
- Frontend: `npm --prefix app/front run build` -> passed.
- Schemas: `npm run schemas:export` -> 10 schemas.
- Ingesta: `npm run ingestion:validate` -> passed.
- Indexacion dry-run: 55 candidatos, 41 aprobados.
- Indexacion local: 41 documentos aprobados, 41 parent nodes, 95 child nodes.
- Evaluacion: `npm run evaluation:llama-first` -> baseline ready con 2
  documentos y 2 preguntas.
- Smoke sintetico no sensible: Parse `pjb-g05y0jzu8law2xy820haloreyu5e`,
  Classify `clj-gez9e4ucpa1pdcl3c6vv06fd9pes`, Extract
  `ext-zzz5se6fsmx5d2qlqs6wcm7n9dfs`.

## Referencias vivas

- `decision-log.md`: decisiones especificas del experimento.
- `docs/adr/`: limites, pins, chunking y routing de produccion.
- `docs/runbooks/`: outage, creditos, pin de version y reproceso.
