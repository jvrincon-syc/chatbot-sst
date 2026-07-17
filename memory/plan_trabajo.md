# Plan consolidado de arquitectura para chatbot-sst

## 1. Objetivo del sistema

El chatbot de Seguridad y Salud en el Trabajo de SYC deberá responder consultas utilizando exclusivamente la información contenida en los documentos corporativos procesados.

El sistema deberá:

* Responder únicamente con evidencia recuperada del corpus.
* No completar información con conocimiento general del modelo.
* Indicar documento, sección y página cuando estén disponibles.
* Comprender preguntas de seguimiento.
* Reconocer cuándo no cuenta con información suficiente.
* Abstenerse cuando la evidencia sea inexistente, insuficiente, contradictoria o de baja confiabilidad.
* Relacionar información distribuida entre varios documentos cuando sea necesario.
* Permitir comparar distintos proveedores de embeddings.
* Conservar trazabilidad desde cada respuesta hasta el documento original.

---

# 2. Principio fundamental de respuesta

El chatbot operará con una política de tipo **fail-closed**.

Esto significa que, si no existe evidencia documental suficiente, el sistema no intentará responder por aproximación.

## Política de abstención

El chatbot deberá responder con una estructura como:

> No encontré información suficiente en los documentos disponibles para responder esta pregunta con certeza.

Opcionalmente podrá agregar:

> Puedes reformular la pregunta o consultar directamente con el área de Seguridad y Salud en el Trabajo.

El sistema se abstendrá cuando ocurra cualquiera de estas condiciones:

* No se recuperaron fragmentos relevantes.
* Los fragmentos tienen baja puntuación de recuperación.
* El reranker no encuentra evidencia suficientemente relacionada.
* Las fuentes encontradas no respaldan completamente la respuesta.
* El OCR tiene una confianza insuficiente para datos críticos.
* Existen contradicciones entre documentos y no puede determinarse cuál está vigente.
* La pregunta solicita información externa al corpus.
* El usuario pregunta por opiniones, recomendaciones legales o conocimiento general no documentado.

## Manejo de contradicciones

Cuando dos documentos presenten información diferente, el chatbot no debe elegir arbitrariamente una versión.

Debe indicar:

> Se encontró información diferente en los documentos consultados.

Y presentar ambas versiones con sus respectivas fuentes:

* Documento A, sección y página.
* Documento B, sección y página.

---

# 3. Arquitectura general

```text
┌─────────────────────────────┐
│ Next.js / React             │
│ Chat, historial y fuentes   │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│ FastAPI                     │
├─────────────────────────────┤
│ 1. Contextualización        │
│ 2. Normalización            │
│ 3. Clasificación consulta   │
│ 4. FAQ                      │
│ 5. Prefiltrado metadatos    │
│ 6. Recuperación híbrida     │
│ 7. Grafo auxiliar           │
│ 8. Reranking                │
│ 9. Expansión parent-child   │
│ 10. Generación              │
│ 11. Verificación            │
│ 12. Política abstención     │
└────────┬───────────┬────────┘
         │           │
         ▼           ▼
┌────────────────┐  ┌────────────────┐
│ PostgreSQL     │  │ Redis          │
│ + pgvector     │  │ Caché          │
│ + Full-Text    │  │ Sesiones       │
│ + grafo ligero │  │ FAQ counters   │
└────────────────┘  └────────────────┘
```

El sistema utilizará:

* PostgreSQL como fuente principal de verdad.
* Pgvector para recuperación semántica.
* PostgreSQL Full-Text Search para búsqueda lexical.
* Tablas relacionales en PostgreSQL para el grafo ligero.
* Redis para caché, sesiones temporales y métricas de preguntas frecuentes.
* FastAPI como backend.
* Next.js como frontend.
* Docker Compose para el MVP.
* Arquitectura compatible con Kubernetes en una evolución posterior.

---

# 4. Pipeline para llenar `docs_normalized`

