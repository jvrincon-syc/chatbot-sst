# Llama-first

Via experimental para usar LlamaParse, LlamaClassify, LlamaExtract y
LlamaIndex sin perder los contratos locales de trazabilidad.

## Estado

Implementado localmente:

- Puertos neutrales para Parse, Classify, Extract, provider runs y uso.
- Adapters Llama Cloud detras de infraestructura.
- `LlamaOrchestrator` con paradas configurables.
- Extension compatible de Schema 2.0 para metadata Llama.
- Indexacion local con LlamaIndex, parent/child nodes y baseline de retrieval.
- GUI con lane `local`/`llama_cloud`, toggles Classify/Extract y orden.

## Bloqueos

- No subir documentos corporativos a Llama Cloud sin autorizacion explicita de
  datos, region, retencion/eliminacion y presupuesto.
- `LLAMA_PARSE_VERSION=latest` es solo exploratorio; produccion requiere pin
  fechado validado.
- Escritura real PostgreSQL/pgvector depende de conexion configurada.
- Benchmark A/B de adopcion requiere fixtures live autorizados o grabados.

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
`LLAMA_CALL_ORDER`. Ordenes comunes: `classify,parse,extract`,
`parse,classify,extract`, `classify,parse`, `parse,classify`, `parse`.

### Embeddings

La indexacion selecciona un perfil inmutable (`--profile`) y el runtime de
embeddings se configura en el borde de infraestructura. Los consumidores usan
el puerto comun `EmbeddingProvider` con `embed_documents` y `embed_queries`.

Variables principales:

```text
EMBEDDING_PROVIDER=mock|bge|voyage
EMBEDDING_MODEL
EMBEDDING_DIMENSION
EMBEDDING_DISTANCE_METRIC=cosine|l2|inner_product
EMBEDDING_BATCH_SIZE
EMBEDDING_DEVICE
BGE_USE_FP16
BGE_QUERY_MAX_LENGTH
BGE_DOCUMENT_MAX_LENGTH
HF_TOKEN
HF_HUB_CACHE
VOYAGE_API_KEY
EMBEDDING_TIMEOUT_SECONDS
EMBEDDING_RETRIES
```

`VOYAGE_API_KEY` solo es obligatorio cuando se activa el provider `voyage`.
BGE-M3 usa `BAAI/bge-m3` via `FlagEmbedding` y carga el modelo de forma lazy
por proceso/factory. Cambiar de provider, dimension o metrica requiere elegir
otro perfil pgvector y reindexar el corpus correspondiente.

## Politica de costo

- Parse auditable usa `tier=cost_effective` cuando se necesitan `markdown` e
  `items`.
- Parse `fast` solo para probes text-only.
- Classify usa `FAST`.
- Extract usa `cost_effective`, `parse_tier=fast` y limites de paginas.

## Verificacion reciente

- Backend: `npm run python -- -m pytest app/back/tests` -> 319 passed,
  3 skipped.
- Frontend build: passed.
- Schemas: 10 exportados.
- Ingesta validation: passed.
- Indexacion: 55 candidatos, 41 aprobados, 41 parent nodes, 95 child nodes.
- Evaluacion Llama-first: baseline listo con 2 documentos y 2 preguntas.
- Smoke sintetico no sensible: Parse `pjb-g05y0jzu8law2xy820haloreyu5e`,
  Classify `clj-gez9e4ucpa1pdcl3c6vv06fd9pes`, Extract
  `ext-zzz5se6fsmx5d2qlqs6wcm7n9dfs`.

## Referencias

- ADR-001: limites del experimento.
- ADR-002: pins Pydantic/Llama.
- ADR-003: estrategia de nodos.
- ADR-004: routing productivo/selectivo.
- `docs/runbooks/`: outage, creditos, pin de version y reproceso.
