# Llama-first Research Log

Fecha local: 2026-07-21

## 2026-07-21 - Parse tiers, versioning and expand

- Fuente: https://developers.llamaindex.ai/llamaparse/parse/guides/tiers/
- Hallazgo: Parse v2 requiere `tier` y `version`; `latest` sirve para exploracion, pero produccion debe pinnear una version fechada. `cost_effective` es apropiado para texto con tablas simples; `fast` no soporta markdown.
- Efecto en diseno: `LLAMA_PARSE_TIER=cost_effective` y `LLAMA_PARSE_VERSION=latest` quedan como defaults experimentales. El cierre del plan debe reemplazar `latest` por version fechada validada.

## 2026-07-21 - Parse result retrieval

- Fuente: https://developers.llamaindex.ai/llamaparse/parse/guides/retrieving-results/
- Hallazgo: `expand` controla el contenido retornado. Sin `expand`, el API devuelve metadata del job, no contenido parseado. Valores inline relevantes: `markdown`, `items`, `metadata`, `job_metadata`.
- Efecto en diseno: `LLAMA_PARSE_EXPAND=markdown,items,metadata,job_metadata` se modela como setting tipado.

## 2026-07-21 - Parse request anatomy

- Fuente: https://developers.llamaindex.ai/llamaparse/parse/guides/configuring-parse/
- Hallazgo: el request v2 separa campos requeridos (`file_id` o `source_url`, `tier`, `version`) de `input_options`, `processing_options`, `agentic_options`, `output_options`, `page_ranges`, cache y controles de procesamiento.
- Efecto en diseno: Fase 1 no expone diccionarios SDK en dominio; la configuracion concreta vive en infrastructure/adapters futuros.

## 2026-07-21 - LlamaClassify

- Fuente: https://developers.llamaindex.ai/llamaparse/classify/
- Hallazgo: Classify categoriza documentos en tipos definidos con reglas de lenguaje natural, esta en beta, y se recomienda antes de extraction, parsing o indexing para mejorar routing/costo.
- Efecto en diseno: el resultado cloud se reconciliara con reglas locales; por ahora solo se define un puerto y modelos neutrales.

## 2026-07-21 - LlamaExtract

- Fuente: https://developers.llamaindex.ai/llamaparse/extract/
- Hallazgo: Extract genera datos tipados desde documentos no estructurados con SDK, REST y UI; v2 es el flujo recomendado. Los tiers/versiones de Extract tambien deben controlarse.
- Efecto en diseno: Fase 1 define `StructuredExtractorPort` y `ExtractionResult` con evidencia obligatoria para campos criticos.

## 2026-07-21 - LlamaExtract concepts

- Fuente: https://developers.llamaindex.ai/llamaparse/extract/guides/concepts/
- Hallazgo: los conceptos centrales son extraction agents, data schemas, extraction targets, jobs y runs. El schema es JSON Schema con soporte de Pydantic en SDK.
- Efecto en diseno: los schemas corporativos propios seguiran siendo el contrato auditable; adapters mapearan runs externos a modelos internos.

## 2026-07-21 - LlamaIndex OSS

- Fuente: https://github.com/run-llama/llama_index
- Hallazgo: LlamaIndex OSS es el framework de indexacion/retrieval que se usara sin instalar inicialmente el metapaquete `llama-index`.
- Efecto en diseno: se planifican dependencias granulares `llama-index-core` y `llama-index-vector-stores-postgres`.

## 2026-07-21 - PyPI dependency availability