Actualmente `docs_raw` contiene archivos Markdown, PDF digitales y PDF escaneados.

El objetivo del pipeline será convertir todos los documentos a una representación Markdown normalizada dentro de `data/docs_normalized`.

## Flujo general

```text
docs_raw
   │
   ▼
Inventario del archivo
   │
   ▼
Detección de formato
   │
   ├── Markdown
   ├── PDF digital
   └── PDF escaneado
   │
   ▼
Extracción de contenido
   │
   ▼
Normalización estructural
   │
   ▼
Clasificación documental
   │
   ▼
Generación de Markdown normalizado
   │
   ▼
Metadatos y manifiesto
   │
   ▼
docs_normalized
```

## 4.1 Inventario inicial

Por cada documento se registrará:

* Identificador único.
* Ruta de origen.
* Nombre del archivo.
* Extensión.
* Hash del archivo.
* Tamaño.
* Fecha de incorporación.
* Categoría inferida desde la ruta.
* Versión documental, cuando exista.
* Número de páginas.
* Estado de procesamiento.
* Versión del pipeline.
* Versión del corpus.

## 4.2 Procesamiento de Markdown

Los archivos Markdown existentes deberán:

* Conservar encabezados.
* Conservar listas.
* Conservar tablas.
* Conservar referencias.
* Normalizar espacios y saltos de línea.
* Eliminar encabezados repetidos.
* Validar que tengan una estructura mínima.
* Copiarse o transformarse hacia `docs_normalized`.

## 4.3 Procesamiento de PDF digital

Para cada PDF con texto digital:

1. Detectar que contiene una capa de texto.
2. Extraer el contenido página por página.
3. Conservar el número de página.
4. Detectar títulos y subtítulos.
5. Conservar listas.
6. Reconstruir tablas cuando sea posible.
7. Eliminar encabezados y pies repetidos.
8. Corregir palabras divididas entre líneas.
9. Convertir el resultado a Markdown.
10. Guardarlo en `docs_normalized`.

## 4.4 Procesamiento de PDF escaneado

Para PDF sin capa de texto:

1. Conservar el archivo original en `docs_raw`.
2. Procesar el PDF con OCRmyPDF.
3. Utilizar Tesseract configurado en español.
4. Generar una copia con capa de texto.
5. Extraer el contenido página por página.
6. Registrar confianza OCR.
7. Identificar páginas con escritura manual.
8. Marcar fragmentos dudosos.
9. Normalizar el resultado.
10. Convertirlo a Markdown.
11. Guardar el Markdown en `docs_normalized`.

## 4.5 Estructura de salida

La estructura de `docs_normalized` debería reflejar la de `docs_raw`.

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
    └── _manifests/
```

Por cada documento normalizado deberá existir, como mínimo:

```text
nombre_documento.md
nombre_documento.metadata.json
```

Cuando sea necesario:

```text
nombre_documento.pages.json
nombre_documento.ocr.json
nombre_documento.tables.json
```

## 4.6 Formato del Markdown normalizado

El Markdown debe conservar información de procedencia.

Ejemplo conceptual:

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
---

# Reglamento del COPASST

<!-- page: 1 -->

## Objetivo

Contenido de la primera página.

<!-- page: 2 -->

## Integración del comité

Contenido de la segunda página.
```

Los marcadores de página permiten conservar la trazabilidad incluso después de convertir el PDF a Markdown.

---

# 5. Capa de normalización documental

La normalización deberá producir dos representaciones:

* Texto original extraído.
* Texto normalizado para recuperación.

## Transformaciones permitidas

* Corrección de espacios duplicados.
* Unificación Unicode.
* Eliminación de caracteres invisibles.
* Reconstrucción de palabras partidas.
* Eliminación de encabezados repetidos.
* Eliminación de pies de página repetidos.
* Normalización de saltos de línea.
* Identificación de títulos.
* Conversión de listas.
* Conversión de tablas a Markdown.
* Normalización controlada de siglas.

