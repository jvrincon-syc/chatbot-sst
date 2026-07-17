# Cumplimiento Sprint 1.1 a 1.4

Fecha de revisión: 2026-07-16

## Resumen

El alcance 1.1 a 1.4 está implementado de forma operativa para el corpus actual:

- `data/docs_raw` se inventaria completo.
- Markdown, PDF digital y PDF escaneado tienen rutas de procesamiento separadas.
- OCR real usa OCRmyPDF con Tesseract en español.
- La salida normalizada conserva `text_raw`, `text_normalized`, metadatos y trazabilidad por página.
- La corrida real más reciente procesó 55 documentos, con 0 fallidos y 0 documentos en revisión.

Quedan pendientes o parciales algunos puntos de robustez previstos en el plan, principalmente persistencia PostgreSQL real, idempotencia incremental estricta, detección avanzada de estructura en PDF, extracción real de tablas complejas y una prueba lenta de OCR con escaneado real.

## Sprint 1.1 - Inventario, contratos y esqueleto

Estado: parcial alto.

Cumplido:

- Estructura base en `app/back/src/ingestion/`.
- Modelos Pydantic para inventario, metadata, pages, OCR y tables.
- JSON Schemas versionados exportados.
- Escaneo recursivo de `data/docs_raw`.
- Hash de contenido, tamaño, MIME y categoría inferida.
- Script `scripts/ingestion/run_inventory.py`.
- Manifest `_manifests/inventory.json`.
- Estados de procesamiento definidos.

Parcial o pendiente:

- PostgreSQL está configurado por `secrets.env`, pero la persistencia real en `documents_inventory` sigue mockeada/pendiente.
- El inventario calcula `content_hash`, pero la segunda corrida todavía no demuestra reprocesamiento selectivo completo por hash.
- La detección de extensiones dudosas usa MIME/firma básica; no cubre todos los casos raros del plan.

## Sprint 1.2 - Lectores base y primeras pruebas

Estado: parcial alto.

Cumplido:

- Lector Markdown.
- Lector PDF digital con extracción por página usando interfaz inyectable.
- Marcadores de página `<!-- page: N -->`.
- `.pages.json` generado.
- Contrato `.tables.json` definido.
- Pruebas unitarias de Markdown y PDF digital.
- Fallback desde PDF digital insuficiente hacia OCR.

Parcial o pendiente:

- Detección de títulos/subtítulos en PDF digital es heurística, no usa aún fuentes, negritas ni bloques visuales.
- Reconstrucción real de tablas complejas no está implementada; el contrato existe.
- Eliminación de encabezados y pies repetidos es básica y debe endurecerse con casos reales.
- La detección por `page_area`, `text_block_count` e `image_coverage` no está completa.

## Sprint 1.3 - OCR y documentos problemáticos

Estado: parcial alto.

Cumplido:

- OCRmyPDF integrado.
- Tesseract en español configurado y diagnosticable.
- Trabajo sobre copia temporal.
- `--deskew` y `--rotate-pages` activos.
- Sidecar de texto OCR.
- Timeout configurable por documento.
- `.ocr.json` generado.
- Confianza OCR y advertencias por página en contrato.
- Baja confianza y posible escritura manual se traducen en `needs_review`.
- `needs_review.json` y `errors.json` generados.
- Pruebas unitarias mockeadas.
- Doctor OCR (`scripts/ingestion/doctor_ocr.py`).

Parcial o pendiente:

- La confianza real de Tesseract se aproxima desde el sidecar; OCRmyPDF no entrega actualmente métricas palabra a palabra en este wrapper.
- Detección de escritura manual es heurística.
- Falta prueba lenta con escaneado real.
- `_review_queue/` existe como criterio del plan, pero no se generan capturas o casos visuales de revisión.

## Sprint 1.4 - Normalización y preservación

Estado: cumplido para el alcance base.

Cumplido:

- Unicode NFC.
- Normalización de saltos de línea.
- Eliminación de caracteres invisibles/de control.
- Corrección de palabras partidas por salto de línea.
- Reducción de espacios duplicados.
- Preservación de fechas, códigos, porcentajes, cifras e identificadores en pruebas.
- `text_raw` y `text_normalized` se conservan por página.
- Validación básica de salida contra modelos.

Parcial o pendiente:

- Eliminación de encabezados y pies repetidos debe ampliarse con patrones del corpus real.
- No existe aún glosario de siglas para normalización controlada.
- La auditoría de transformaciones está en artefactos y logs, pero no tiene reporte comparativo detallado por transformación.

## Seguimiento ejecutado

Después de esta auditoría se avanzó Sprint 1.6:

- Se amplió la validación post-procesamiento para cubrir checks obligatorios faltantes.
- Se agregaron pruebas RED/GREEN para auxiliares, hashes, estados finales, `needs_review` y `errors`.
- Se reejecutó el pipeline completo con 55 documentos procesados, 0 fallidos y 0 en revisión.
- La validación final pasó con 0 errores críticos.
