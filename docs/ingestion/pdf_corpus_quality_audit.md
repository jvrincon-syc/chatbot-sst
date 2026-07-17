# Auditoría visual del corpus PDF y salida esperada

Fecha: 2026-07-17

## Resultado técnico

Se revisaron visualmente los **9 PDF y sus 77 páginas** bajo `data/docs_raw`, y se compararon con sus `.md`, `.metadata.json`, `.pages.json`, `.ocr.json` y tablas auxiliares disponibles.

La salida normalizada actual es consistente consigo misma, pero **no es todavía una representación semánticamente confiable del corpus**. La validación existente comprueba principalmente forma, IDs y conteos; no demuestra fidelidad visual, clasificación correcta, lectura completa de imágenes/tablas, ni que las métricas OCR sean reales.

Los nueve PDF requieren reprocesamiento o revisión. Los defectos de mayor impacto son:

1. confianza OCR `1.0` fabricada en los tres escaneados;
2. tres tipos documentales incorrectos (`formulario`, `programa`, `matriz`);
3. tablas y formularios visibles declarados como ausentes;
4. pérdida de texto incrustado en imágenes del programa de pausas activas;
5. versiones, códigos y fechas visibles no extraídos;
6. encabezados/pies repetidos y rutas absolutas antiguas;
7. estado `processed` sin warnings aun cuando hay pérdida o conflicto documental.

La referencia machine-readable que define el resultado mínimo esperado está en [pdf_corpus_expected.json](pdf_corpus_expected.json).

## Alcance y método

- Población: todos los PDF encontrados recursivamente bajo `data/docs_raw`.
- Documentos: 9.
- Páginas: 77 de 77.
- PDF con capa digital predominante: 6.
- PDF escaneados/OCR: 3.
- Método: render visual página por página, lectura del contenido visible, contraste con artefactos normalizados y trazado de las causas en el código.
- Criterio de completitud: conservar todo el texto sustantivo visible y las relaciones estructurales de tablas, formularios e imágenes con instrucciones. La mera presencia de texto extraído no prueba completitud.

Esta es una auditoría de fidelidad del corpus local; no certifica vigencia jurídica ni aprobación documental.

## Inventario esperado y discrepancias

| PDF | Pág. | Tipo esperado | Código / versión visibles | Estado actual material |
| --- | ---: | --- | --- | --- |
| `1761580555950_syc_RE.RH-04SST23102025.pdf` | 2 | formulario | RE.RH-04 SST / 0.3 | Tipo `manual`; formulario/tablas aplanados; versión nula |
| `1772036012249_syc_mrh03sstmanualdeconv.pdf` | 12 | manual | M.RH-03-SST / 0.2 | Tipo correcto; versión nula; encabezado repetido |
| `1781045303349_syc_politicadedesconexin.pdf` | 1 | política | PL.RH-03SST / 0.1 | OCR 1.0 ficticio; errores de código/texto; firma no detectada |
| `1781045390931_syc_politicadeprevencind.pdf` | 1 | política | PL.RH-01SST / 0.2 | OCR 1.0 ficticio; versión omitida; firma no detectada |
| `1761609513260_syc_RG.RH-01-SST23102025.pdf` | 6 | reglamento | RG.RH-01SST / 0.0 | Tipo correcto; versión nula; índice anuncia anexo ausente |
| `1711493199040_syc_pg-rh-10-sst.program.pdf` | 16 | programa | PG-RH-10-SST / 0.0 | Tipo `capacitacion`; pérdida de texto visual; tabla aplanada |
| `1768504433896_syc_1723156961461_syc_vial.pdf` | 1 | matriz | no visibles | Tipo `politica`; matriz de tres columnas aplanada |
| `1780069704133_syc_REGLAMENTOACTUALIZADO29052026.pdf` | 36 | reglamento | sin versión visible; enero 2025 | Tipo correcto; fecha omitida; conflicto con filename 2026 |
| `1778000305710_syc_politicadeseguridady.pdf` | 2 | política | PL.RH-01-SST / 0.6 | OCR 1.0 ficticio; tablas aplanadas; versión OCR contradictoria |