## Transformaciones no permitidas

El pipeline no debe modificar automáticamente:

* Nombres propios.
* Fechas.
* Porcentajes.
* Números de identificación.
* Códigos de formularios.
* Artículos.
* Numerales.
* Plazos.
* Valores de tablas.

El contenido original siempre debe conservarse para auditoría.

---

# 6. Clasificación de textos y documentos

Todos los documentos y fragmentos deberán clasificarse para permitir prefiltrado.

## Tipos documentales iniciales

* Manual.
* Reglamento.
* Procedimiento.
* Política.
* Formulario.
* Anexo.
* Instructivo.
* Capacitación.
* Acta.
* Información general.
* Norma.
* Guía.
* Otro.

## Temas iniciales

* Seguridad y Salud en el Trabajo.
* COPASST.
* Comité de Convivencia Laboral.
* Reglamento interno de trabajo.
* Política de seguridad.
* Prevención de alcohol y drogas.
* Seguridad vial.
* Pausas activas.
* Auditoría.
* Mejora.
* Planificación.
* Verificación.
* Organización.
* ARL.
* Formularios.
* Capacitaciones.

## Clasificación de secciones

Además del documento completo, cada parent chunk podrá clasificarse como:

* Definición.
* Objetivo.
* Alcance.
* Responsabilidad.
* Procedimiento.
* Requisito.
* Prohibición.
* Plazo.
* Formulario.
* Anexo.
* Evidencia.
* Política.
* Excepción.
* Referencia normativa.
* Información general.

La clasificación podrá realizarse mediante:

1. Reglas basadas en rutas y títulos.
2. Patrones de encabezados.
3. Clasificación asistida por LLM.
4. Revisión manual de casos ambiguos.

---

# 7. Metadatos para prefiltrado

Los metadatos serán fundamentales para evitar búsquedas sobre todo el corpus cuando la consulta ya indique el área, tipo de documento o categoría.

## Metadatos del documento

```text
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
processing_status
```

## Metadatos del parent chunk

```text
parent_chunk_id
document_id
section_title
section_path
section_type
topic
subtopic
document_type
page_start
page_end
text_raw
text_normalized
token_count
contains_table
contains_form
contains_handwriting
ocr_confidence
classification_confidence
```

## Metadatos del child chunk

```text
child_chunk_id
parent_chunk_id
document_id
chunk_index
section_title
section_path
section_type
topic
subtopic
document_type
page_start
page_end
text_raw
text_normalized
token_start
token_end
token_count
overlap_previous
overlap_next
contains_table
contains_form
contains_handwriting
ocr_confidence
embedding_profile
corpus_version
content_hash
```

## Prefiltros posibles

El sistema podrá aplicar filtros como:

```text
topic = COPASST
document_type = reglamento
section_type = responsabilidad
page_start >= 1
ocr_confidence >= umbral
contains_handwriting = false
corpus_version = activa
```

Ejemplo:

> ¿Qué responsabilidades tiene el COPASST?

El sistema puede prefiltrar:

```text
topic = COPASST
section_type IN responsabilidad, función, obligación
```

Posteriormente ejecutará búsqueda lexical y vectorial únicamente sobre esos candidatos.

---

# 8. Parent-child chunking con overlap

## Parent chunks

Representarán unidades semánticas completas:

* Sección.
* Artículo.
* Numeral.
* Procedimiento.
* Política.
* Tabla.
* Bloque de formulario.
* Lista de responsabilidades.

Tamaño orientativo:

```text
800 a 1.500 tokens
```

La estructura documental tendrá prioridad sobre el tamaño.

## Child chunks

Los child chunks se utilizarán para la búsqueda.

Tamaño orientativo:

```text
250 a 450 tokens
```

Overlap:

```text
50 a 100 tokens
```

El overlap solo se realizará entre children pertenecientes al mismo parent.

