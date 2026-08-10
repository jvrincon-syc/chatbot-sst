# chatbot-sst

Pipeline para normalizar documentos SST, revisar evidencia y preparar
indexacion/RAG con trazabilidad verificable.

## Lectura rapida

- Indice corto: `docs/README.md`.
- Mapa transversal del backend y handoffs entre fases: `docs/backend/`.
- Ingesta local y Schema 2.0: `docs/ingestion/README.md`.
- Chunking local y contrato HTTP: `docs/chunking/README.md`.
- Embedding bundle-first: `docs/embedding/README.md`.
- Indexacion bundle-first: `docs/indexing/README.md`.
- Retrieval y readiness: `docs/retrieval/README.md`.
- Via Llama-first experimental: `docs/llama_first/README.md`.
- Observabilidad del backend: `docs/observability/README.md`.
- Decisiones vigentes: `docs/adr/`.
- Runbooks operativos: `docs/runbooks/`.
- Reglas transversales: `docs/rules/`.

`data/`, `memory/`, `.tmp/`, `.venv*`, `node_modules/`, `manual-test-temp/`
y `pytest-*` no son contexto documental normal. `memory/`, `plans/` y
`.claude/` son guias locales, no autoridad versionada. Abrirlos solo cuando una
tarea lo pida.

## Guia de uso

Este repo separa el trabajo en capas operativas:

- Ingesta local: normaliza documentos y conserva trazabilidad por pagina.
- Chunking: transforma documentos normalizados en bundles parent-child
  auditables.
- Embedding: convierte chunk bundles en embedding bundles verificables.
- Indexacion: persiste nodos y vectores por perfil/target sin regenerar
  embeddings.
- Retrieval: valida lanes de consulta y recupera evidencia con provenance.
- Llama-first: experimento controlado con fallback y reglas de autorizacion.

Si buscas el estado actual de una corrida, no confies en cifras escritas a mano
en este README. Usa los comandos de inventario y validacion del area
correspondiente.

## Requisitos base

- Python `>=3.12,<3.13`.
- Node.js 18 o superior.
- npm.
- OCR local cuando se procese PDF escaneado: Tesseract con `spa`.
- OCR reforzado para PDF escaneado: OCRmyPDF y Ghostscript.

`pypdfium2` llega como dependencia Python del proyecto, asi que no hace falta
instalar PDFium aparte para la ruta normal del repo.

## Instalacion recomendada en Windows

Esta es la fuente de verdad actual del equipo en Windows: el repo esta
funcionando con el entorno virtual `chatbot-sst` ubicado en
`C:\venvs\chatbot-sst`.

### 1. Crear el entorno virtual canonico

```powershell
py -3.12 -m venv C:\venvs\chatbot-sst
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
& 'C:\venvs\chatbot-sst\Scripts\Activate.ps1'
```

### 2. Instalar dependencias Python del repo

```powershell
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e .[dev]
```

### 3. Crear configuracion local

```powershell
Copy-Item secrets.example.env secrets.env
```

Edita `secrets.env` solo si vas a activar PostgreSQL, Redis, embeddings live o
Llama Cloud. Para la ingesta local base, los valores por defecto sirven como
punto de partida.

### 4. Instalar dependencias del frontend

```powershell
npm.cmd --prefix app/front install
```

En la raiz no hace falta un `npm install` adicional para correr los scripts del
repo; lo importante es tener `npm` disponible en el sistema.

### 5. OCR opcional pero recomendado para PDF escaneado

Instala Tesseract con idioma `spa`. Si vas a usar OCR reforzado, instala tambien
OCRmyPDF y Ghostscript. Luego verifica el stack con:

```powershell
npm.cmd run doctor:ocr
```

### 6. Nota importante sobre los scripts npm en PowerShell

En algunas sesiones de PowerShell, `npm.ps1` puede quedar bloqueado por la
execution policy. Si te pasa, tienes dos opciones validas:

- usar `npm.cmd ...` directamente
- o ejecutar una vez:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
```

Los scripts del repo priorizan `C:\venvs\chatbot-sst\Scripts\python.exe` en
Windows si existe. Si no existe, usan `.venv` como fallback.

## Instalacion recomendada en macOS

En macOS la ruta natural del repo es una `.venv` local dentro de la carpeta del
proyecto, porque los scripts no-Windows resuelven `./.venv/bin/python`.

### 1. Instalar prerequisitos del sistema

```bash
brew install python@3.12 node
brew install tesseract tesseract-lang
brew install ocrmypdf ghostscript
```

Si no vas a procesar PDFs escaneados, puedes dejar OCRmyPDF y Ghostscript para
despues. Si si los necesitas, manten `spa` disponible en Tesseract.

### 2. Crear y activar el entorno virtual local

```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

