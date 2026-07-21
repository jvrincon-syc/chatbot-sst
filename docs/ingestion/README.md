# Pipeline de ingesta y normalización

Este directorio documenta la Fase 1 local que transforma `data/docs_raw` en
bundles Schema 2.0. El pipeline no incluye PostgreSQL, chunking, embeddings,
RAG, Redis ni frontend.

## Estado

El estado reproducible está en:

- `phase1_checklist.md`;
- `phase1_closure_report.md`;
- `pdf_corpus_quality_audit.md`;
- `pdf_corpus_expected.json`.

El candidato vigente es `.tmp/task6_candidate_full3`: contiene 9 bundles y 77
páginas. El gate estructural pasa; el golden semántico continúa fallido. No se
ha promovido a `data/docs_normalized`.

## Entorno

Usar Python 3.12 desde:

```powershell
.\.venv_windows_trabajo\Scripts\python.exe
```

Capacidades verificadas:

- OCRmyPDF 16.13.0;
- Tesseract 5.4.0 con `spa`;
- PDFium;
- pdfplumber;
- OpenCV.

Ghostscript 10.07.1 x64 está pendiente de instalación por soporte IT.

Las rutas locales se configuran en `secrets.env`, que no se versiona:

```text
OCR_TEMP_DIR
OCR_LOW_CONFIDENCE_THRESHOLD
OCR_TIMEOUT_SECONDS
TESSERACT_CMD
TESSERACT_LANGUAGE
TESSERACT_VERSION
OCRMYPDF_CMD
GHOSTSCRIPT_CMD
```

## Diagnóstico

```powershell
.\.venv_windows_trabajo\Scripts\python.exe scripts\ingestion\doctor_ocr.py
.\.venv_windows_trabajo\Scripts\python.exe -m pip check
```

## Pipeline candidato

El pipeline es incremental por defecto. Para una corrida de cierre se usa un
staging root y `--force`; nunca se escribe directamente sobre el corpus
normalizado antes de aprobar ambos gates.

Ejemplo para una fuente:

```powershell
.\.venv_windows_trabajo\Scripts\python.exe scripts\ingestion\run_pipeline.py `
  --staging-root .tmp\candidate `
  --force `
  --pipeline-version 2.0.1 `
  --run-id candidate `
  --only-source ruta/relativa/documento.pdf
```

## Validación

Validación estructural y semántica:

```powershell
.\.venv_windows_trabajo\Scripts\python.exe scripts\ingestion\validate_normalized.py `
  --docs-normalized .tmp\candidate `
  --raw-root data\docs_raw `
  --mode closure `
  --golden docs\ingestion\pdf_corpus_expected.json `
  --run-id candidate_gate
```

La promoción solo procede cuando el gate estructural y el golden pasan en la
misma corrida.

## Pruebas

```powershell
.\.venv_windows_trabajo\Scripts\python.exe -m pytest app\back\tests\ingestion -q
.\.venv_windows_trabajo\Scripts\python.exe -m pytest `
  app\back\tests\ingestion\test_pdf_corpus_golden.py -m corpus -q
```

Un skip por capacidades externas no equivale a aprobación del gate.

## Artefactos

Cada bundle canónico contiene:

- `.md`;
- `.metadata.json`;
- `.pages.json`;
- `.ocr.json`;
- `.tables.json`;
- `.forms.json`.

Los manifiestos de inventario, corrida, validación, errores y revisión viven
en `_manifests/`.

## Reglas de integridad

- Las carpetas de `data/docs_raw` son organizacion operativa y no fuente de
  verdad documental. La clasificacion debe priorizar evidencia interna:
  titulo/control documental, contenido visible, codigo y tablas de control.
  Una discrepancia entre carpeta y evidencia fuerte no debe producir
  `classification_conflict` ni `needs_review`.
- Los contenedores genericos (`manual`, `capacitaciones`, `politica`,
  `convivencia_laboral`) no penalizan tipos o topicos resueltos por el
  documento. Segmentos especificos como `seguridad_vial` si pueden ayudar a
  elegir un topic mas preciso que el contenedor.
- Los codigos en header o tabla de control documental tienen prioridad sobre
  referencias narrativas a otros formatos dentro del cuerpo.
- El original en `data/docs_raw` no se modifica.
- Las rutas canónicas son relativas POSIX.
- Una capacidad desconocida queda `not_evaluated`.
- La confianza OCR solo es `measured` con motor, versión, unidad y muestra.
- Un warning material obliga `needs_review`.
- No se insertan frases artificiales en Markdown para satisfacer el golden.