```text
Parent A
├── Child A1
├── Child A2 con overlap de A1
├── Child A3 con overlap de A2
└── Child A4 con overlap de A3
```

No debe existir overlap entre secciones diferentes.

## Recuperación parent-child

1. Se recuperan child chunks.
2. Se fusionan resultados lexicales y vectoriales.
3. Se incorporan candidatos del grafo cuando sea necesario.
4. Se ejecuta reranking.
5. Se identifican los parent chunks asociados.
6. Se expande el contexto.
7. Se elimina contenido duplicado por overlap.
8. Se construye el paquete final de evidencia.

---

# 9. Interfaz abstracta de embeddings

La lógica RAG no dependerá directamente de BGE, Voyage o Cohere.

```text
EmbeddingProvider
├── BGEEmbeddingProvider
├── VoyageEmbeddingProvider
└── CohereEmbeddingProvider
```

La interfaz conceptual deberá soportar:

```text
embed_documents
embed_queries
get_model_name
get_provider_name
get_dimension
get_distance_metric
supports_sparse
supports_multimodal
```

Cada proveedor deberá tener su propia configuración.

```text
provider
model
dimension
distance_metric
normalization
batch_size
corpus_version
chunking_version
active
```

Los vectores de distintos modelos no deben mezclarse en una misma colección lógica.

Durante las pruebas se mantendrán perfiles independientes:

* BGE-M3.
* Voyage-4.
* Cohere Embed v4.

El benchmark comparará:

* Recall@5.
* Recall@10.
* MRR.
* Latencia.
* Costo.
* Exactitud en español.
* Desempeño en términos normativos.
* Desempeño en preguntas multidocumento.

---

# 10. Capa de contextualización conversacional

El chatbot deberá comprender preguntas de seguimiento.

Ejemplo:

```text
Usuario:
¿Cuáles son las funciones del COPASST?

Usuario:
¿Y cuánto dura su periodo?
```

La segunda pregunta debe convertirse en:

> ¿Cuánto dura el periodo de los integrantes del COPASST?

## Responsabilidades de la contextualización

* Resolver pronombres.
* Resolver referencias como “ese comité”.
* Identificar el tema activo.
* Identificar el documento activo.
* Recuperar entidades mencionadas anteriormente.
* Crear una consulta autónoma.
* No agregar hechos.
* No utilizar el historial como evidencia documental.

## Datos de entrada

* Pregunta actual.
* Últimos mensajes relevantes.
* Entidades activas.
* Tema activo.
* Documentos citados anteriormente.

## Datos de salida

```text
original_question
standalone_question
active_entities
active_topic
active_document
context_confidence
```

Si la contextualización no es clara, el chatbot podrá pedir una aclaración antes de recuperar documentos.

---

# 11. Capa de normalización de consultas

Después de contextualizar, la pregunta se normalizará.

## Funciones

* Corregir errores tipográficos moderados.
* Normalizar mayúsculas.
* Expandir siglas.
* Resolver alias.
* Detectar nombres de comités.
* Detectar tipos documentales.
* Detectar referencias a formularios.
* Detectar intención.
* Identificar filtros posibles.
* Identificar si la pregunta es directa o relacional.

## Glosario controlado

Ejemplos:

```text
copast → COPASST
comité paritario → COPASST
sst → Seguridad y Salud en el Trabajo
comité laboral → Comité de Convivencia Laboral
```

La normalización no debe alterar el significado de la consulta.

## Salida de normalización

```text
standalone_question
normalized_question
detected_entities
detected_topics
detected_document_types
detected_section_types
lexical_terms
semantic_query
graph_terms
```

---

# 12. Clasificación de la consulta

La consulta deberá clasificarse antes de seleccionar los recuperadores.

Clases iniciales:

```text
DIRECT
DEFINITION
PROCEDURAL
RELATIONAL
MULTI_DOCUMENT
COMPARATIVE
FORM_OR_ANNEX
FOLLOW_UP
UNSUPPORTED
```

## Ejemplos

### Directa

