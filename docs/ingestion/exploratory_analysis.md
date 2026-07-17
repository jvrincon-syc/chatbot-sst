# Analisis exploratorio del corpus

Fecha de corte: 2026-07-16

## Resumen

```text
sample_size: 55 archivos revisados por inventario completo
folders_reviewed: convivencia_laboral, copasst, general_sst
document_types_found: Markdown, PDF digital, PDF escaneado/OCR
estimated_ocr_percentage: 3 de 55 documentos, 5.45%
unsupported_or_corrupt_files: 0 en la corrida final
```

El corpus actual mezcla documentos Markdown ya estructurados con PDFs corporativos. El pipeline se diseno para intentar primero lectura digital en PDF y caer a OCR solamente cuando la capa de texto no es suficiente.

## Tipos encontrados

- Markdown: 46 documentos.
- PDF digital: 6 documentos procesados con extractor PDF.
- PDF con OCR: 3 documentos procesados con OCRmyPDF + Tesseract en espanol.
- Archivos no soportados o corruptos: 0 en la corrida final.

## Patrones observados

- Rutas y nombres de archivo aportan senales fuertes de categoria y tema.
- Algunos PDFs tienen nombres generados con prefijos numericos.
- La mayoria de documentos Markdown ya tienen contenido semiestructurado.
- Los PDFs requieren conservar pagina para trazabilidad posterior.
- La salida normalizada debe reflejar la estructura de `docs_raw` para mantener navegacion manual simple.

## Umbrales y decisiones iniciales

- PDF digital se acepta si la extraccion produce al menos 10 palabras.
- Si la capa de texto es insuficiente, se usa OCR.
- OCR usa idioma `spa`, rotacion y deskew.
- Baja confianza OCR o posible escritura manual mandan el documento a `needs_review`.
- Clasificacion con confianza menor al umbral configurado manda el documento a revision.

## Riesgos para sprints posteriores

- La extraccion de tablas complejas queda como mejora futura.
- La deteccion avanzada de encabezados, pies y estilos de PDF requiere una libreria con informacion de layout mas rica.
- La confianza OCR actual depende de la salida disponible por OCRmyPDF sidecar; no hay aun metricas palabra a palabra reales.
- PostgreSQL esta configurado, pero la persistencia real del inventario se deja para integracion posterior.

## Ejemplos manuales

- `convivencia_laboral/manual/*.md`: Markdown estructurado.
- `general_sst/manuales/politica/*.pdf`: PDF corporativo.
- `general_sst/manuales/reglamento_interno_trabajo/*.pdf`: PDF de mayor tamano, sensible a OCR/extraccion por pagina.

## Resultado

El corpus queda apto para Fase 2 porque cada documento inventariado tiene salida normalizada o estado final trazable, y la validacion automatica confirma consistencia de metadatos, auxiliares, manifiestos y hashes.