### 3. Instalar dependencias Python del repo

```bash
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e '.[dev]'
```

### 4. Crear configuracion local

```bash
cp secrets.example.env secrets.env
```

### 5. Instalar dependencias del frontend

```bash
npm --prefix app/front install
```

### 6. Verificar OCR

```bash
npm run doctor:ocr
```

## Alternativa automatica para bootstrap

Si prefieres levantar un entorno nuevo sin seguir los pasos manuales, el repo ya
trae un bootstrap basico:

```powershell
npm.cmd run setup
```

o en macOS/Linux:

```bash
npm run setup
```

Ese flujo:

- crea `.venv`
- instala dependencias Python en modo editable con extras `dev`
- genera `secrets.env` desde `secrets.example.env` si no existe

En Windows sigue siendo recomendable el entorno canonico
`C:\venvs\chatbot-sst` cuando quieras alinearte con la configuracion que hoy
usa el equipo y con la prioridad de `npm run python`.

## Que hace falta para dejar el repo funcional

### Minimo para ingesta local

- Python 3.12
- dependencias Python del repo
- `secrets.env`
- Tesseract `spa` si vas a tocar PDF escaneado

### Para trabajar con la GUI de ingesta

- todo lo anterior
- dependencias del frontend en `app/front`

### Para indexacion e integraciones live

- PostgreSQL accesible por `DATABASE_URL` o `POSTGRES_*`
- Redis accesible por `REDIS_*`
- `SST_POSTGRES_DSN` para corridas live de PostgreSQL/pgvector cuando aplique
- keys reales solo si activas embeddings externos o Llama Cloud

Por defecto `LLAMA_CLOUD_ENABLED=false`, asi que la ruta local sigue siendo la
base segura.

## Verificacion recomendada despues de instalar

### Windows

```powershell
python --version
node --version
npm.cmd --version
python -m pip check
npm.cmd run doctor:ocr
npm.cmd run test:ingestion
```

### macOS

```bash
python --version
node --version
npm --version
python -m pip check
npm run doctor:ocr
npm run test:ingestion
```

Si `test:ingestion` pasa y `doctor:ocr` no reporta faltantes para tu caso de
uso, ya tienes una base funcional para seguir con inventario, validacion o GUI.

## Comandos frecuentes

### Ingesta y validacion

```powershell
npm run doctor:ocr
npm run test:ingestion
npm run ingestion:inventory
npm run ingestion:run
npm run ingestion:validate
npm run schemas:export
```

### Indexacion

```powershell
npm run test:embedding
npm run test:indexing
npm run test:retrieval
npm run embedding:verify-profile -- --profile-id local-bge-m3-v1 --dry-run
npm run indexing:prepare-postgres
npm run indexing:run -- --dry-run
npm run indexing:validate
```

### Llama-first experimental

```powershell
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

`npm run gui:api` es el entrypoint real del backend. No existe un alias `api`
separado en `package.json`.

Durante esa sesion, los eventos de arranque, requests, errores y apagado salen
en JSON estructurado por la terminal.

La GUI cubre inventario, revision humana, subida de `.pdf`/`.md`, ejecucion
local o Llama Cloud en staging, controles de Classify/Extract y validacion.

Para seguir una corrida o una request, consulta el runbook:
`docs/runbooks/backend-observability.md`.

## Estado del proyecto

La Fase 1 local ya opera como Schema 2.0. Los conteos exactos, run IDs y
resumenes de validacion cambian con el corpus y deben consultarse en la salida
de `npm run ingestion:inventory` y `npm run ingestion:validate`, no en texto
fijo del README.

Chunking, embedding, indexacion y retrieval ya tienen superficies propias en
el backend versionado, pero no todas tienen el mismo grado de madurez
operativa. Consulta `docs/backend/gaps-and-debt.md` para distinguir estado
vigente, deuda visible y faltantes al modelo objetivo.

Chunking, embedding, indexacion y retrieval deben consumir solo documentos o
bundles elegibles, o manejar `needs_review` explicitamente. Llama-first sigue
detras de configuracion y autorizacion de datos.
