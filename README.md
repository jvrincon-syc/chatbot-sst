# chatbot-sst

Pipeline para normalizar documentos SST, revisar evidencia y preparar
indexacion/RAG con trazabilidad verificable.

## Lectura rapida

- Indice corto: `docs/README.md`.
- Ingesta local y Schema 2.0: `docs/ingestion/README.md`.
- Via Llama-first experimental: `docs/llama_first/README.md`.
- Decisiones vigentes: `docs/adr/`.
- Runbooks operativos: `docs/runbooks/`.

`data/`, `memory/`, `.tmp/`, `.venv*` y `node_modules/` no son contexto
documental normal. Abrirlos solo cuando una tarea lo pida.

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

En Windows, `npm run python -- ...` prefiere `C:\\venvs\\chatbot-sst` si existe
y usa `.venv` como alternativa.

Para abrir una terminal ya activada en PowerShell:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
& 'C:\venvs\chatbot-sst\Scripts\Activate.ps1'
```

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

La GUI cubre inventario, revision humana, subida de `.pdf`/`.md`, ejecucion
local o Llama Cloud en staging, controles de Classify/Extract y validacion.

## Estado vigente

Fase 1 local esta cerrada y promovida como Schema 2.0: 55 documentos, 9 PDF,
77 paginas PDF, 41 `processed`, 14 `needs_review`, 0 `failed`.

Las fases de chunking, indexacion y RAG deben indexar solo documentos
aprobados o manejar `needs_review` explicitamente. Llama-first sigue detras de
configuracion y autorizacion de datos.