> ¿Qué significa COPASST?

Recuperadores:

* FAQ.
* Lexical.
* Vectorial.

### Procedimental

> ¿Cuáles son los pasos para presentar una queja?

Recuperadores:

* Lexical.
* Vectorial.
* Metadatos de tipo procedimiento.
* Parent-child.

### Relacional

> ¿Cómo se relacionan las inspecciones del COPASST con los planes de mejora?

Recuperadores:

* Lexical.
* Vectorial.
* Grafo.
* Parent-child.

### Multidocumento

> ¿Qué responsabilidades del empleador aparecen en manuales y reglamentos?

Recuperadores:

* Prefiltros.
* Lexical.
* Vectorial.
* Grafo opcional.
* Agrupación por documento.

### No soportada

> ¿Qué recomienda la legislación internacional?

El sistema deberá abstenerse porque la pregunta solicita conocimiento externo al corpus.

---

# 13. RAG híbrido principal

El mecanismo principal será:

* Búsqueda vectorial con pgvector.
* Búsqueda lexical con PostgreSQL Full-Text Search.
* Prefiltrado por metadatos.
* Fusión de candidatos.
* Reranking.
* Expansión parent-child.

## Flujo

```text
Consulta normalizada
        │
        ▼
Prefiltrado por metadatos
        │
        ├── VectorRetriever
        ├── LexicalRetriever
        ├── FAQRetriever
        └── GraphRetriever opcional
        │
        ▼
Fusión de resultados
        │
        ▼
Deduplicación
        │
        ▼
Reranking
        │
        ▼
Expansión child → parent
        │
        ▼
Paquete de evidencia
```

---

# 14. Grafo ligero en PostgreSQL

El grafo será un mecanismo auxiliar y no el núcleo obligatorio del RAG.

## Cuándo se utilizará

* Preguntas con múltiples entidades.
* Preguntas que relacionen varios temas.
* Preguntas multidocumento.
* Preguntas comparativas.
* Dependencias entre procesos.
* Referencias a anexos y formularios.
* Recuperación inicial débil.
* Consultas que requieran uno o dos saltos.

## Entidades

```text
Comité
Área
Rol
Procedimiento
Actividad
Documento
Formulario
Anexo
Política
Riesgo
Responsabilidad
Obligación
Plazo
Norma
```

## Relaciones

```text
REGULA
REFERENCIA
REQUIERE
UTILIZA
GENERA
PARTICIPA_EN
TIENE_RESPONSABLE
APLICA_A
PERTENECE_A
FORMA_PARTE_DE
TIENE_PLAZO
DEBE_REALIZAR
AMPLIA
REEMPLAZA
CONTRADICE
SE_RELACIONA_CON
```

## Evidencia obligatoria

Toda relación deberá enlazarse con:

```text
document_id
parent_chunk_id
child_chunk_id
page_start
page_end
section_title
supporting_text
confidence
review_status
```

El generador nunca deberá responder solamente con una relación del grafo. Deberá recuperar los chunks originales que respaldan esa relación.

---

# 15. Reranking

Después de fusionar resultados se ejecutará un reranker.

Ejemplo inicial:

```text
Top 20 vectoriales
+
Top 20 lexicales
+
Top 10 grafo
+
Top FAQ, cuando aplique
        │
        ▼
Deduplicación
        │
        ▼
Reranking
        │
        ▼
Top 5 a 8 evidencias
```

El reranker deberá evaluar la relación entre:

* Pregunta completa.
* Fragmento.
* Contexto del parent.
* Metadatos.
* Calidad OCR.

---

# 16. Paquete de evidencia

Antes de invocar el LLM generador se construirá un paquete de evidencia.

Cada evidencia incluirá:

```text
evidence_id
document_name
document_type
section_title
section_path
page_start
page_end
child_text
parent_context
retrieval_source
retrieval_score
reranker_score
ocr_confidence
contains_handwriting
```

El paquete deberá:

* Eliminar duplicados por overlap.
* Agrupar evidencias del mismo documento.
* Conservar páginas.
* Identificar contradicciones.
* Limitar el contexto enviado al LLM.
* Priorizar fuentes con mayor confiabilidad.

---

# 17. System prompt

El system prompt será una parte versionada de la arquitectura.

No deberá quedar escrito directamente dentro de un controller.

Podrá almacenarse en:

```text
memory/prompts/system/
```

Ejemplo conceptual:

```text
Eres el asistente documental de Seguridad y Salud en el Trabajo de
Sistemas y Computadores S.A.

Debes responder exclusivamente con base en las evidencias documentales
proporcionadas en el contexto.

Reglas obligatorias:

1. No utilices conocimiento general, conocimiento previo ni fuentes externas.
2. No inventes, completes ni supongas información.
3. Cada afirmación factual debe estar respaldada por una fuente.
4. Conserva exactamente fechas, cifras, porcentajes, nombres y códigos.
5. Indica documento, sección y página cuando estén disponibles.
6. Si la evidencia es insuficiente, responde que no cuentas con información
   suficiente.
7. Si existen contradicciones, presenta cada versión y sus fuentes.
8. Si una fuente proviene de OCR de baja confianza, adviértelo.
9. No presentes relaciones del grafo como hechos si no tienen evidencia textual.
10. El historial conversacional sirve para entender la pregunta, pero no es una
    fuente documental.
```

## Versionado

Cada respuesta deberá registrar:

```text
system_prompt_version
generation_prompt_version
verification_prompt_version
```

Esto permitirá reproducir resultados y comparar configuraciones.

---

# 18. Generación de respuesta

El generador recibirá:

* System prompt.
* Pregunta original.
* Pregunta autónoma.
* Evidencias.
* Reglas de citación.
* Formato esperado.

Formato sugerido:

```text
Respuesta directa.

Detalles adicionales, si son necesarios.

Fuentes:
- Documento, sección, página.
- Documento, sección, página.
```

Cuando una respuesta combine varios documentos, cada afirmación deberá asociarse con su fuente correspondiente.

---

# 19. Verificación de respuesta

La verificación será una etapa separada de la generación.

## Paso 1: separación de afirmaciones

La respuesta se divide en afirmaciones verificables.

## Paso 2: comparación contra evidencia

Cada afirmación se clasifica como:

```text
SUPPORTED
PARTIALLY_SUPPORTED
UNSUPPORTED
CONTRADICTED
LOW_OCR_CONFIDENCE
```

## Paso 3: decisión

* Si todas están respaldadas, se entrega la respuesta.
* Si hay afirmaciones parcialmente respaldadas, se eliminan o corrigen.
* Si hay afirmaciones no respaldadas, se regenera una vez.
* Si la regeneración falla, el chatbot se abstiene.
* Si la cita es incorrecta, la respuesta no se publica.
* Si el dato depende de OCR dudoso, se incluye advertencia.

---

# 20. Redis

Redis se utilizará desde el MVP para:

* Caché de respuestas verificadas.
* Caché de embeddings de preguntas.
* Contexto conversacional temporal.
* Rate limiting.
* Conteo de consultas frecuentes.
* Caché de expansiones del grafo.
* Locks de procesos de ingestión.
* Idempotencia de trabajos.

PostgreSQL seguirá siendo la fuente oficial de:

* FAQ.
* Documentos.
* Chunks.
* Grafo.
* Historial permanente.
* Feedback.
* Configuración activa.

## Clave de caché

```text
normalized_question
context_hash
corpus_version
embedding_profile
retrieval_version
graph_version
reranker_version
system_prompt_version
generator_model
```

Una respuesta solo podrá cachearse después de ser verificada.

---

# 21. FAQ

El FAQ será una capa de recuperación adicional.

## Flujo

