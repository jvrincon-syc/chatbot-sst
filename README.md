# chatbot-sst

Pipeline local para normalizar documentos SST, revisar evidencia y preparar
indexacion/RAG con trazabilidad.

## Lectura rapida

- Indice de documentacion: `docs/README.md`.
- Ingesta y Schema 2.0: `docs/ingestion/README.md`.
- Experimento Llama-first: `docs/llama_first/README.md`.
- Decisiones de arquitectura: `docs/adr/`.
- Operacion: `docs/runbooks/`.

`memory/` y `data/` no son parte de esta limpieza documental. `data/docs_raw`
permanece como fuente local y `data/docs_normalized` como salida generada.

## Requisitos

- Python `>=3.12,<3.13`.
- Node.js 18 o superior.
- npm.
- OCR local cuando se procese PDF escaneado: OCRmyPDF, Tesseract con `spa`,
  Ghostscript y PDFium.

## Instalacion

```powershell
npm run setup
```

El comando crea `.venv`, instala dependencias Python en modo editable y genera
`secrets.env` desde `secrets.example.env` si no existe.

En Windows de trabajo este repo suele usar `.venv_windows_trabajo` si existe;
el script `npm run python -- ...` lo prefiere automaticamente antes de `.venv`.

## Comandos frecuentes

```powershell
npm run doctor:ocr
npm run test:ingestion
npm run ingestion:inventory
npm run ingestion:run
npm run ingestion:validate
npm run schemas:export
npm run test:indexing
npm run indexing:run -- --dry-run
npm run indexing:validate
npm run evaluation:llama-first
```

## GUI de ingesta

```powershell
npm install --prefix app/front
npm run gui:dev
```

La API se ejecuta con `npm run gui:api` y el frontend con
`npm run gui:front`. El frontend local abre normalmente en
`http://127.0.0.1:5173`.

La GUI permite inventario, revision humana, subida de `.pdf`/`.md`, ejecucion
local o Llama Cloud en staging, controles de Classify/Extract y validacion. Las
decisiones humanas se guardan en
`data/docs_normalized/_manifests/review_decisions.json`.

## Estado vigente

Fase 1 local esta cerrada y promovida como Schema 2.0: 55 documentos, 9 PDF, 77
paginas PDF, 41 `processed`, 14 `needs_review`, 0 `failed`. Las fases de
chunking, indexacion y RAG deben indexar solo documentos aprobados o manejar
`needs_review` explicitamente.

Llama-first esta en rama experimental. Parse es obligatorio en modo cloud;
Classify y Extract son paradas configurables. No se deben subir documentos
corporativos a Llama Cloud hasta tener autorizacion de datos, region,
retencion/eliminacion y presupuesto de creditos.

## Ideas no cerradas

Para RAG evaluar: parent/child chunking con overlap, reranking, pgvector o
Qdrant, metadatos para prefiltro, vector quantization y un FAQ/cache para
preguntas frecuentes. Fine-tuning/LoRA no reemplaza citas exactas por pagina y
debe tratarse como linea separada de investigacion.
