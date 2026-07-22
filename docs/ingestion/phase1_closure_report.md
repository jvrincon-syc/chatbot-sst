# Cierre Fase 1 - Ingesta Schema 2.0

Fecha de verificacion: 2026-07-20.

## Decision

Fase 1 queda cerrada y promovida. `data/docs_normalized` fue reemplazado por un
candidato completo Schema 2.0 generado desde `data/docs_raw`, validado con gate
estructural y golden semantico, y promovido con helper fail-closed.

## Salida oficial

```text
data/docs_raw: 55 archivos
Markdown: 46
PDF: 9

data/docs_normalized:
schema_version 2.0: 55/55
processed: 41
needs_review: 14
failed: 0

PDF golden:
documentos: 9
paginas esperadas: 77
paginas materializadas: 77
```

## Evidencia

```text
candidate: .tmp/phase1_main_full_candidate_20260720_r1
run_id: phase1_main_full_candidate_20260720_r1
pipeline_version: 2.0.0
resultado: processed=41, needs_review=14, failed=0, skipped=0

validation:
docs_normalized=data/docs_normalized
raw_root=data/docs_raw
mode=closure
golden=docs/ingestion/pdf_corpus_expected.json
run_id=phase1_official_20260720_guardrail_gate
result=passed, 0 errors
```

Pruebas registradas en el cierre:

```text
pip check: ok
pytest app/back/tests/ingestion -m 'not corpus': 245 passed, 2 deselected
pytest app/back/tests/ingestion/test_pdf_corpus_golden.py -m corpus: 2 passed
```

## Observaciones de cierre

- Las versiones `0.2` y `0.6` que bloqueaban metadata en PDF escaneados fueron
  extraidas con OCR regional de cabecera, no inferidas desde el golden.
- `minimum_content.must_preserve` acepta anclas literales ejecutables y rechaza
  prosa descriptiva no comprobable.
- `needs_review` no reabre Fase 1; define el contrato de consumo para Fase 2.

## Regla downstream

Las fases de chunking, indexacion y RAG solo deben indexar documentos
`processed`, salvo que exista una decision humana o regla explicita para un
documento `needs_review`.
