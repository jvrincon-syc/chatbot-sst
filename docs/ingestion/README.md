# Pipeline de ingesta documental

Este modulo implementa Fase 1 de `memory/fase1.md`:

- Inventario recursivo de `data/docs_raw`.
- Contratos Pydantic para metadata, pages, OCR y tables.
- Lector Markdown funcional.
- Lector PDF digital con `pypdf` e interfaz inyectable.
- Lector OCR por interfaz inyectable con `MockOcrEngine`.
- Motor OCRmyPDF + Tesseract español con diagnóstico de dependencias.
- Normalización textual conservadora.
- Manifiestos, logs JSON Lines y validación post-procesamiento.
- Ejecucion incremental por `source_path`, `document_id` y `content_hash`.

## Entorno

Instalacion recomendada en un equipo nuevo:

```bash
npm run setup:ocr:mac
npm run setup
npm run secrets:init
npm run doctor:ocr
```

`npm run setup` crea `.venv` aislado, actualiza herramientas de build dentro del entorno e instala el paquete Python con dependencias de desarrollo.

La forma manual equivalente es:

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip setuptools wheel
./.venv/bin/python -m pip install -e ".[dev]"
```

Los scripts cargan variables locales desde `secrets.env` cuando existe. Ese archivo está ignorado por Git.

## Comandos

Inventario:

```bash
./.venv/bin/python scripts/ingestion/run_inventory.py
```

Pipeline completo:

```bash
./.venv/bin/python scripts/ingestion/run_pipeline.py --run-id run_phase1_mocked
```

El pipeline es incremental por defecto. En una segunda corrida sin cambios:

- Lee `_manifests/inventory.json`.
- Compara `source_path`, `document_id` y `content_hash`.
- Reusa los artefactos normalizados existentes.
- Marca el documento como `skipped`.

Corrida incremental:

```bash
npm run ingestion:run -- --run-id phase1_incremental_check
```

Reprocesamiento por cambio:

- Modifica o reemplaza el archivo en `data/docs_raw`.
- Ejecuta otra corrida.
- El hash cambia y el documento se procesa de nuevo.

Validación independiente:

```bash
./.venv/bin/python scripts/ingestion/validate_normalized.py --run-id manual
```

Exportar JSON Schemas:

```bash
./.venv/bin/python scripts/ingestion/export_schemas.py
```

Pruebas:

```bash
./.venv/bin/python -m pytest app/back/tests/ingestion
```

Con `package.json`:

```bash
npm run test:ingestion
npm run ingestion:run
npm run ingestion:validate
```

## Estado de PDFs y OCR

El pipeline intenta primero extraccion PDF digital. Si la capa de texto es insuficiente o no hay extractor PDF configurado, cae al motor OCRmyPDF + Tesseract espanol.

El entorno local actual tiene OCRmyPDF, Tesseract y el idioma `spa`. La corrida `run_phase1_main_pdf_ocr_active` procesó todos los documentos del corpus:

- 46 Markdown.
- 6 PDFs digitales con `pypdf`.
- 3 PDFs por OCR con Tesseract.
- 0 documentos en `needs_review`.
- 0 documentos fallidos.

La corrida de cierre `phase1_final_full` reproceso 55 documentos. La corrida inmediata `phase1_final_incremental` omitio 55 documentos por hash sin cambios. La corrida posterior `phase1_final_post_skip_fix` confirmo que el skip incremental se mantiene tambien cuando el inventario anterior ya venia en estado `skipped`.

Para diagnosticar OCR:

```bash
npm run doctor:ocr
```

Variables relevantes en `secrets.env`:

- `OCRMYPDF_CMD`
- `TESSERACT_CMD`
- `TESSERACT_LANGUAGE`
- `OCR_TEMP_DIR`
- `OCR_LOW_CONFIDENCE_THRESHOLD`
- `OCR_TIMEOUT_SECONDS`

## Salidas

Las corridas generan:

- `data/docs_normalized/**/*.md`
- `data/docs_normalized/**/*.metadata.json`
- `data/docs_normalized/**/*.pages.json`
- `data/docs_normalized/_manifests/inventory.json`
- `data/docs_normalized/_manifests/run_<id>.json`
- `data/docs_normalized/_manifests/<id>_details.log`
- `data/docs_normalized/_manifests/needs_review.json`
- `data/docs_normalized/_manifests/errors.json`
- `data/docs_normalized/_manifests/validation_<id>.json`

## Revision de errores

Documentos que requieran revision quedan en:

```bash
data/docs_normalized/_manifests/needs_review.json
```

Documentos fallidos quedan en:

```bash
data/docs_normalized/_manifests/errors.json
```

Cada entrada incluye `document_id`, `source_path`, razones, etapa y accion recomendada.

## Cierre de Fase 1

Documentos de seguimiento:

- `docs/ingestion/exploratory_analysis.md`
- `docs/ingestion/phase1_checklist.md`
- `docs/ingestion/phase1_closure_report.md`
- `docs/ingestion/sprint_1_1_to_1_4_compliance.md`
