# Fase 1 — Pipeline de Ingesta y Normalización Documental

## chatbot-sst · De `docs_raw` a `docs_normalized`

---

## 1. Objetivo de la fase

Construir el pipeline que convierte todos los documentos crudos almacenados en `data/docs_raw` —Markdown, PDF digitales y PDF escaneados— en una representación Markdown normalizada, validada y trazable, almacenada en `data/docs_normalized`, lista para ser consumida por las etapas posteriores de chunking, indexación y recuperación.

Esta fase **no incluye** embeddings, chunking parent-child, grafo ni generación de respuestas. Su alcance es:

- Analizar inicialmente el corpus real.
- Inventariar los archivos.
- Detectar su formato y condición.
- Extraer y normalizar su contenido.
- Clasificar los documentos.
- Generar metadatos y archivos auxiliares con esquemas definidos.
- Registrar detalladamente cada ejecución.
- Separar los documentos fallidos o que requieren revisión.
- Validar automáticamente la consistencia de la salida.

### Criterio de éxito de la fase

Al finalizar, por cada archivo detectado en `docs_raw` deberá existir una trazabilidad completa en el inventario, incluso cuando el documento no pueda procesarse.

Por cada archivo procesado correctamente deberá existir en `docs_normalized`:

- Un `.md` normalizado con front-matter de procedencia.
- Un `.metadata.json` con los metadatos del documento.
- Cuando aplique: `.pages.json`, `.ocr.json` y `.tables.json` conformes a sus esquemas.
- Un registro en el manifiesto global con estado `processed`, `failed`, `needs_review` o `skipped`.
- Eventos detallados en el log de la ejecución.

Además, la validación post-procesamiento deberá confirmar que:

- Todo `.md` tiene su correspondiente `.metadata.json`.
- Los `document_id` son únicos.
- No existen archivos auxiliares huérfanos.
- Los hashes de origen coinciden con el inventario.
- Los archivos JSON cumplen el esquema definido.
- Los documentos fallidos o dudosos aparecen en `needs_review.json` o `errors.json`.
- Las pruebas automatizadas del módulo de ingesta se ejecutan satisfactoriamente.

---

## 2. Alcance funcional

| Incluido en Fase 1 | Excluido de Fase 1 — fases posteriores |
|---|---|
| Análisis exploratorio manual de `docs_raw` | Parent-child chunking |
| Inventario completo de `docs_raw` | Embeddings e interfaz de proveedores |
| Detección de formato y condición documental | Búsqueda lexical/vectorial |
| Extracción de contenido por página | Grafo ligero |
| OCR con OCRmyPDF + Tesseract en español | Contextualización conversacional |
| Normalización estructural y textual | Generación y verificación de respuestas |
| Clasificación documental por tipo y tema | Redis, caché y FAQ |
| Generación de Markdown normalizado con procedencia | Frontend |
| Esquemas versionados de archivos auxiliares | |
| Logs detallados por documento y ejecución | |
| Cola de documentos en revisión | |
| Validación post-procesamiento | |
| Pruebas unitarias e integración básica | |

---

## 3. Flujo de la fase

```text
[0] Análisis exploratorio manual de docs_raw
   │
   ▼
docs_raw
   │
   ▼
[1] Inventario del archivo
   │
   ▼
[2] Detección de formato y condición
   │
   ├── Markdown
   ├── PDF digital
   ├── PDF escaneado
   └── Archivo no soportado, corrupto o dudoso
   │
   ▼
[3] Extracción de contenido
   │
   ▼
[4] Normalización estructural y textual
   │
   ▼
[5] Clasificación documental
   │
   ▼
[6] Generación de Markdown y archivos auxiliares
   │
   ▼
[7] Metadatos, manifiestos y logs
   │
   ▼
[8] Validación post-procesamiento
   │
   ├── válido ────────────────► docs_normalized
   │
   └── dudoso o fallido ─────► needs_review / errors
```

El pipeline no deberá detener toda la ejecución por el fallo de un único documento. Cada documento se procesará de forma aislada, se registrará su resultado y el proceso continuará con el siguiente archivo.

---

## 4. Módulos a construir

### Código principal: `app/back/src/ingestion/`

