# Checklist vigente de Fase 1 - Ingesta Schema 2.0

Fecha de corte: 2026-07-20

Este checklist reemplaza los cierres historicos de Schema 1.0. La fuente de
alcance permanece en `memory/`; el contrato ejecutable vigente esta en
`docs/ingestion/pdf_corpus_expected.json`.

## Contratos y pipeline

- [x] Contratos canonicos Schema 2.0 y adaptador legacy explicito.
- [x] Escritura nueva exclusivamente en Schema 2.0.
- [x] Identidad estable y paths POSIX relativos.
- [x] Bundles atomicos con Markdown, metadata, pages, OCR, tables y forms.
- [x] Capacidades desconocidas representadas como `not_evaluated`.
- [x] Confianza OCR medida solo con procedencia real.
- [x] Warnings materiales propagados a `needs_review`.
- [x] Pipeline candidato aislado y promocion fail-closed.
- [x] Promocion bloqueada salvo `golden_status="passed"` explicito.
- [x] Golden validator permite candidato completo con metadata extra no-PDF
  valida y rechaza PDF extra o metadata invalida.
- [x] Golden `minimum_content.must_preserve` acepta anclas literales y rechaza
  prosa descriptiva no ejecutable.

## Extraccion

- [x] PDF digital procesado antes del fallback OCR.
- [x] Tablas y formularios digitales conectados al bundle.
- [x] OCRmyPDF configurado localmente.
- [x] Ghostscript 10.07.1 configurado localmente.
- [x] Tesseract 5.5.2 instalado con idioma `spa`.
- [x] PDFium conectado como rasterizador regional y de pagina completa.
- [x] Tres PDF escaneados materializados.
- [x] Nueve bundles PDF materializados.
- [x] Las 77 paginas del corpus PDF materializadas.
- [x] Pausas activas procesado como `hybrid` cuando OCR regional agrega texto.
- [x] Tablas y forms de escaneos evaluados con sidecars Schema 2.0.
- [x] Handwriting/firma evaluado con detector visual conservador.
- [x] Versiones de cabecera `0.2` y `0.6` en escaneos extraidas con evidencia
  OCR regional de cabecera.

## Validacion vigente

Candidato promovido:

```text
.tmp/phase1_main_full_candidate_20260720_r1
```

- [x] 55 fuentes inventariadas desde `data/docs_raw`.
- [x] 46 Markdown inventariados.
- [x] 9 PDF inventariados.
- [x] 55 bundles presentes.
- [x] 55 Markdown normalizados presentes.
- [x] 55 metadata Schema 2.0 presentes.
- [x] 55 pages sidecars presentes.
- [x] 55 OCR sidecars presentes.
- [x] 55 tables sidecars presentes.
- [x] 55 forms sidecars presentes.
- [x] 77 paginas PDF presentes y contiguas.
- [x] 0 documentos fallidos.
- [x] 41 documentos `processed`.
- [x] 14 documentos `needs_review`.
- [x] Gate estructural aprobado.
- [x] Golden de bijeccion aprobado.
- [x] Golden de metadata aprobado.
- [x] Golden de paginas aprobado.
- [x] Golden de total de paginas aprobado.
- [x] Golden de contenido aprobado.
- [x] Expectativas descriptivas del golden convertidas a anclas textuales
  ejecutables.
- [x] Estados `processed`/`needs_review` alineados con auditoria visual y
  reglas materiales.
- [x] Corpus gate completo aprobado.
- [x] Candidato promovido a `data/docs_normalized`.
- [x] Validacion post-promocion aprobada sobre la salida oficial.

## Evidencia de pruebas

```text
./.venv312/bin/python scripts/ingestion/validate_normalized.py \
  --docs-normalized data/docs_normalized \
  --raw-root data/docs_raw \
  --mode closure \
  --golden docs/ingestion/pdf_corpus_expected.json \
  --run-id phase1_official_20260720_guardrail_gate
passed: 0 error(s)

./.venv312/bin/python -m pip check
No broken requirements found.

./.venv312/bin/python -m pytest app/back/tests/ingestion -m 'not corpus' -q
245 passed, 2 deselected in 3.03s

./.venv312/bin/python -m pytest app/back/tests/ingestion/test_pdf_corpus_golden.py -m corpus -q
2 passed in 69.90s (0:01:09)
```

## Regla de consumo downstream

Fase 1 queda cerrada como normalizacion trazable y promovida Schema 2.0. Las
fases de chunking, indexacion y RAG deben filtrar o gestionar explicitamente
documentos con `processing_status="needs_review"`; esos documentos existen y
estan auditados, pero no deben tratarse como aprobados automaticamente.
