# Checklist Fase 1 parcial

Alcance ejecutado: sprints 1.0 a 1.7, con PostgreSQL pendiente de persistencia real.

## Sprint 1.0 - Analisis exploratorio

- [x] Inventariar corpus real completo como muestra inicial.
- [x] Identificar distribucion Markdown/PDF digital/PDF OCR.
- [x] Documentar patrones y riesgos.
- [x] Documentar umbrales iniciales.
- [x] Crear `docs/ingestion/exploratory_analysis.md`.

## Sprint 1.1 - Inventario, contratos y esqueleto

- [x] Crear estructura `app/back/src/ingestion/`.
- [x] Crear estructura `app/back/tests/ingestion/`.
- [x] Definir modelos Pydantic para metadata, pages, OCR, tables e inventario.
- [x] Exportar JSON Schemas versionados.
- [x] Escanear recursivamente `data/docs_raw`.
- [x] Calcular hash, tamaño, MIME y categoría inferida.
- [x] Generar `data/docs_normalized/_manifests/inventory.json`.
- [x] Implementar `scripts/ingestion/run_inventory.py`.
- [x] Mantener `document_id` estable por ruta documental.
- [x] Usar `content_hash` para detectar cambios.
- [x] Mantener PostgreSQL como integración pendiente/mockeada.

## Sprint 1.2 - Lectores base y primeras pruebas

- [x] Implementar lector Markdown.
- [x] Implementar lector PDF digital con `pypdf` e interfaz inyectable.
- [x] Generar Markdown normalizado con front matter.
- [x] Generar `.pages.json`.
- [x] Dejar `.tables.json` soportado por contrato.
- [x] Agregar pruebas unitarias de Markdown y PDF digital con extractor fake.
- [x] Procesar PDFs digitales antes de caer a OCR.

## Sprint 1.3 - OCR y documentos problemáticos

- [x] Definir interfaz de OCR.
- [x] Implementar `MockOcrEngine`.
- [x] Implementar motor OCRmyPDF + Tesseract español.
- [x] Trabajar sobre copia temporal del PDF.
- [x] Configurar `--deskew` y `--rotate-pages`.
- [x] Diagnosticar dependencia faltante de OCRmyPDF/Tesseract/idioma.
- [x] Registrar confianza OCR por página en contrato.
- [x] Marcar baja confianza y posible escritura manual como razones de revisión.
- [x] Generar `needs_review.json` y `errors.json`.
- [x] Agregar prueba unitaria de OCR mockeado.
- [x] Integrar OCRmyPDF/Tesseract real por wrapper de comandos.
- [x] Instalar `ocrmypdf` en el sistema local.
- [x] Instalar idioma `spa` de Tesseract en el sistema local.
- [x] Generar texto desde OCRmyPDF con `--sidecar`.
- [x] Configurar timeout OCR por documento.
- [ ] Crear prueba lenta con escaneado real.

## Sprint 1.4 - Normalización y preservación

- [x] Normalizar Unicode a NFC.
- [x] Normalizar saltos de línea.
- [x] Eliminar caracteres de control.
- [x] Corregir palabras partidas por salto de línea.
- [x] Reducir espacios duplicados.
- [x] Preservar fechas, códigos, porcentajes e identificadores en pruebas.
- [x] Mantener `text_raw` y `text_normalized` por página.

## Sprint 1.5 - Clasificación documental

- [x] Implementar reglas por ruta y nombre.
- [x] Implementar patrones por encabezado.
- [x] Registrar `classification_confidence` en metadata.
- [x] Enviar casos de baja confianza a `needs_review`.
- [x] Añadir pruebas para reglas y umbrales.
- [x] Clasificar todo el corpus real con confianza mínima 0.70.
- [ ] Añadir clasificación asistida por LLM para ambigüedades futuras.

## Sprint 1.6 - Manifiestos, logs y validación post-procesamiento

- [x] Generar `.metadata.json` completo por documento procesado.
- [x] Generar manifiesto global por corrida.
- [x] Generar `run_<timestamp>_details.log`.
- [x] Registrar eventos por documento y etapa.
- [x] Implementar `scripts/ingestion/validate_normalized.py`.
- [x] Generar `validation_<run_id>.json`.
- [x] Validar `.md` con metadata asociada.
- [x] Validar metadata de documentos `processed` contra Markdown existente.
- [x] Validar IDs duplicados en metadatos.
- [x] Validar auxiliares huérfanos.
- [x] Validar que auxiliares pertenezcan al mismo `document_id` de su metadata.
- [x] Validar esquema y versión de metadata, pages, OCR y tables.
- [x] Validar consistencia de `page_count` en pages/OCR/tables.
- [x] Validar hashes de origen contra `inventory.json`.
- [x] Validar que `needs_review` esté en `needs_review.json`.
- [x] Validar que `failed` esté en `errors.json`.
- [x] Validar que no haya documentos `processed` también presentes en `errors.json`.
- [x] Validar que inventario no quede con estado `pending`.
- [x] Crear pruebas de IDs/auxiliares, archivos huérfanos, hashes inconsistentes y estados finales.

## Sprint 1.7 - Integracion end-to-end y cierre

- [x] Ejecutar pipeline completo sobre corpus real.
- [x] Verificar segunda corrida sin cambios como incremental.
- [x] Reprocesar documentos cuando cambia el hash.
- [x] Revisar `needs_review.json` y `errors.json`.
- [x] Medir cobertura de corpus y metodos de extraccion.
- [x] Ejecutar pruebas automatizadas.
- [x] Ejecutar validacion final.
- [x] Documentar ejecucion incremental y reprocesamiento por hash.
- [x] Crear `docs/ingestion/phase1_closure_report.md`.

## Instalación y configuración

- [x] Crear `package.json` con scripts de instalación y operación.
- [x] Crear `requirements.txt` y `requirements-dev.txt`.
- [x] Crear `secrets.example.env`.
- [x] Mantener `secrets.env` ignorado por Git.
- [x] Crear doctor OCR (`scripts/ingestion/doctor_ocr.py`).

## Validación actual

- [x] Pruebas automatizadas: 34 passing.
- [x] Corrida real: 55 documentos procesados.
- [x] Corrida incremental real: 55 documentos omitidos por hash sin cambios.
- [x] Corrida real: 0 documentos en `needs_review`.
- [x] Corrida real: 6 PDFs digitales procesados.
- [x] Corrida real: 3 PDFs procesados por OCR.
- [x] Corrida real: confianza de clasificación mínima 0.70.
- [x] Corrida real: 0 fallidos.
- [x] Validación final: passed, 0 errores críticos, 14 checks.
- [x] Segunda corrida sin cambios: documentos marcados como `skipped`.