```text
ingestion/
├── inventory/          # Escaneo de docs_raw, hash e inventario inicial
├── readers/            # Lectores Markdown, PDF digital y PDF escaneado
├── ocr/                # OCRmyPDF, Tesseract, confianza y advertencias
├── normalization/      # Texto raw y texto normalizado
├── classification/     # Clasificación documental y temática
├── schemas/            # Modelos y contratos de metadata/pages/ocr/tables
├── manifests/          # Inventario, corridas, errores y needs_review
├── logging/            # Logs estructurados por ejecución y documento
└── validation/         # Validación de consistencia post-procesamiento
```

### Pruebas: `app/back/tests/ingestion/`

```text
tests/ingestion/
├── fixtures/
│   ├── markdown/
│   ├── pdf_digital/
│   ├── pdf_scanned/
│   ├── malformed/
│   └── expected/
├── test_inventory.py
├── test_markdown_reader.py
├── test_pdf_digital_reader.py
├── test_pdf_scanned_reader.py
├── test_normalization.py
├── test_schemas.py
├── test_validation.py
└── test_pipeline_integration.py
```

---

## 5. Desglose de tareas por módulo

### 5.0 Análisis exploratorio manual de `docs_raw`

Antes de implementar lectores o reglas de normalización, dedicar aproximadamente medio día a revisar manualmente una muestra representativa de cada carpeta del corpus.

#### Muestra mínima

Seleccionar, cuando existan:

- Al menos un Markdown por carpeta.
- Al menos un PDF digital simple por carpeta.
- Al menos un PDF digital con tablas o estructura compleja.
- Al menos un PDF escaneado.
- Documentos con formularios.
- Documentos de varias páginas.
- Archivos con nombres, extensiones o rutas atípicas.

#### Aspectos por revisar

- PDFs corruptos o protegidos.
- Documentos sin extensión o con extensión incorrecta.
- Formularios escaneados torcidos.
- Páginas rotadas.
- Escritura manual.
- Tablas complejas, combinadas o partidas entre páginas.
- Encabezados y pies repetidos.
- Documentos con varias columnas.
- Imágenes sin texto reconocible.
- Baja resolución o alto ruido visual.
- Duplicados o versiones aparentemente repetidas.
- Nombres de archivo que permitan inferir categoría, fecha o versión.

#### Entregable

Crear `docs/ingestion/exploratory_analysis.md` con:

```text
sample_size
folders_reviewed
document_types_found
problem_patterns
estimated_ocr_percentage
unsupported_or_corrupt_files
initial_threshold_recommendations
risks_for_sprints
manual_examples
```

Las conclusiones deberán utilizarse para ajustar:

- Umbral de detección de PDF escaneado.
- Reglas de rotación y deskew.
- Estrategia de tablas.
- Casos de prueba.
- Estimación realista del Sprint 1.3.
- Criterios para marcar un documento como `needs_review`.

---

### 5.1 `inventory/` — Inventario inicial

Por cada archivo detectado en `docs_raw`, registrar:

```text
document_id
source_path
document_name
detected_extension
reported_extension
mime_type
content_hash
file_size
ingestion_date
category_inferred
document_version
page_count
processing_status = pending
pipeline_version
corpus_version
```

#### Tareas

- [ ] Recorrer recursivamente `data/docs_raw/**`.
- [ ] Detectar archivos sin extensión o con extensión inconsistente mediante MIME y firma binaria.
- [ ] Calcular hash de contenido para detectar duplicados o archivos ya procesados.
- [ ] Comparar contra el inventario existente para procesar únicamente archivos nuevos o modificados.
- [ ] Inferir categoría desde la carpeta contenedora.
- [ ] Asignar un `document_id` estable para el mismo archivo mientras su identidad documental no cambie.
- [ ] Registrar el inventario en PostgreSQL (`documents_inventory`) y generar `_manifests/inventory.json`.
- [ ] Marcar archivos corruptos, no soportados o ambiguos como `failed` o `needs_review` sin omitirlos del inventario.

#### Criterios de aceptación

- Todos los archivos encontrados tienen un registro de inventario.
- Dos archivos con el mismo contenido son identificables como duplicados mediante `content_hash`.
- Una segunda ejecución sin cambios no reprocesa documentos innecesariamente.
- Ningún archivo queda fuera del reporte por tener extensión desconocida.

