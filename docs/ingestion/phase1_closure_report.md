# Estado de cierre de Fase 1 - Ingesta Schema 2.0

Fecha de verificacion: 2026-07-20

## Decision vigente

Fase 1 queda cerrada y promovida bajo el contrato vigente de `memory/` +
golden.

La salida oficial `data/docs_normalized` ya no es el arbol historico Schema
1.0. Fue reemplazada por un candidato completo Schema 2.0 generado desde
`data/docs_raw`, validado con gate estructural y golden semantico, y promovido
mediante el helper fail-closed `promote_candidate()`.

## Salida oficial

Fuente:

```text
data/docs_raw: 55 archivos
Markdown: 46
PDF: 9
```

Salida promovida:

```text
data/docs_normalized
schema_version metadata: 2.0 en 55/55 documentos
Markdown normalizado: 55
metadata.json: 55
pages.json: 55
ocr.json: 55
tables.json: 55
forms.json: 55
processed: 41
needs_review: 14
failed: 0
```

Corpus PDF auditado:

```text
PDFs golden: 9
Paginas PDF esperadas: 77
Paginas PDF materializadas: 77
PDFs needs_review: 9
PDFs failed: 0
```

## Candidato promovido

```text
.tmp/phase1_main_full_candidate_20260720_r1
run_id: phase1_main_full_candidate_20260720_r1
pipeline_version: 2.0.0
resultado: {'processed': 41, 'failed': 0, 'needs_review': 14, 'skipped': 0}
```

Promocion:

```text
promoted .tmp/phase1_main_full_candidate_20260720_r1 -> data/docs_normalized
manifest:
  structural_status: passed
  golden_status: passed
  run_id: phase1_main_full_candidate_20260720_r1_gate
```

## Gates oficiales

Validacion post-promocion:

```text
./.venv312/bin/python scripts/ingestion/validate_normalized.py \
  --docs-normalized data/docs_normalized \
  --raw-root data/docs_raw \
  --mode closure \
  --golden docs/ingestion/pdf_corpus_expected.json \
  --run-id phase1_official_20260720_guardrail_gate

passed: 0 error(s)
```

Checks aprobados:

```text
metadata_schema
unique_document_ids
markdown_has_metadata
orphan_files
auxiliary_schema
auxiliary_document_ids
page_count_consistency
page_ordering_contiguity
front_matter_parity
inventory_schema
inventory_metadata_bijection
inventory_source_hashes
inventory_final_statuses
status_manifests
processed_with_review_reasons
closure_required_artifacts
golden_bijection
golden_metadata
golden_pages
golden_content
golden_page_total
```

## Capacidades locales

Verificado con `scripts/ingestion/doctor_ocr.py`:

```text
OCR status: ok
OCRmyPDF: /usr/local/bin/ocrmypdf (17.8.0)
Ghostscript: 10.07.1
Tesseract: /usr/local/bin/tesseract (5.5.2)
Idioma Tesseract: spa disponible
pdfplumber: available
PDFium: available
OpenCV: available
```

`secrets.env` queda configurado localmente con rutas absolutas para OCRmyPDF,
Ghostscript y Tesseract.

## Cierre del bloqueo semantico

Las dos versiones que bloqueaban `golden_metadata` fueron extraidas desde OCR
regional de cabecera, no inferidas desde el golden:

```text
convivencia_laboral/manual/1781045390931_syc_politicadeprevencind.pdf
version: 0.2

general_sst/manuales/politica/1778000305710_syc_politicadeseguridady.pdf
version: 0.6
```

Tambien quedo un guardarrail para que `minimum_content.must_preserve` acepte
anclas literales ejecutables y rechace prosa descriptiva como `three objective
rows`; la prosa debe quedar en `structure`.

## Pruebas

```text
./.venv312/bin/python -m pip check
No broken requirements found.

./.venv312/bin/python -m pytest app/back/tests/ingestion -m 'not corpus' -q
245 passed, 2 deselected in 3.03s

./.venv312/bin/python -m pytest app/back/tests/ingestion/test_pdf_corpus_golden.py -m corpus -q
2 passed in 69.90s (0:01:09)
```

## Politica para Fase 2

La salida oficial ya cumple Fase 1 robusta/golden como arbol promovido Schema
2.0. Para chunking, indexacion y RAG, el consumidor debe respetar
`processing_status`:

- `processed` puede avanzar como entrada normal.
- `needs_review` esta trazado y materializado, pero no debe indexarse como
  contenido aprobado sin una decision explicita de revision o filtrado.

Esta restriccion no reabre Fase 1; es el contrato de consumo esperado por las
fases posteriores.
