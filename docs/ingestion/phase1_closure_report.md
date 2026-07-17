# Estado de cierre de Fase 1 — Ingesta Schema 2.0

Fecha de verificación: 2026-07-17

## Decisión vigente

Fase 1 tiene cierre estructural, pero todavía no tiene cierre semántico.

No se promovió ningún candidato y no se autoriza todavía chunking, indexación
ni RAG. La promoción permanece condicionada a que los gates estructural y
golden pasen simultáneamente.

## Capacidades del entorno

Verificado:

```text
OCRmyPDF: 16.13.0
Tesseract: 5.4.0.20240606
Idiomas Tesseract: spa, eng, osd
pdfplumber: available
PDFium: available
OpenCV: available
pip check: No broken requirements found
```

Pendiente:

```text
Ghostscript: unavailable
Versión solicitada a IT: Ghostscript 10.07.1 x64
```

El entorno usa PDFium → Tesseract como fallback directo para materializar
escaneos mientras Ghostscript no está disponible. Ghostscript sigue siendo
necesario para completar y verificar el camino OCRmyPDF de preprocesamiento.

## Candidato vigente

```text
.tmp/task6_candidate_full3
run_id: task6_full3
pipeline_version: 2.0.1
```

Resultado:

```text
PDF inventariados: 9
Bundles materializados: 9
Páginas esperadas: 77
Páginas materializadas: 77
processed: 4
needs_review: 5
failed: 0
```

Los tres PDF escaneados ya producen bundles. El programa de pausas activas se
procesa como `hybrid` y conserva OCR regional con confianza Tesseract medida.

## Gates

Gate estructural:

```text
16 checks estructurales: passed
golden_bijection: passed
golden_pages: passed
golden_page_total: passed
```

Gate semántico:

```text
golden_metadata: failed, 44 detalles
golden_content: failed, 69 detalles
```

El aumento respecto al candidato anterior no representa pérdida de cobertura.
El candidato anterior solo tenía seis bundles y no evaluaba las expectativas
de los tres escaneos. El candidato vigente evalúa los nueve documentos.

## Diferencias semánticas principales

### Escaneos

- Parte de la salida TSV aparece mezclada con el texto OCR y contamina títulos.
- Códigos OCR como `PL.RH-035ST` no coinciden con el control visible.
- Versiones y fechas permanecen sin extraer.
- Las tablas y firmas siguen `not_evaluated`.
- La clasificación resultante puede ser `formulario`, `procedimiento` o
  `programa` cuando el golden exige `politica`.

### Documentos digitales

- Persisten diferencias de normalización exacta en títulos y códigos.
- Faltan fechas visibles de pausas activas y del reglamento interno.
- Algunos documentos quedan `processed` cuando la auditoría exige
  `needs_review`.
- Forms y handwriting permanecen `not_evaluated` cuando el golden exige una
  evaluación capaz.

### Contrato golden

Parte de `minimum_content` contiene descripciones de auditoría —por ejemplo,
`three objective rows` o `cover and January 2025 date`— que el comparador busca
literalmente en documentos en español. Estas entradas deben convertirse en
aserciones estructuradas o anclas textuales reales. No deben copiarse al
Markdown para hacer pasar el gate.

## Trabajo restante

1. Instalar y verificar Ghostscript 10.07.1 x64.
2. Limpiar y reconciliar la salida TSV de los escaneos.
3. Extraer títulos, códigos, versiones y fechas con evidencia.
4. Conectar un backend capaz para handwriting/firma.
5. Evaluar tablas/formularios de los escaneos.
6. Corregir el contrato ejecutable de contenido mínimo.
7. Regenerar un candidato limpio.
8. Ejecutar suite, gate estructural y golden.
9. Promover solo si todos pasan.

## Evidencia conservada

- Auditoría visual: `docs/ingestion/pdf_corpus_quality_audit.md`.
- Golden ejecutable: `docs/ingestion/pdf_corpus_expected.json`.
- Diseño vigente: `docs/superpowers/specs/2026-07-17-robust-pdf-ingestion-quality-design.md`.
- Plan vigente: `docs/superpowers/plans/2026-07-17-pipeline-gap-closure.md`.