## Hallazgos por documento

### El formato de queja está clasificado como manual

El título visible dice “FORMATO PARA INTERPONER QUEJA POR PRESUNTO ACOSO ANTE EL COMITÉ DE CONVIVENCIA”. Las dos páginas contienen grupos de campos, tablas de selección, áreas para hechos/pruebas/sugerencias y firma. El resultado correcto es `document_type=formulario`, con topic Comité de Convivencia Laboral, código visible `RE.RH-04 SST`, versión `0.3`, `contains_form=detected` y `contains_tables=detected`.

El actual `.md` aplana las celdas y repite el encabezado. La página 2 también expone texto de encabezado fuera del recorte visual. Esa diferencia entre crop visible y capa de texto debe conservarse como warning de layout, no mezclarse sin explicación en el cuerpo.

### El manual de convivencia conserva el cuerpo, pero no su control documental

Las 12 páginas incluyen introducción, políticas, comité, marco legal, valores, normas, derechos/deberes y contacto. El tipo `manual` es correcto. En todas las páginas es visible `M.RH-03-SST`, versión `0.2`, en un encabezado tabular. La salida actual repite ese encabezado en todos los chunks, deja `version=null` y contiene palabras partidas.

### Las dos políticas de convivencia son escaneos firmados con errores OCR

La Política de Desconexión Laboral muestra `PL.RH-03SST`, versión `0.1`, y una firma manuscrita. El OCR produce, entre otros, `PL.RH-035ST`, `Sistomas`, `huestros` y `mecanísmos`.

La Política de Prevención de Acoso Laboral muestra `PL.RH-01SST`, versión `0.2`, fecha 2025-12-06 y firma. El OCR produce `PL.RH-018ST`, inserta `DN humana` y cambia Joan Mauricio por Joan Nauricio.

En ambos casos `ocr_confidence=1.0` no viene de Tesseract/OCRmyPDF; se asigna porque el sidecar no está vacío. Por tanto no puede usarse para aprobar calidad. `contains_handwriting=false` tampoco significa ausencia: no hubo un detector capaz.

### El reglamento del comité tiene un conflicto interno en el índice

Las seis páginas corresponden a un reglamento, código `RG.RH-01SST`, versión `0.0`. El contenido cubre composición, operación, funciones, quejas, vigencia y modificaciones. El índice anuncia “7. ANEXO” en la página 6, pero el cuerpo fuente finaliza en 6.2 y no contiene el anexo. Debe quedar `needs_review` hasta verificar el documento controlado; la ingestión no debe inventar ni omitir silenciosamente esa sección.

### El programa de pausas activas requiere extracción híbrida por página/región

Las 16 páginas se titulan “PROGRAMA DE PAUSAS ACTIVAS”, código `PG-RH-10-SST`, versión `0.0`, marzo de 2024. No es una `capacitacion`, sino un `programa`.

La página 6 contiene una tabla real `AUMENTAN / DISMINUYEN`. Las páginas 8–15 mezclan texto digital con imágenes que contienen instrucciones. En las páginas 13–15 son visibles etiquetas y pasos como `Bien`, `Mal`, `45 a 70 cm`, ajustes de silla/teclado/pantalla y zonas de trabajo; la salida actual pierde buena parte de esa información y las páginas 14–15 quedan casi sólo con el encabezado.

El fallback debe decidirse por página o región. Un conteo total de palabras del documento oculta páginas incompletas.

### Seguridad vial es una matriz de objetivos, metas e indicadores

La única página tiene una tabla central con tres columnas (`OBJETIVOS`, `METAS`, `INDICADORES`) y tres filas. El tipo esperado es `matriz`, no `politica`. Cada fórmula debe permanecer asociada a su objetivo y meta, conservando numerador, denominador y multiplicación por 100. No hay código, fecha o versión visibles; los timestamps del filename no son evidencia documental.

### El reglamento interno está completo por páginas, pero pierde estructura y tiene fechas conflictivas

