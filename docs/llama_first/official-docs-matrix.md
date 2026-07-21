# Official Docs Matrix

Fecha de consulta: 2026-07-21

| Capacidad | Fuente oficial | Entrada | Salida | Coste | Riesgo | Decision preliminar |
|---|---|---|---|---|---|---|
| Parse | https://developers.llamaindex.ai/llamaparse/parse/guides/configuring-parse/ | `file_id` o `source_url`, `tier`, `version` | job + contenido segun `expand` | por pagina/tier | cambios si `latest` no se pinnea | principal experimental |
| Parse results | https://developers.llamaindex.ai/llamaparse/parse/guides/retrieving-results/ | `job_id`, `expand` | `markdown`, `items`, `metadata`, `job_metadata` | puede incluir outputs grandes | pedir contenido de mas filtra datos y aumenta tamano | usar expand minimo |
| Parse tiers | https://developers.llamaindex.ai/llamaparse/parse/guides/tiers/ | tier/version | parse reproducible si version fechada | fast menor, agentic_plus mayor | `fast` no soporta markdown | `cost_effective` default exploratorio |
| Classify | https://developers.llamaindex.ai/llamaparse/classify/ | archivo + tipos/reglas | categoria/confianza/evidencia segun API | por paginas/proceso | beta, breaking changes | principal con reconciliacion local |
| Extract | https://developers.llamaindex.ai/llamaparse/extract/ | archivo/config/schema | JSON tipado | por extract/parse | schema incompleto o campo sin soporte | principal para control documental tipado |
| Extract concepts | https://developers.llamaindex.ai/llamaparse/extract/guides/concepts/ | agents/schema/targets/jobs | runs de extraccion | segun job | mal diseno de schema | schemas internos + mapper |
| LlamaIndex OSS | https://github.com/run-llama/llama_index | Documents/Nodes | nodes, docstore, vector store | OSS + embeddings | vendor coupling si entra al dominio | modulo indexing separado |

## Confirmaciones

- `tier` y `version` son obligatorios en Parse v2.
- `expand` debe pedirse explicitamente para obtener contenido parseado.
- `markdown`, `items`, `metadata` y `job_metadata` son valores documentados para retrieval de resultados.
- `fast` no sirve para el objetivo actual porque no soporta markdown.
- Classify esta en beta; los adapters deben encapsular cambios de SDK.
- Extract v2 es el flujo recomendado para nuevos proyectos.
