# Ingesta local

Esta area documenta la Fase 1 local: `data/docs_raw` -> bundles Schema 2.0 en
`data/docs_normalized`. No incluye PostgreSQL, embeddings, RAG, Redis ni
frontend salvo la GUI de control de ingesta.

## Estado vigente

Fase 1 local ya opera como Schema 2.0 y el contrato estable es este:

- `data/docs_raw` sigue siendo inmutable.
- `data/docs_normalized` contiene los bundles promovidos.
- La clasificacion prioriza el contenido visible, los codigos documentales y
  las tablas de control por encima de la carpeta de origen.
- Los contenedores genericos no deben provocar conflictos si la evidencia
  interna es fuerte.
- Los documentos `needs_review` siguen trazados pero no se indexan como
  aprobados sin una decision explicita.
- Los conteos concretos cambian con el corpus; consulta
  `npm run ingestion:inventory` y `npm run ingestion:validate` para el estado
  actual en vez de copiar cifras historicas aqui.

## Comandos

Usa los scripts npm, que seleccionan `C:\\venvs\\chatbot-sst` en Windows si esta
disponible y `.venv` en el resto de entornos.

```powershell
npm run doctor:ocr
npm run test:ingestion
npm run ingestion:inventory
npm run ingestion:run
npm run ingestion:validate
npm run schemas:export
```

Para una corrida candidata aislada:

```powershell
npm run ingestion:run -- --staging-root .tmp/candidate --force --run-id candidate
npm run ingestion:validate -- --docs-normalized .tmp/candidate --mode closure --run-id candidate_gate
```

Promover manualmente solo procede cuando el gate estructural y el golden pasan
en la misma corrida. No escribas directamente sobre `data/docs_normalized` antes
de aprobar el candidato.

## Contrato

Cada documento normalizado debe conservar:

- Markdown normalizado.
- `.metadata.json`.
- `.pages.json`.
- `.ocr.json`.
- `.tables.json`.
- `.forms.json`.

Los manifiestos de inventario, corrida, validacion, errores y revision viven en
`_manifests/`.

## Reglas clave

- `data/docs_raw` es inmutable.
- Las rutas canonicas son relativas POSIX.
- Las carpetas de `data/docs_raw` son organizacion operativa, no verdad
  documental. La clasificacion prioriza titulo/control documental, contenido,
  codigo y tablas internas.
- Contenedores genericos como `manual`, `capacitaciones`, `politica` o
  `convivencia_laboral` no deben crear conflictos si la evidencia interna es
  fuerte.
- Segmentos especificos como `seguridad_vial` pueden ayudar a resolver topic.
- Codigos de header o tabla de control tienen prioridad sobre referencias
  narrativas dentro del cuerpo.
- Una capacidad desconocida queda `not_evaluated`.
- La confianza OCR solo es `measured` con motor, version, unidad y muestra.
- El inventario normalizado expone `ocr_confidence` por documento cuando existe
  en metadata/OCR; la GUI lo muestra como porcentaje o `N/A`.
- El umbral minimo de confianza OCR para revision es configurable desde la GUI y
  por CLI con `--ocr-review-threshold`; el valor por defecto es `0.80`.
- Un PDF procesado por LlamaParse sin dato de confianza OCR queda
  `needs_review` con razon `ocr_confidence_unavailable`.
- La metadata de Llama Cloud se persiste en `.metadata.json` bajo
  `llama_cloud`, incluyendo job id, hash de configuracion, `page_metadata` y
  `job_metadata`. La confianza de LlamaParse se registra como `estimated` con
  `method=llamaparse_page_parse_confidence`; no equivale a confianza OCR por
  palabra.
- Un warning material obliga `needs_review`.
- No se insertan frases artificiales en Markdown para satisfacer el golden.

## Downstream

Chunking, indexacion y RAG deben filtrar o gestionar explicitamente
`processing_status="needs_review"`. Esos documentos existen y estan trazados,
pero no deben indexarse como contenido aprobado sin decision humana o regla
explicita.