```text
Pregunta
   │
   ▼
Normalización
   │
   ▼
Búsqueda FAQ
   │
   ├── Coincidencia confiable
   │      └── Respuesta con citas
   │
   └── Sin coincidencia
          └── RAG completo
```

Las preguntas repetidas se registrarán en Redis.

Cuando superen un umbral se crearán como candidatas.

```text
faq_candidates
```

Antes de convertirse en respuestas oficiales deberán pasar por revisión.

Cada FAQ deberá conservar:

```text
canonical_question
answer
citations
source_documents
corpus_version
approval_status
approved_by
approved_at
```

---

# 22. Estructura de carpetas ajustada

```text
chatbot-sst/
├── app/
│   ├── back/
│   │   ├── src/
│   │   │   ├── api/
│   │   │   │   ├── controllers/
│   │   │   │   └── routes/
│   │   │   │
│   │   │   ├── core/
│   │   │   │   ├── config/
│   │   │   │   ├── logging/
│   │   │   │   └── exceptions/
│   │   │   │
│   │   │   ├── ingestion/
│   │   │   │   ├── inventory/
│   │   │   │   ├── readers/
│   │   │   │   ├── ocr/
│   │   │   │   ├── normalization/
│   │   │   │   ├── classification/
│   │   │   │   ├── chunking/
│   │   │   │   └── manifests/
│   │   │   │
│   │   │   ├── rag/
│   │   │   │   ├── contextualization/
│   │   │   │   ├── query_normalization/
│   │   │   │   ├── query_classification/
│   │   │   │   ├── prefiltering/
│   │   │   │   ├── retrieval/
│   │   │   │   ├── graph_retrieval/
│   │   │   │   ├── reranking/
│   │   │   │   ├── evidence/
│   │   │   │   ├── generation/
│   │   │   │   ├── verification/
│   │   │   │   └── abstention/
│   │   │   │
│   │   │   ├── providers/
│   │   │   │   ├── embeddings/
│   │   │   │   ├── llm/
│   │   │   │   ├── rerankers/
│   │   │   │   └── ocr/
│   │   │   │
│   │   │   ├── graph/
│   │   │   │   ├── entities/
│   │   │   │   ├── relations/
│   │   │   │   └── extraction/
│   │   │   │
│   │   │   ├── infrastructure/
│   │   │   │   ├── postgres/
│   │   │   │   ├── pgvector/
│   │   │   │   ├── redis/
│   │   │   │   └── repositories/
│   │   │   │
│   │   │   └── evaluation/
│   │   │
│   │   └── tests/
│   │
│   └── front/
│       └── src/
│           ├── app/
│           ├── components/
│           │   ├── chat/
│           │   ├── citations/
│           │   ├── document-viewer/
│           │   └── feedback/
│           ├── services/
│           ├── hooks/
│           ├── styles/
│           └── types/
│
├── data/
│   ├── docs_raw/
│   ├── docs_normalized/
│   ├── FAQ/
│   │   ├── approved/
│   │   └── candidates/
│   └── evaluation/
│
├── memory/
│   ├── prompts/
│   │   ├── system/
│   │   ├── generation/
│   │   └── verification/
│   ├── glossaries/
│   └── conversation-policies/
│
├── migrations/
├── scripts/
│   ├── ingestion/
│   ├── evaluation/
│   └── maintenance/
├── docker/
├── docs/
└── docker-compose.yml
```

---

# 23. Flujo completo de consulta

```text
1. Recibir pregunta
2. Recuperar historial conversacional
3. Contextualizar la pregunta
4. Convertirla en consulta autónoma
5. Normalizar términos y siglas
6. Detectar entidades y temas
7. Clasificar la consulta
8. Detectar si es externa al corpus
9. Consultar FAQ aprobado
10. Consultar caché verificada
11. Construir prefiltrado por metadatos
12. Ejecutar búsqueda lexical
13. Ejecutar búsqueda vectorial
14. Activar grafo si la consulta lo requiere
15. Fusionar candidatos
16. Eliminar duplicados
17. Ejecutar reranking
18. Expandir child chunks hacia parents
19. Eliminar duplicación por overlap
20. Construir paquete de evidencia
21. Evaluar suficiencia de evidencia
22. Aplicar política de abstención si es necesario
23. Generar respuesta con system prompt
24. Verificar afirmaciones
25. Verificar citas
26. Regenerar una vez si falla
27. Abstenerse si continúa el fallo
28. Cachear respuesta validada
29. Registrar métricas
30. Mostrar respuesta y fuentes
```

