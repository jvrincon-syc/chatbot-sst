# Diseño: ingestión PDF robusta y calidad documental verificable

Fecha: 2026-07-17

Estado: diseño vigente; implementación parcial

Alcance: Fase 1 local; sin persistencia PostgreSQL

Estado operativo: los contratos Schema 2.0, bundles atómicos, PDFium,
Tesseract, OCR regional, validación estructural y candidato de 9 bundles/77
páginas están implementados. El cierre semántico, handwriting, Ghostscript y
la promoción siguen pendientes; véase
`docs/ingestion/phase1_closure_report.md`.

## Problema

El pipeline actual puede producir artefactos estructuralmente válidos que hacen afirmaciones falsas:

- texto OCR no vacío se convierte en confianza `1.0`;
- ausencia de detector se convierte en `false`;
- una capa digital suficiente a nivel documento oculta páginas o regiones visuales no extraídas;
- ruta y filename pueden superar al título explícito en la clasificación;
- tablas, formularios, versiones y layout no se evalúan realmente;
- warnings de página no llegan al estado documental;
- rutas absolutas hacen que la validación dependa de la máquina.

La auditoría visual completa del subcorpus PDF está en `docs/ingestion/pdf_corpus_quality_audit.md`; el resultado esperado está codificado en `docs/ingestion/pdf_corpus_expected.json`.

## Objetivo

Regenerar los nueve PDF con una representación fiel, trazable y portable, y cambiar el contrato para que el sistema nunca presente como medición una suposición o un valor predeterminado.

Éxito significa:

1. cada página/región visible sustantiva está representada;
2. toda métrica declara procedencia y capacidad;
3. las incertidumbres permanecen explícitas;
4. la clasificación y control documental incluyen evidencia;
5. la validación compara invariantes semánticas además de forma.

## Enfoque elegido

Se implementará el enfoque 2 robusto mediante **schema 2.0**, con lector/adaptador para artefactos 1.0 y escritura exclusiva de 2.0.

Se elige 2.0 porque cambiar booleans a observaciones triestado, admitir `hybrid` y separar confianza de tipo/topic cambia la semántica del contrato. Mantener `1.0` o `1.1` haría demasiado fácil que consumidores antiguos interpreten `unknown` como `false`.

## Contrato de observaciones

Las capacidades de OCR, handwriting, tablas, formularios, deskew y rotación se modelan como observaciones:

```json
{
  "status": "detected | not_detected | not_evaluated",
  "value": true,
  "engine": "nombre opcional",
  "engine_version": "versión opcional",
  "method": "método opcional",
  "evidence": [
    {
      "page_number": 1,
      "region": null,
      "text": "evidencia breve"
    }
  ],
  "warnings": []
}
```

Invariantes:

- `not_evaluated` exige `value=null`;
- `detected` exige `value=true` y evidencia o un detector identificable;
- `not_detected` exige `value=false` y un detector capaz identificado;
- la ausencia de clave legacy nunca se adapta a `not_detected`.

## Confianza OCR

La confianza OCR es nullable y tipada:

```json
{
  "value": 0.87,
  "kind": "measured | estimated | unavailable",
  "engine": "tesseract",
  "engine_version": "...",
  "unit": "mean_word_confidence",
  "sample_size": 423
}
```

Reglas:

- sólo se usa `measured` si la librería/motor devuelve la métrica;
- sidecar no vacío no produce confianza;
- un proxy puede conservarse sólo como `estimated` y nunca gobierna por sí solo aprobación/rechazo;
- si el backend disponible no expone confianza real, `value=null`, `kind=unavailable`;
- los conteos de palabras de baja confianza requieren datos palabra a palabra reales; de lo contrario son null/no evaluados.

## Modelo por página y extracción híbrida

`extraction_method` documental admite `markdown`, `pdf_digital`, `ocr` y `hybrid`. Cada página mantiene su método y puede contener resultados por región.

Flujo por página:

1. extraer texto digital con geometría cuando esté disponible;
2. calcular cobertura visual/textual: cantidad de texto, regiones de imagen, huecos relevantes, caracteres anómalos y layout;
3. si una región con contenido potencial no está cubierta, ejecutar OCR de esa página/región;
4. reconciliar digital/OCR conservando ambos como evidencia y producir texto normalizado;
5. propagar warnings y razones de revisión al documento.