---

### 5.2 `readers/` — Detección de formato y extracción

#### Detección de formato

- [ ] `.md` válido → lector Markdown.
- [ ] `.pdf` con capa de texto suficiente → lector PDF digital.
- [ ] `.pdf` sin capa de texto o con densidad insuficiente → lector PDF escaneado.
- [ ] Archivo con extensión dudosa → detección por MIME y firma.
- [ ] Archivo ilegible, protegido o corrupto → `failed` o `needs_review`.

La regla inicial para distinguir PDF digital y escaneado deberá analizar una muestra de las primeras páginas y considerar:

```text
extractable_character_count
extractable_word_count
page_area
text_block_count
image_coverage
```

Los umbrales deberán ser configurables y ajustarse con base en el análisis exploratorio.

#### Lector Markdown: `readers/markdown_reader.py`

- [ ] Conservar encabezados, listas, tablas y referencias.
- [ ] Normalizar espacios y saltos de línea.
- [ ] Eliminar encabezados repetidos cuando sean claramente ruido.
- [ ] Validar estructura mínima.
- [ ] Generar una advertencia si no existe título identificable.
- [ ] Mantener la ruta relativa en `docs_normalized`.
- [ ] Producir `text_raw` y `text_normalized`.

#### Lector PDF digital: `readers/pdf_digital_reader.py`

- [ ] Extraer contenido página por página.
- [ ] Conservar número de página.
- [ ] Detectar títulos y subtítulos mediante tamaño de fuente, negrita y patrones.
- [ ] Conservar listas.
- [ ] Reconstruir tablas cuando sea viable.
- [ ] Guardar tablas detectadas en `.tables.json`.
- [ ] Eliminar encabezados y pies repetidos entre páginas.
- [ ] Corregir palabras divididas por salto de línea.
- [ ] Detectar páginas con extracción anormalmente baja.
- [ ] Convertir a Markdown con marcadores `<!-- page: N -->`.
- [ ] Generar `.pages.json`.

#### Lector PDF escaneado: `readers/pdf_scanned_reader.py` y `ocr/`

- [ ] Conservar intacto el archivo original en `docs_raw`.
- [ ] Trabajar siempre sobre una copia temporal.
- [ ] Ejecutar OCRmyPDF.
- [ ] Configurar Tesseract con idioma español.
- [ ] Aplicar rotación o deskew cuando corresponda.
- [ ] Generar una copia temporal con capa de texto.
- [ ] Extraer contenido por página desde la copia OCR.
- [ ] Registrar confianza OCR por página.
- [ ] Detectar páginas con posible escritura manual mediante heurísticas.
- [ ] Marcar fragmentos dudosos.
- [ ] Generar `.pages.json` y `.ocr.json`.
- [ ] Normalizar el resultado con el mismo contrato utilizado para PDF digital.
- [ ] Eliminar las copias temporales al finalizar, salvo cuando se configure retención para depuración.

#### Criterios de aceptación

- Cada lector devuelve una estructura común independiente del formato de entrada.
- Los fallos de un lector se registran sin detener el procesamiento de otros documentos.
- Se conserva el número de página para todos los PDF.
- Los documentos dudosos se envían a revisión en lugar de marcarse silenciosamente como procesados.

---

### 5.3 `normalization/` — Normalización estructural y textual

El módulo produce dos representaciones:

- `text_raw`: contenido extraído sin transformaciones semánticas.
- `text_normalized`: contenido preparado para etapas posteriores.

#### Transformaciones permitidas

- [ ] Corrección de espacios duplicados.
- [ ] Unificación Unicode en NFC.
- [ ] Eliminación de caracteres invisibles o de control.
- [ ] Reconstrucción de palabras partidas por salto de línea.
- [ ] Eliminación de encabezados y pies repetidos.
- [ ] Normalización de saltos de línea a `\n`.
- [ ] Identificación de títulos y jerarquía H1–H4.
- [ ] Conversión de listas a Markdown estándar.
- [ ] Conversión de tablas a Markdown.
- [ ] Normalización controlada de siglas mediante glosario.

#### Transformaciones prohibidas

El pipeline no deberá modificar automáticamente:

