# Cierre Fase 1

Fecha de cierre: 2026-07-16

## Resultado ejecutivo

Fase 1 queda cerrada para el alcance de ingesta y normalizacion documental local:

- Corpus inventariado: 55 archivos.
- Documentos procesados en corrida completa final: 55.
- Documentos omitidos por hash sin cambios en corrida incremental final: 55.
- Fallidos: 0.
- En revision: 0.
- Validacion post-procesamiento: passed, 0 errores criticos.
- Validacion post-procesamiento: 14 checks, 0 warnings.
- Pruebas automatizadas: 34 passing.
- OCR local: OCRmyPDF + Tesseract `spa` disponible.

## Evidencia de corrida

Corridas de cierre:

```text
phase1_final_full
phase1_final_incremental
phase1_final_post_skip_fix
```

La corrida completa reprocesa documentos cuando cambia el hash o cuando cambia la identidad documental calculada. La corrida incremental posterior compara `source_path`, `document_id` y `content_hash` contra `_manifests/inventory.json`; si no hay cambios y existen `.md` + `.metadata.json`, marca el documento como `skipped`.

Resultado medido:

```text
phase1_final_full: processed=55, failed=0, needs_review=0, skipped=0
phase1_final_incremental: processed=0, failed=0, needs_review=0, skipped=55
phase1_final_post_skip_fix: processed=0, failed=0, needs_review=0, skipped=55
validation_phase1_final_incremental: passed, errors=0, warnings=0, checks=14
```

Cobertura por metodo:

```text
markdown: 46
pdf_digital: 6
ocr: 3
```

Clasificacion:

```text
min_classification_confidence: 0.70
metadata_statuses: processed=55
```

## Que quedo implementado

- Inventario recursivo de `data/docs_raw`.
- `document_id` estable por ruta documental.
- `content_hash` SHA-256 para detectar cambios.
- Skip incremental de documentos sin cambios.
- Lectores aislados para Markdown, PDF digital y PDF escaneado/OCR.
- OCRmyPDF con Tesseract en espanol.
- Normalizacion conservadora con preservacion de datos criticos.
- Clasificacion documental por reglas de ruta, nombre y contenido.
- Markdown normalizado con front matter.
- Artefactos `.metadata.json`, `.pages.json`, `.ocr.json` cuando aplica.
- Manifiestos de corrida, inventario, errores, revision y validacion.
- Validacion obligatoria de hashes, schemas, IDs, estados y auxiliares.
- Pruebas unitarias e integracion basica.

## Gaps aceptados para fases posteriores

- Persistencia real en PostgreSQL de `documents_inventory`.
- Extraccion robusta de tablas complejas desde PDF.
- Deteccion avanzada de estructura visual en PDFs: fuentes, negritas, columnas, encabezados y pies por layout.
- Confianza OCR palabra a palabra real.
- Capturas visuales en `_review_queue/` para paginas dudosas.
- Clasificacion asistida por LLM para ambiguedades futuras.
- Prueba lenta con PDF escaneado real controlado como fixture.

## Posibles cambios recomendados

- Migrar el inventario a PostgreSQL antes de Fase 2 si se necesita auditoria multiusuario.
- Introducir una libreria de layout PDF si tablas y estilos se vuelven decisivos.
- Agregar `--force` o `--only-source` al pipeline si se requiere reprocesamiento manual selectivo desde CLI.
- Versionar fixtures PDF sinteticos pequenos para pruebas OCR lentas reproducibles.
- Definir politica de retencion de manifiestos y logs para no acumular corridas indefinidamente.

## Correccion de cierre incremental

Durante el cierre se detecto que una tercera corrida podia reprocesar documentos si el inventario previo venia de una corrida incremental con estado `skipped`. Se corrigio la politica para reutilizar artefactos cuando el estado previo sea `processed` o `skipped`, siempre que `source_path`, `document_id`, `content_hash`, `.md` y `.metadata.json` coincidan.

## Decision de cierre

La Fase 1 queda lista para alimentar chunking, indexacion y recuperacion en fases posteriores. Los gaps restantes no bloquean el objetivo de convertir `docs_raw` en `docs_normalized` validado, trazable y reproducible.
