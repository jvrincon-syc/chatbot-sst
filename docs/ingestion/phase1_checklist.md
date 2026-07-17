# Checklist vigente de Fase 1 — Ingesta Schema 2.0

Fecha de corte: 2026-07-17

Este checklist reemplaza los cierres históricos de Schema 1.0. La fuente de
alcance permanece en `memory/`; el contrato técnico vigente está en el diseño
de calidad Schema 2.0 y el trabajo pendiente en el plan de gap closure.

## Contratos y pipeline

- [x] Contratos canónicos Schema 2.0 y adaptador legacy explícito.
- [x] Escritura nueva exclusivamente en Schema 2.0.
- [x] Identidad estable y paths POSIX relativos.
- [x] Bundles atómicos con Markdown, metadata, pages, OCR, tables y forms.
- [x] Capacidades desconocidas representadas como `not_evaluated`.
- [x] Confianza OCR medida solo con procedencia real.
- [x] Warnings materiales propagados a `needs_review`.
- [x] Pipeline candidato aislado y promoción fail-closed.

## Extracción

- [x] PDF digital procesado antes del fallback OCR.
- [x] Tablas y formularios digitales conectados al bundle.
- [x] OCRmyPDF 16.13.0 instalado en el entorno del proyecto.
- [x] Tesseract 5.4.0 instalado con idiomas `spa`, `eng` y `osd`.
- [x] PDFium conectado como rasterizador regional y de página completa.
- [x] Fallback PDFium → Tesseract para escaneos sin Ghostscript.
- [x] Tres PDF escaneados materializados.
- [x] Nueve bundles PDF materializados.
- [x] Las 77 páginas del corpus PDF materializadas.
- [x] Pausas activas procesado como `hybrid` con OCR regional.
- [ ] Ghostscript 10.07.1 x64 instalado y habilitado por soporte IT.
- [ ] Backend capaz de handwriting/firma conectado.
- [ ] Tablas y firmas de los escaneos evaluadas con capacidad suficiente.

## Validación vigente

Candidato de trabajo:

```text
.tmp/task6_candidate_full3
```

- [x] 9 fuentes PDF inventariadas.
- [x] 9 bundles presentes.
- [x] 77 páginas presentes y contiguas.
- [x] 0 documentos fallidos.
- [x] Gate estructural aprobado.
- [x] Golden de bijección aprobado.
- [x] Golden de total de páginas aprobado.
- [ ] Golden de metadata aprobado; quedan 44 diferencias.
- [ ] Golden de contenido aprobado; quedan 69 diferencias.
- [ ] Expectativas descriptivas del golden convertidas a aserciones
  semánticas o anclas textuales ejecutables.
- [ ] Estados `processed`/`needs_review` alineados con la auditoría visual.
- [ ] Suite completa reproducida sin errores ni skips de capacidades.
- [ ] Gate golden completo aprobado.
- [ ] Candidato promovido a `data/docs_normalized`.

## Bloqueos para el cierre

- Ghostscript requiere instalación corporativa.
- El TSV de los escaneos necesita reconciliación limpia antes de usarlo para
  título, clasificación y control documental.
- Las observaciones de handwriting permanecen `not_evaluated`.
- El golden mezcla anclas textuales con descripciones de auditoría; no se
  permite insertar esas descripciones artificialmente en el Markdown.

## Regla de cierre

No se autoriza chunking, indexación ni RAG sobre este candidato. La promoción
solo procede cuando el gate estructural y el golden semántico pasan en la misma
corrida y el diff de promoción ha sido revisado.