- [ ] Nombres propios.
- [ ] Fechas.
- [ ] Porcentajes.
- [ ] Números de identificación.
- [ ] Códigos de formularios.
- [ ] Artículos y numerales.
- [ ] Plazos.
- [ ] Valores de tablas.

#### Auditoría

- Cada página deberá conservar tanto `text_raw` como `text_normalized`.
- Las transformaciones relevantes deberán ser reproducibles.
- Las advertencias de normalización deberán registrarse en el log detallado.
- Las pruebas deberán verificar que fechas, cifras, códigos y porcentajes se mantienen intactos.

---

### 5.4 `classification/` — Clasificación documental

#### Clasificación del documento completo

Tipo documental permitido:

```text
manual
reglamento
procedimiento
política
formulario
anexo
instructivo
capacitación
acta
información_general
norma
guía
otro
```

Temas permitidos inicialmente:

```text
SST
COPASST
Comité de Convivencia Laboral
Reglamento interno de trabajo
Política de seguridad
Prevención de alcohol y drogas
Seguridad vial
Pausas activas
Auditoría
Mejora
Planificación
Verificación
Organización
ARL
Formularios
Capacitaciones
```

Clasificación de sección preparada para etapas posteriores:

```text
definición
objetivo
alcance
responsabilidad
procedimiento
requisito
prohibición
plazo
formulario
anexo
evidencia
política
excepción
referencia_normativa
información_general
```

#### Estrategia de clasificación

1. [ ] Reglas basadas en ruta y nombre del archivo.
2. [ ] Patrones de encabezados y contenido.
3. [ ] Clasificación asistida por LLM para casos ambiguos.
4. [ ] Registro de `classification_confidence`.
5. [ ] Envío a `needs_review` cuando la confianza esté por debajo del umbral configurado.

La clasificación asistida por LLM no deberá bloquear el procesamiento base. Si el servicio no está disponible, el documento podrá conservarse como `otro` o `needs_review`, según las reglas configuradas.

---

### 5.5 `schemas/` — Contratos de archivos de salida

Los esquemas deberán definirse antes de implementar los lectores y mantenerse versionados. Se recomienda usar modelos Pydantic y generar JSON Schema para validación automática.

Todas las métricas de confianza o calidad utilizarán valores entre `0.0` y `1.0`. Cuando una métrica no aplique, se utilizará `null`, no un valor artificial.

#### Esquema de `*.pages.json`

```json
{
  "schema_version": "1.0",
  "document_id": "doc_001",
  "page_count": 2,
  "pages": [
    {
      "page_number": 1,
      "text_raw": "Texto extraído sin normalizar",
      "text_normalized": "Texto normalizado",
      "extraction_method": "pdf_digital",
      "ocr_confidence": null,
      "has_handwriting_warning": false,
      "warnings": []
    }
  ]
}
```

Campos obligatorios por página:

```text
page_number: integer >= 1
text_raw: string
text_normalized: string
extraction_method: markdown | pdf_digital | ocr
ocr_confidence: number entre 0 y 1 | null
has_handwriting_warning: boolean
warnings: list[string]
```

#### Esquema de `*.ocr.json`

```json
{
  "schema_version": "1.0",
  "document_id": "doc_001",
  "engine": "tesseract",
  "engine_version": "5.x",
  "language": "spa",
  "overall_confidence": 0.87,
  "pages": [
    {
      "page_number": 1,
      "confidence": 0.86,
      "word_count": 342,
      "low_confidence_word_count": 21,
      "deskew_applied": true,
      "rotation_detected_degrees": 0,
      "contains_handwriting": false,
      "warnings": []
    }
  ]
}
```

Campos obligatorios:

```text
engine
engine_version
language
overall_confidence
pages[].page_number
pages[].confidence
pages[].word_count
pages[].low_confidence_word_count
pages[].deskew_applied
pages[].rotation_detected_degrees
pages[].contains_handwriting
pages[].warnings
```

#### Esquema de `*.tables.json`

```json
{
  "schema_version": "1.0",
  "document_id": "doc_001",
  "table_count": 1,
  "tables": [
    {
      "table_id": "doc_001_table_001",
      "page_number": 3,
      "caption": "Distribución de responsabilidades",
      "headers": ["Rol", "Responsabilidad"],
      "rows": [
        ["Empleador", "Asignar recursos"],
        ["COPASST", "Realizar seguimiento"]
      ],
      "markdown_representation": "| Rol | Responsabilidad |\n|---|---|\n| Empleador | Asignar recursos |",
      "quality": 0.91,
      "warnings": []
    }
  ]
}
```