---

# 24. Orden de implementación

## Etapa 1 — Ingesta y extracción

* Inventario.
* Markdown.
* PDF digital.
* OCRmyPDF.
* Tesseract español.
* Extracción por página.
* Registro de confianza OCR.
* Manifiestos.

## Etapa 2 — Normalización

* Raw y normalizado.
* Conversión a Markdown.
* Persistencia en `docs_normalized`.
* Títulos.
* Listas.
* Tablas.
* Páginas.
* Clasificación documental.

## Etapa 3 — Chunking y metadatos

* Parent chunks.
* Child chunks.
* Overlap.
* Metadatos de prefiltrado.
* Trazabilidad.
* Citas.
* Tratamiento de formularios.

## Etapa 4 — RAG base

* Interfaz de embeddings.
* BGE-M3.
* Voyage-4.
* Cohere Embed v4.
* Pgvector.
* Full-Text Search.
* Prefiltrado.
* Fusión.
* Reranking.

## Etapa 5 — Conversación y políticas

* Capa de contextualización.
* Normalización de consultas.
* Clasificación.
* System prompt.
* Política de abstención.
* Respuestas con citas.

## Etapa 6 — Verificación

* Evaluación de suficiencia.
* Separación de afirmaciones.
* Verificación contra fuentes.
* Regeneración.
* Fail-closed.

## Etapa 7 — Grafo ligero

* Entidades.
* Alias.
* Relaciones.
* Evidencias.
* GraphRetriever.
* Router de consultas relacionales.
* Expansión máxima de dos saltos.

## Etapa 8 — Redis y FAQ

* Caché.
* Sesiones.
* FAQ aprobado.
* Candidatos FAQ.
* Contadores.
* Invalidación por versión.

## Etapa 9 — Frontend

* Chat.
* Historial.
* Fuentes.
* Páginas.
* Visor documental.
* Alertas OCR.
* Feedback.

## Etapa 10 — Evaluación y entrega

* Dataset de preguntas.
* Preguntas directas.
* Preguntas de seguimiento.
* Preguntas multidocumento.
* Preguntas relacionales.
* Preguntas sin respuesta.
* Precisión de citas.
* Evaluación del OCR.
* Latencia y concurrencia.
* Docker Compose.

---

# 25. Definición final de la arquitectura

El chatbot SST utilizará un RAG híbrido con búsqueda vectorial, búsqueda lexical, prefiltrado por metadatos, parent-child retrieval, child overlap y reranking.

Contará con una capa de contextualización para convertir preguntas de seguimiento en consultas autónomas, una capa de normalización para resolver siglas y términos del dominio, y una capa de clasificación para seleccionar los mecanismos de recuperación adecuados.

El sistema utilizará un grafo ligero almacenado en PostgreSQL únicamente como apoyo para consultas relacionales o multidocumento. Toda relación deberá estar respaldada por fragmentos documentales verificables.

El chatbot estará gobernado por un system prompt versionado y una política estricta de abstención. Cuando no exista evidencia suficiente, deberá indicar explícitamente que no cuenta con la información necesaria.

Los documentos originales permanecerán en `docs_raw`, mientras que todos los Markdown normalizados generados desde archivos Markdown, PDF digitales y PDF escaneados se almacenarán en `docs_normalized`.

Redis se utilizará como capa de caché, sesiones y detección de candidatos FAQ, pero PostgreSQL seguirá siendo la fuente oficial de verdad.