Se revisaron las 36 páginas: portada, índice, aprobación y capítulos/artículos hasta disposiciones finales. La portada dice enero de 2025; el filename contiene `ACTUALIZADO29052026`. Esa aparente fecha de actualización no debe sobreescribir automáticamente la fecha visible ni convertirse en vigencia sin validación de control documental.

La página 3 contiene una tabla de elaboración/aprobación y la página 28 una tabla de sanciones. Las 36 páginas incluyen watermark `CONFIDENCIAL` y pie corporativo repetido. También hay palabras partidas que afectan citas normativas. En las páginas 35–36 los dobles asteriscos son visibles en el PDF fuente; deben marcarse como anomalía fuente, no limpiarse silenciosamente como si fueran Markdown generado por el pipeline.

### La política de SST contiene dos tablas críticas y control de cambios

La página 1 muestra `PL.RH-01-SST`, versión `0.6`, fecha 2025-12-16 y firma. La página 2 contiene tabla de elaboración/aprobación/verificación y control de cambios de versiones 0.0 a 0.6. El OCR aplana ambas, lee el encabezado de página 2 como 0.5 y la última versión como `10.6`. El resultado documental debe usar 0.6 con evidencia visual y registrar el conflicto OCR; nunca confianza perfecta.

## Causas raíz confirmadas

1. `OcrMyPdfEngine` convierte texto no vacío en confianza `1.0` y vacío en `0.0`; no consume una métrica real del motor.
2. `PdfScannedReader` promedia esas pseudoconfianzas y fija `low_confidence_word_count=0`.
3. Handwriting, deskew y rotación se rellenan con valores predeterminados que parecen mediciones.
4. `PdfDigitalReader` no extrae layout/tablas y decide el fallback por el total de palabras del documento.
5. Las advertencias de páginas incompletas no se propagan al documento.
6. La clasificación pondera ruta/filename más que contenido y mezcla confianza de tipo con confianza de topic.
7. `version` no tiene extractor; el inventario y metadata la dejan siempre nula.
8. `contains_tables=false` se deriva de que no exista un artefacto de tablas, no de una evaluación capaz.
9. No existe eliminación auditable de encabezados/pies repetidos.
10. Los artefactos persisten rutas absolutas de otra máquina y el validador omite hashes si esas rutas no existen.

## Qué significa esta auditoría para la Fase 1

La afirmación anterior de “Fase 1 cerrada” debe reinterpretarse como **cierre estructural parcial**: los 55 archivos tienen artefactos con esquemas parseables, pero la fidelidad semántica de los PDF no está cerrada. Para este subcorpus PDF, el estado correcto es 9/9 `needs_review` hasta reprocesar y validar contra la referencia golden.

No se recomienda editar manualmente los `.md/.metadata/.pages` actuales como corrección primaria. Deben regenerarse desde `docs_raw` con el pipeline corregido, preservando trazabilidad y haciendo reproducible la solución.

## Criterios de aceptación del reprocesamiento

- 77 páginas presentes, contiguas y en orden.
- Ninguna confianza OCR numérica sin procedencia del motor/librería.
- `not_evaluated` separado de `not_detected`.
- Clasificación explícita de formulario, manual, política, reglamento, programa y matriz.
- Versión/código/fecha con evidencia de página/patrón.
- OCR híbrido en páginas/regiones con texto visual ausente.
- Tablas/formularios con relaciones estructurales preservadas.
- Headers, footers y watermarks separados del cuerpo indexable con spans auditables.
- Warnings y `needs_review` propagados ante pérdida, conflicto o anomalía fuente.
- Paths relativos POSIX y validación portable.

## Limitaciones

- La auditoría verifica lo visible en los PDF locales, no la autenticidad de firmas ni la vigencia jurídica.
- No se infirieron fechas desde timestamps de filename.
- La escritura manuscrita se marcó por observación visual; una futura detección automática deberá declarar motor, evidencia y alcance.
- “Toda la información” significa todo texto/estructura visible relevante para recuperación y trazabilidad; imágenes decorativas no requieren descripción salvo que contengan instrucciones o significado documental.