Campos obligatorios por tabla:

```text
table_id
page_number
caption: string | null
headers: list[string]
rows: list[list[string]]
markdown_representation: string
quality: number entre 0 y 1
warnings: list[string]
```

#### Reglas de versionado

- Todo archivo auxiliar deberá incluir `schema_version`.
- Un cambio incompatible incrementará la versión mayor.
- Un campo nuevo opcional incrementará la versión menor.
- Los consumidores posteriores deberán validar la versión antes de leer el archivo.

---

### 5.6 `manifests/` — Metadatos, manifiestos y revisión manual

#### Salida mínima por documento

```text
nombre_documento.md
nombre_documento.metadata.json
```

#### Salida condicional

```text
nombre_documento.pages.json
nombre_documento.ocr.json
nombre_documento.tables.json
```

#### Metadatos del documento: `*.metadata.json`

```text
schema_version
document_id
document_name
source_path
normalized_path
document_type
topic
subtopic
version
publication_date
effective_date
page_count
language
extraction_method
ocr_engine
ocr_confidence
contains_handwriting
contains_tables
content_hash
corpus_version
pipeline_version
processing_status
warnings
processed_at
```

Valores permitidos para `processing_status`:

```text
pending
processed
failed
needs_review
skipped
```

#### Front-matter del Markdown normalizado

```markdown
---
document_id: doc_001
document_type: reglamento
topic: copasst
source_file: reglamento_copasst.pdf
extraction_method: ocr
ocr_engine: tesseract
page_count: 18
corpus_version: 1
pipeline_version: 1.0.0
---

# Reglamento del COPASST

<!-- page: 1 -->
## Objetivo
Contenido de la primera página.
```

#### Manifiesto global

En `data/docs_normalized/_manifests/`:

```text
inventory.json
run_<timestamp>.json
run_<timestamp>_details.log
validation_<timestamp>.json
errors.json
needs_review.json
```

#### `needs_review.json`

Deberá incluir, como mínimo:

```json
{
  "schema_version": "1.0",
  "generated_at": "2026-07-16T18:00:00-05:00",
  "documents": [
    {
      "document_id": "doc_001",
      "source_path": "data/docs_raw/copasst/formulario.pdf",
      "reasons": ["low_ocr_confidence", "possible_handwriting"],
      "stage": "ocr",
      "recommended_action": "Revisar páginas 2 y 3",
      "review_status": "pending"
    }
  ]
}
```

Razones normalizadas sugeridas:

```text
unsupported_format
corrupt_file
password_protected
low_ocr_confidence
possible_handwriting
complex_table
missing_title
ambiguous_classification
page_count_mismatch
schema_validation_failed
hash_mismatch
partial_extraction
```

#### Carpeta de revisión

Cuando sea útil, crear:

```text
data/docs_normalized/_review_queue/<document_id>/
```

Esta carpeta podrá contener:

- Una copia temporal o vista previa del archivo problemático.
- Capturas de páginas dudosas.
- Salidas parciales.
- Un archivo `review_case.json` con diagnóstico.

**El archivo original nunca deberá moverse ni eliminarse de `docs_raw`.** La carpeta de revisión es una copia de trabajo y no la fuente oficial.

---

### 5.7 `logging/` — Logs detallados por ejecución

Cada ejecución deberá generar:

```text
data/docs_normalized/_manifests/run_<timestamp>_details.log
```

Se recomienda un formato JSON Lines: un objeto JSON por línea. Esto permite lectura humana, búsqueda y procesamiento automático.

#### Campos mínimos por evento

```text
timestamp
run_id
document_id
source_path
stage
event
status
duration_ms
message
warning_code
exception_type
exception_trace
```

#### Etapas registrables

```text
inventory
format_detection
reading
ocr
normalization
classification
output_generation
manifest_update
validation
cleanup
```

#### Ejemplo de evento