- Fuente: `python -m pip index versions ...`
- Hallazgo: versiones actuales disponibles: `llama-cloud==2.12.0`, `llama-index-core==0.14.23`, `llama-index-vector-stores-postgres==0.8.1`.
- Efecto en diseno: se prefiere `llama-cloud==2.12.0` sobre el candidato del plan `2.11.0`, documentando que es la version actual al 2026-07-21. El resolver dry-run con LlamaIndex `0.14.23` falla porque `llama-index-workflows>=2.14` requiere `pydantic>=2.11.5`. Pruebas con `0.13.6`, `0.12.52` y `0.11.23` mas integraciones Postgres compatibles tambien fallan o no emparejan con el vector store. Se deja `llama-indexing` vacio hasta decidir si se relaja Pydantic por ADR.

## 2026-07-21 - LlamaIndex IngestionPipeline

- Fuente: https://developers.llamaindex.ai/python/framework/module_guides/loading/ingestion_pipeline/
- Hallazgo: `IngestionPipeline` aplica transformaciones a documentos/nodos y puede cachear pares nodo-transformacion para reutilizacion entre corridas.
- Efecto en diseno: Fase 6 separara ingestion documental de indexing; el cache se encapsulara detras de infrastructure para no acoplar dominio a LlamaIndex.

## 2026-07-21 - LlamaIndex HierarchicalNodeParser

- Fuente: https://developers.llamaindex.ai/python/framework-api-reference/node_parsers/hierarchical/
- Hallazgo: el parser devuelve una lista plana de nodos jerarquicos con relaciones parent/child y posible overlap entre niveles.
- Efecto en diseno: los tests de Fase 6 deben verificar IDs deterministas, existencia de parent para hojas y trazabilidad de pagina para evitar que el overlap diluya evidencia.

## 2026-07-21 - LlamaIndex Postgres vector store

- Fuente: https://developers.llamaindex.ai/python/framework/integrations/vector_stores/postgres/
- Hallazgo: la integracion oficial se instala como `llama-index-vector-stores-postgres` y expone `PGVectorStore` para PostgreSQL con pgvector.
- Efecto en diseno: se mantiene dependencia granular, sin instalar el metapaquete `llama-index`, y se valida el import `llama_index.vector_stores.postgres`.

## 2026-07-21 - Low-cost Llama Cloud call profile

- Fuente: https://developers.llamaindex.ai/llamaparse/general/pricing/
- Hallazgo: Parse `fast` cuesta menos que `cost_effective`, pero Extract de menor costo usa `tier=cost_effective` y puede combinarse con `parse_tier=fast`. Classify tiene modo `Fast`.
- Fuente: https://developers.llamaindex.ai/llamaparse/parse/guides/retrieving-results/
- Hallazgo: Parse `fast` no soporta `markdown` ni `items`; pedir esos expands en fast produce error de validacion.
- Efecto en diseno: el camino PDF auditable mantiene Parse `cost_effective` para conservar markdown/items; los probes de Parse `fast` filtran expands a texto/metadata. Classify envia `mode=FAST`; Extract envia `tier=cost_effective`, `parse_tier=fast` y limita paginas por configuracion.

## 2026-07-21 - SDK v2 field validation during live smoke

- Fuente: SDK instalado `llama-cloud==2.12.0` y respuesta viva de la API.
- Hallazgo: Parse v2 rechaza `input_options.ocr_languages` y
  `processing_control.timeout_seconds`; el SDK tipa OCR como
  `processing_options.ocr_parameters.languages` y timeout como
  `processing_control.timeouts.base_in_seconds`.
- Fuente: https://developers.llamaindex.ai/llamaparse/classify/sdk/
- Hallazgo: Classify exige reglas con descripciones naturales; la API rechaza
  descripciones demasiado cortas.
- Fuente: https://developers.llamaindex.ai/llamaparse/extract/guides/migration-v1-to-v2/
- Hallazgo: Extract v2 acepta `file_input` como file ID o Parse job ID
  (`pjb-...`), permitiendo Parse once, Extract many.
- Efecto en diseno: se corrigio `LlamaParseConfig`, `LlamaClassifyConfig`
  usa descripciones versionadas y el smoke reutiliza el `parse_job_id` para
  Classify y Extract.