El programa de pausas activas deberá quedar `hybrid`: texto digital para el cuerpo y OCR de imágenes/instrucciones en páginas 8–15. No se forzará OCR de todas las páginas cuando sólo una región lo necesita.

## Texto raw, normalizado y layout

Cada página conservará:

- `text_raw`: extracción original por método;
- `text_normalized`: versión de recuperación;
- `blocks`: texto con página, bounding box, método y rol;
- `removed_spans`: encabezados/pies/watermarks retirados del cuerpo indexable;
- `normalization_actions`: uniones de palabras, limpieza y correcciones con before/after.

La detección de boilerplate usará consenso de bloques repetidos en posiciones superiores/inferiores de varias páginas. Nada se borra del raw; el texto repetido se etiqueta y se excluye del contenido indexable.

No se corregirán automáticamente citas legales o códigos si la corrección no es inequívoca. Esas diferencias generan `needs_review`.

## Tablas y formularios

La evaluación será explícita por página:

- detector/layout disponible y tabla encontrada → `detected`;
- detector capaz ejecutado y sin tabla → `not_detected`;
- extractor sin capacidad de tablas → `not_evaluated`.

Cada tabla preservará:

- página y bounding box;
- encabezados;
- filas/celdas;
- spans/merged cells cuando aplique;
- representación Markdown;
- extractor y calidad;
- warnings.

Los formularios preservarán grupos, etiquetas, controles/selecciones y áreas vacías. Un área en blanco visible es estructura del formulario, no texto perdido.

Fixtures de aceptación prioritarios:

- formato de queja;
- tabla AUMENTAN/DISMINUYEN;
- matriz Objetivos/Metas/Indicadores;
- aprobación y sanciones del reglamento;
- aprobación y control de cambios de la política SST.

## Clasificación

Se separan:

- `document_type`;
- `document_type_confidence`;
- `topic`;
- `topic_confidence`;
- `signals[]`;
- `route_prior`;
- `content_prediction`;
- `conflict_status`.

Orden de autoridad:

1. título explícito y campos de control documental;
2. contenido/estructura repetida;
3. filename;
4. ruta como prior débil.

La ruta nunca asigna alta confianza por sí sola. Si ruta y título discrepan, prevalece el título cuando es inequívoco y se registra el conflicto.

Taxonomía inicial:

- `manual`
- `formulario`
- `politica`
- `reglamento`
- `programa`
- `matriz`
- `otro`

No se usa `capacitacion` como sustituto de `programa`; puede permanecer como topic/categoría de navegación.

## Control documental

Se extraen de headers, portadas y tablas:

- título canónico;
- código tal como se ve y, separadamente, una forma normalizada opcional;
- versión;
- fecha de publicación;
- fecha efectiva;
- historial de cambios.

Cada valor lleva:

```json
{
  "value": "0.3",
  "value_raw": "0.3",
  "status": "extracted | not_found | not_evaluated | conflicting",
  "evidence": [
    {
      "page_number": 1,
      "pattern": "Versión 0.3",
      "source": "visual_text"
    }
  ]
}
```

Los timestamps del filename se guardan como señal de procedencia, nunca como fecha documental. Si contradicen el documento —como enero 2025 frente a `ACTUALIZADO29052026`— se genera conflicto y revisión.

## Paths e identidad

Los artefactos 2.0 almacenan:

- `source_relpath` POSIX relativo a `raw_root`;
- `normalized_relpath` POSIX relativo a `normalized_root`;
- `document_id` estable calculado desde identidad relativa normalizada;
- hashes de fuente y artefactos.

Las raíces absolutas viven en configuración runtime, no en el corpus versionado.

Adaptación legacy:

- si una ruta absoluta está bajo una raíz conocida, se relativiza;
- si no puede relativizarse, se conserva en `legacy_path` con warning;
- el validador no omite hash silenciosamente porque una ruta legacy no exista.

## Estados y revisión

Un documento sólo puede quedar `processed` si:

- todos los números de página son contiguos;
- no hay página/región sustantiva con cobertura insuficiente;
- los artefactos requeridos por método existen;
- no hay conflicto material sin resolver;
- todas las métricas afirmadas satisfacen su contrato.

Queda `needs_review` por:

- cobertura incompleta;
- OCR sin confianza medida cuando la calidad textual es dudosa;
- clasificación ruta/contenido conflictiva;
- código/versión/fecha conflictivos;
- índice/cuerpo inconsistente;
- tabla/formulario detectado pero no reconstruido;
- anomalía del documento fuente con impacto en recuperación.