```json
{"timestamp":"2026-07-16T18:10:15-05:00","run_id":"run_20260716_181000","document_id":"doc_001","source_path":"data/docs_raw/copasst/reglamento.pdf","stage":"ocr","event":"page_processed","status":"warning","duration_ms":842,"message":"Confianza OCR baja en página 4","warning_code":"LOW_OCR_CONFIDENCE","exception_type":null,"exception_trace":null}
```

#### Reglas

- Registrar inicio y fin de cada documento.
- Registrar duración total y duración por etapa.
- Registrar advertencias sin convertirlas necesariamente en errores.
- Registrar la traza completa de excepciones en fallos.
- No incluir contenido documental completo ni datos sensibles innecesarios en los logs.
- Asociar todos los eventos con `run_id` y `document_id`.
- Permitir configurar nivel de log y retención.

---

### 5.8 `validation/` — Validación post-procesamiento

Crear:

```text
scripts/ingestion/validate_normalized.py
```

El script deberá ejecutarse al final de cada corrida y también de forma independiente.

#### Validaciones obligatorias

- [ ] Todo `.md` tiene un `.metadata.json` asociado.
- [ ] Todo `.metadata.json` referencia un `.md` existente cuando el estado es `processed`.
- [ ] Los `document_id` son únicos en inventario, metadatos y manifiestos.
- [ ] No existen `.pages.json`, `.ocr.json` o `.tables.json` huérfanos.
- [ ] Todo archivo auxiliar pertenece al mismo `document_id` de su metadata.
- [ ] Los hashes de los archivos fuente coinciden con `inventory.json`.
- [ ] Los archivos JSON cumplen su esquema y versión.
- [ ] `page_count` coincide entre metadata, pages y OCR cuando aplique.
- [ ] Un documento con estado `failed` aparece en `errors.json`.
- [ ] Un documento con estado `needs_review` aparece en `needs_review.json`.
- [ ] No existe un documento simultáneamente como `processed` y `failed` en la misma ejecución.
- [ ] Todos los archivos inventariados tienen un estado final o justificadamente `pending`.

#### Salida de validación

```text
data/docs_normalized/_manifests/validation_<timestamp>.json
```

Ejemplo:

```json
{
  "schema_version": "1.0",
  "run_id": "run_20260716_181000",
  "status": "failed",
  "documents_checked": 120,
  "errors": 2,
  "warnings": 5,
  "checks": [
    {
      "check": "unique_document_ids",
      "status": "passed",
      "details": []
    },
    {
      "check": "orphan_files",
      "status": "failed",
      "details": ["copasst/documento_x.pages.json"]
    }
  ]
}
```

#### Comportamiento de salida

- Retornar código `0` cuando no existan errores críticos.
- Retornar código distinto de `0` cuando falle una validación crítica.
- Las advertencias no deberán impedir necesariamente la publicación de la salida, pero sí quedar registradas.
- La corrida se considerará completa únicamente después de ejecutar esta validación.

---

### 5.9 Pruebas automatizadas

Las pruebas unitarias deberán comenzar en el Sprint 1.2, no dejarse para el cierre de la fase.

#### Fixtures mínimas

1. Un Markdown válido con título, lista y tabla.
2. Un PDF digital simple de una página.
3. Un PDF digital con varias páginas.
4. Un PDF escaneado de una página.
5. Un archivo corrupto o no soportado.
6. Casos esperados en JSON y Markdown para comparación.

#### Pruebas mínimas

- [ ] El lector Markdown conserva estructura y genera el contrato esperado.
- [ ] El lector PDF digital conserva páginas y texto.
- [ ] El lector escaneado invoca OCR y genera métricas.
- [ ] Los normalizadores preservan fechas, códigos, cifras y porcentajes.
- [ ] Los esquemas rechazan archivos incompletos o inválidos.
- [ ] El inventario detecta duplicados y cambios por hash.
- [ ] La segunda ejecución es idempotente.
- [ ] Un fallo documental no detiene el lote completo.
- [ ] La validación detecta archivos huérfanos y IDs duplicados.
- [ ] Los documentos dudosos se registran en `needs_review.json`.

#### Estrategia

- Utilizar `pytest`.
- Mockear OCRmyPDF y Tesseract en pruebas unitarias rápidas.
- Mantener al menos una prueba de integración real de OCR, marcada como lenta.
- Ejecutar las pruebas rápidas en cada cambio del módulo.
- Ejecutar integración y validación completa antes de cerrar la fase.