## Compatibilidad y migración

- Reader: acepta 1.0 y 2.0.
- Writer: produce sólo 2.0.
- Adaptador `v1_to_v2`:
  - `contains_tables=false` → `not_evaluated`;
  - `contains_handwriting=false` → `not_evaluated`;
  - confianza OCR 1.0 del sidecar legacy → `estimated`, nunca `measured`;
  - `version=null` sin extractor → `not_evaluated`;
  - paths absolutos → relativos sólo con raíz conocida.
- No se reescriben artefactos históricos en sitio. Los PDF se regeneran desde raw después de que el nuevo pipeline pase pruebas.

## Validación

La validación 2.0 debe rechazar:

- `schema_version` ausente/desconocida;
- campos desconocidos (`extra=forbid`);
- processed sin `.pages.json`;
- OCR sin artefacto OCR;
- páginas duplicadas, fuera de orden o no contiguas;
- métodos de página incompatibles con el método documental;
- confianza `measured` sin motor/unidad/muestra;
- tabla fuera del rango de páginas;
- observación `detected` sin evidencia;
- paths absolutos canónicos;
- source faltante o hash no comprobable;
- inventario/metadata sin biyección;
- front matter divergente de metadata;
- status `processed` con review reasons materiales.

El validador del corpus PDF comparará además el resultado con `pdf_corpus_expected.json`: tipo, título/código/versión/fechas esperadas, page count, features y contenido mínimo.

## Estrategia TDD

Primero se añadirán pruebas fallidas para:

1. sidecar no vacío no crea confianza medida;
2. señal de handwriting ausente se adapta a `not_evaluated`;
3. extractor sin tablas no afirma ausencia;
4. versión repetida en header se extrae con evidencia;
5. ruta sola no produce alta confianza;
6. conflicto ruta/título queda explícito;
7. PDF mixto usa OCR por página y método `hybrid`;
8. warning de página se propaga;
9. boilerplate sale sólo del normalizado y conserva spans;
10. paths relativos sobreviven mover el árbol;
11. invariantes estrictos de schema/artefactos/páginas;
12. adapter legacy mapea falsos y confianza correctamente;
13. fixtures golden de los nueve PDF satisfacen clasificación y control documental;
14. las páginas 8–15 del programa preservan las instrucciones visibles;
15. tablas/formulario críticos conservan asociaciones.

Después se implementará el mínimo código para pasar cada grupo y se ejecutará la suite completa.

## Componentes afectados

- `schemas/artifacts.py`: modelos v2 y adaptadores.
- `ocr/ocrmypdf_engine.py`: métricas reales o unavailable; nada hard-coded como medición.
- `readers/pdf_digital_reader.py`: salida con layout/cobertura por página.
- `readers/pdf_scanned_reader.py`: confianza tipada y warnings reales.
- nuevo reconciliador híbrido por página/región.
- `classification/rules.py`: señales separadas y precedencia de contenido.
- nuevo extractor de control documental.
- nuevo detector auditable de boilerplate.
- extractores de tablas/formularios.
- `pipeline.py`: composición, paths relativos, artefactos y propagación de estado.
- `validation/normalized.py`: invariantes 2.0 y golden validation.
- tests unitarios, integración y regresión del corpus.

La selección concreta de librerías de layout/OCR se hará durante implementación después de inventariar dependencias ya disponibles. Si se necesita una dependencia nueva, se elegirá detrás de una interfaz y con fallback explícito a `not_evaluated`; nunca a un valor inventado.

## Fuera de alcance

- PostgreSQL e inventario multiusuario.
- certificación jurídica de vigencia;
- reconocimiento/autenticación de firmas;
- clasificación por LLM como autoridad;
- edición manual de normalizados como sustituto de regeneración;
- procesamiento de los 46 Markdown salvo compatibilidad de schema y validación.

## Entrega y despliegue

1. implementar contrato/adaptador con TDD;
2. implementar extracción y validación por capacidades;
3. reprocesar los nueve PDF en una corrida de auditoría;
4. comparar contra el golden;
5. revisar diffs y casos `needs_review`;
6. sólo después reemplazar artefactos versionados y actualizar el reporte de Fase 1.

No se declara nuevamente “Fase 1 cerrada” hasta que los criterios semánticos del golden estén satisfechos o las excepciones queden explícitamente aceptadas.