---

## 6. Estructura de carpetas de esta fase

```text
data/
├── docs_raw/
│   ├── convivencia_laboral/
│   ├── copasst/
│   └── general_sst/
│
└── docs_normalized/
    ├── convivencia_laboral/
    ├── copasst/
    ├── general_sst/
    ├── _review_queue/
    │   └── <document_id>/
    └── _manifests/
        ├── inventory.json
        ├── run_<timestamp>.json
        ├── run_<timestamp>_details.log
        ├── validation_<timestamp>.json
        ├── errors.json
        └── needs_review.json

app/back/src/ingestion/
├── inventory/
├── readers/
├── ocr/
├── normalization/
├── classification/
├── schemas/
├── manifests/
├── logging/
└── validation/

app/back/tests/ingestion/
├── fixtures/
├── test_inventory.py
├── test_readers.py
├── test_normalization.py
├── test_schemas.py
├── test_validation.py
└── test_pipeline_integration.py

scripts/ingestion/
├── run_inventory.py
├── run_pipeline.py
└── validate_normalized.py

docs/ingestion/
├── exploratory_analysis.md
└── README.md
```

---

## 7. Requisitos técnicos de la fase

- Python, integrado con el backend FastAPI definido en la arquitectura general.
- OCRmyPDF.
- Tesseract OCR con `tesseract-ocr-spa`.
- Librería PDF con soporte de posición, fuentes y bloques.
- PostgreSQL para persistir el inventario.
- Pydantic o JSON Schema para contratos de salida.
- `pytest` para pruebas unitarias e integración.
- Logging estructurado en JSON Lines.
- Manejo de idempotencia mediante `content_hash`.
- Configuración centralizada de umbrales de OCR, clasificación y detección de formato.
- Aislamiento de errores por documento.
- Directorio temporal configurable para procesamiento OCR.

---

## 8. Plan de trabajo por sprints

### Sprint 1.0 — Análisis exploratorio del corpus

- Revisar manualmente una muestra de cada carpeta.
- Identificar PDFs corruptos, tablas complejas, formularios, escaneos torcidos y archivos sin extensión.
- Estimar proporción de PDF digital frente a PDF escaneado.
- Documentar patrones y riesgos.
- Definir las primeras fixtures de prueba.
- Ajustar estimaciones y umbrales iniciales.

**Entregable:** `docs/ingestion/exploratory_analysis.md`.

### Sprint 1.1 — Inventario, contratos y esqueleto

- Crear estructura de módulos.
- Definir modelos Pydantic y esquemas JSON.
- Escanear recursivamente `docs_raw`.
- Calcular hash, tamaño, MIME y categoría inferida.
- Crear tabla o archivo de inventario inicial.
- Implementar `run_inventory.py`.
- Definir identificadores y estados de procesamiento.

**Criterio de salida:** todos los archivos están inventariados y los esquemas están versionados antes de construir lectores.

### Sprint 1.2 — Lectores base y primeras pruebas unitarias

- Implementar lector Markdown.
- Implementar lector PDF digital.
- Extraer contenido por página.
- Detectar títulos, listas y tablas básicas.
- Eliminar encabezados y pies repetidos.
- Generar Markdown con marcadores de página.
- Generar `.pages.json` y `.tables.json` cuando aplique.
- Crear pruebas unitarias con Markdown válido y PDF digital simple.

**Criterio de salida:** los lectores producen resultados conformes a esquema y las pruebas base pasan.

### Sprint 1.3 — OCR y manejo de documentos problemáticos

- Integrar OCRmyPDF y Tesseract en español.
- Implementar rotación y deskew configurables.
- Registrar confianza por página.
- Detectar escritura manual o baja legibilidad mediante heurísticas.
- Generar `.ocr.json`.
- Implementar `needs_review.json` y `_review_queue/`.
- Crear prueba unitaria mockeada y una prueba de integración con escaneado de una página.

**Criterio de salida:** un escaneado simple se procesa de extremo a extremo y los casos dudosos quedan visibles para revisión.

### Sprint 1.4 — Normalización y preservación de información

- Implementar transformaciones permitidas.
- Conservar `text_raw` y `text_normalized`.
- Garantizar preservación de fechas, cifras, códigos, nombres y porcentajes.
- Crear pruebas de regresión para datos sensibles.
- Validar salida contra los esquemas.

**Criterio de salida:** las transformaciones son auditables y no alteran información crítica.

### Sprint 1.5 — Clasificación documental

- Implementar reglas por ruta y nombre.
- Implementar patrones por encabezado.
- Añadir clasificación asistida por LLM para ambigüedades.
- Registrar confianza de clasificación.
- Enviar casos de baja confianza a revisión.
- Añadir pruebas para reglas y umbrales.

**Criterio de salida:** todos los documentos tienen clasificación o una razón explícita de revisión.

### Sprint 1.6 — Manifiestos, logs y validación post-procesamiento

- Generar `.metadata.json` completo.
- Generar manifiesto global por corrida.
- Implementar `run_<timestamp>_details.log`.
- Registrar tiempos y advertencias por documento y etapa.
- Implementar `validate_normalized.py`.
- Generar `validation_<timestamp>.json`.
- Crear pruebas de IDs duplicados, archivos huérfanos y hashes inconsistentes.

**Criterio de salida:** una corrida puede auditarse y sus inconsistencias se detectan automáticamente.

### Sprint 1.7 — Integración end-to-end y cierre

- Ejecutar el pipeline completo sobre el corpus real.
- Verificar idempotencia con una segunda corrida sin cambios.
- Reprocesar únicamente documentos modificados.
- Revisar errores y documentos en `needs_review`.
- Medir cobertura, tiempos y causas de fallo.
- Ejecutar pruebas unitarias, integración y validación final.
- Documentar ejecución incremental y reprocesamiento selectivo.

**Criterio de salida:** `docs_normalized` queda completo, consistente, validado y trazable.

---

## 9. Entregables de la Fase 1

1. Informe de análisis exploratorio del corpus.
2. Código funcional de `app/back/src/ingestion/`.
3. Esquemas versionados de `.metadata.json`, `.pages.json`, `.ocr.json` y `.tables.json`.
4. Script de inventario: `scripts/ingestion/run_inventory.py`.
5. Pipeline ejecutable: `scripts/ingestion/run_pipeline.py`.
6. Validador independiente: `scripts/ingestion/validate_normalized.py`.
7. `data/docs_normalized/` poblado a partir del corpus actual.
8. Manifiestos por corrida, logs detallados, errores y cola de revisión.
9. Suite de pruebas unitarias e integración básica.
10. Reporte de cobertura con:

```text
porcentaje procesado
porcentaje omitido por hash sin cambios
porcentaje en revisión
porcentaje fallido
tiempo total
tiempo promedio por documento
documentos procesados por método
principales causas de advertencia o fallo
resultado de validación final
```

11. README del pipeline con instrucciones para:

- Ejecutar una corrida completa.
- Ejecutar una corrida incremental.
- Reprocesar un documento.
- Consultar logs.
- Revisar `needs_review`.
- Ejecutar validación.
- Ejecutar pruebas.

---

## 10. Definition of Done de la fase

La Fase 1 se considerará terminada únicamente cuando:

- [ ] El análisis exploratorio esté documentado.
- [ ] Todos los archivos de `docs_raw` estén inventariados.
- [ ] Los formatos soportados se procesen con lectores aislados.
- [ ] Los archivos auxiliares cumplan esquemas versionados.
- [ ] Cada documento tenga un estado final trazable.
- [ ] Los fallos no detengan el lote completo.
- [ ] Existan logs detallados por ejecución y documento.
- [ ] Los documentos dudosos estén en `needs_review.json`.
- [ ] La validación post-procesamiento no reporte errores críticos.
- [ ] La segunda corrida sin cambios demuestre idempotencia.
- [ ] Las pruebas automatizadas pasen.
- [ ] El equipo pueda identificar por qué falló un documento sin volver a ejecutar todo el corpus.

---

## 11. Fuera de alcance

Se retoma en fases posteriores:

- Parent-child chunking y overlap.
- Interfaz de proveedores de embeddings.
- Recuperación híbrida lexical y vectorial.
- Grafo y reranking.
- Contextualización y normalización de consultas.
- Clasificación de consultas.
- System prompt.
- Generación y verificación de respuestas.
- Redis, caché y FAQ.
- Frontend.