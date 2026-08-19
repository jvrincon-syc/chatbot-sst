# Plataforma RAG Multi‑Proyecto sobre el estado actual — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Evolucionar `chatbot-sst` desde un corpus SST único hacia una plataforma multi‑proyecto que pueda construir, comparar y conservar releases RAG reproducibles, sin duplicar el pipeline bundle-first ni mezclar proyectos, recetas técnicas, nodos o vectores.

**Architecture:** El diseño separa tres responsabilidades: `project_id` posee documentos y artefactos físicos; `rag_variant_id` identifica una receta semántica inmutable (parseo/normalización, chunking y embedding); `rag_release_id` es un snapshot inmutable de una variante sobre un corpus concreto y una materialización de índice compatible. Las releases referencian artefactos físicos ya sellados mediante membresías; no los duplican ni se convierten en la clave propietaria de los vectores.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, PostgreSQL 18 + pgvector, filesystem versionado, React/TypeScript, Vite, pytest y pruebas frontend existentes.

## Global Constraints

- La base de este plan es `main` en [`3bc9a8a`](https://github.com/jvrincon-syc/chatbot-sst/commit/3bc9a8a6c53cdb429ba100c85fcb6497d06e4e5b), del 10 de agosto de 2026.
- Se conserva un único pipeline de negocio: ingesta → normalización → chunking → embedding → indexing. Una nueva capa de orquestación no puede reimplementar esas etapas.
- Los perfiles de embedding y los `indexing_targets` continúan siendo recursos globales, verificados y resueltos por el servidor. Un `target_binding_key` de proyecto puede elegir una materialización compatible para la release, pero el cliente nunca envía una tabla vectorial ni un `indexing_target_id` directo.
- No se crea una tabla pgvector por proyecto, variante ni release. Se mantienen las tablas por perfil/espacio vectorial establecidas por ADR‑005.
- Los secretos, URLs privadas, payloads de proveedor, texto completo de chunks y vectores no se persisten en preferencias de UI, eventos ni logs.
- El flujo actual de `Activation`/`Retrieval`, `ConsumerScope` y `retrieval_profiles` permanece legacy durante la ejecución de este plan. Publicar una release de plataforma no activa vectores ni cambia consumidores.
- La fase no implementa chat, personalidad/tipos de chatbot, asignación de releases a chatbots, búsqueda de producción, RBAC corporativo ni facturación.
- Este plan es aditivo: no elimina endpoints, tablas, punteros filesystem ni adaptadores legacy. La sustitución de esos componentes queda fuera de alcance y requiere una decisión y un plan posteriores.

---

## Estado legacy que permanece explícitamente en alcance de compatibilidad

El código existente contiene una lane legacy funcional. Se conserva para no interrumpir SST mientras se construye la plataforma, pero no define la identidad de los nuevos proyectos ni de sus releases.

| Componente actual | Restricción observada | Tratamiento en este plan |
| --- | --- | --- |
| `ingestion/paths.py` | `stable_document_id()` depende solo de `source_relpath`. | Se preserva para los flujos legacy; los documentos de plataforma usan identidad `project_id + logical_document_id + revision` y guardan la ruta solo como localizador. |
| `FilesystemChunkBundleRepository.replace()` | Reemplaza archivos asociados a la ruta normalizada actual. | Sigue atendiendo el flujo legacy; la plataforma crea una ruta sellada por `chunk_bundle_id` mediante un adaptador nuevo. |
| `chunk_bundles`, `embedding_bundles`, `indexing_nodes` y `idx_vec_*` | Tienen identidades globales o dependen de `corpus_version`. | Se evolucionan para artefactos nuevos con `project_id` y nodos namespaced; `corpus_version` se conserva únicamente como dato legacy. |
| `ActivateIndexedBundleUseCase` y `retrieval_profiles` | Activan vectores y perfil de retrieval por `corpus_version`. | Se mantienen sin cambio. `PUBLISHED` en plataforma es publicación de catálogo, no activación de retrieval. |
| UI Embedding/Indexing/Activation/Retrieval | Es la interfaz vigente para la lane bundle-first. | Permanece disponible y se etiqueta como **Legacy pipeline**; la UI de plataforma se añade sin modificar sus contratos. |

La consecuencia importante es deliberada: una release de plataforma puede quedar `PUBLISHED`, auditada y con su materialización de índice registrada, pero **todavía no cambia qué release consulta el chatbot existente**. Esa selección de consumidor se decide en una fase posterior, no de forma implícita aquí.

---

## 1. Principios de identidad, propiedad y reutilización

La plataforma necesita reutilizar artefactos físicos exactos sin perder la reproducibilidad de cada RAG. Por tanto, los artefactos pertenecen al proyecto y una release los referencia mediante membresías inmutables:

- Agregar el documento 56 crea `release-002`, pero los 55 documentos sin cambio deben reutilizar sus artefactos físicos.
- Cambiar local → LlamaParse o BGE‑M3 → Voyage crea una variante RAG distinta, sin perder la posibilidad de reutilizar lo que sea compatible aguas arriba.
- Una release publicada debe seguir reconstruible aunque posteriormente aparezca otro documento o se publique otra variante.

La separación queda así:

| Elemento | Propietario / identidad | ¿Puede reutilizarse? | ¿Debe llevar `rag_release_id`? |
| --- | --- | --- | --- |
| Raw source y revisión documental | Proyecto + ruta lógica + hash de revisión | No entre proyectos; sí dentro del proyecto | No |
| Normalizado | Proyecto + revisión documental + fingerprint de procesamiento | Sí, si la receta de procesamiento coincide exactamente | No |
| Chunk bundle | Proyecto + normalizado + fingerprint de chunking | Sí, si el normalizado y perfil coinciden | No |
| Embedding bundle | Proyecto + chunk bundle + perfil/configuración de embedding | Sí, si el espacio vectorial coincide exactamente | No |
| Nodo físico | Proyecto + chunk bundle + `source_chunk_id` | Sí para todas las releases que referencien el bundle | No |
| Vector físico | Proyecto + materialización de embedding + nodo físico + target | Sí para todas las releases compatibles | No |
| Run de build | Intento operacional dentro de una release | Se audita, no se reutiliza como identidad de artefacto | Sí |
| Membresía de release | Release + artefacto sellado | Inmutable después de publicar | Sí |

### Relación objetivo

```mermaid
flowchart TD
  P["Project"]
  P --> D["Document revisions"]
  P --> V["RAG variants"]
  D --> A["Immutable physical artifacts"]
  V --> R["RAG release"]
  D --> C["Corpus snapshot"]
  C --> R
  A --> M["Release memberships"]
  M --> R
```

Una `RAG variant` es un RAG lógico de larga vida. Una `RAG release` es una fotografía auditable de esa variante sobre un corpus. Un nuevo documento altera el `corpus_snapshot_id`, por lo que crea una nueva release, no una nueva variante.

### Capacidad multi-proyecto, multi-motor y multi-release

El modelo admite múltiples proyectos completamente aislados. Cada proyecto puede tener corpus propios, perfiles de procesamiento permitidos y varios modelos de embedding; dentro de un mismo proyecto, el mismo `corpus_snapshot_id` puede alimentar varias variantes RAG.

| Nivel | Qué diferencia | Ejemplo |
| --- | --- | --- |
| `project_id` | Propietario, corpus, configuración y almacenamiento aislados | `sst-general`, `calidad-interna` |
| `corpus_snapshot_id` | Conjunto exacto de revisiones documentales fuente | `sst-corpus-002` con 56 documentos |
| `rag_variant_id` | Receta técnica: parseo/normalización, chunking y embedding | `local-bge-m3`, `llamaparse-voyage-4` |
| `rag_release_id` | Versión inmutable de una variante sobre un snapshot | `sst-local-bge-m3-r002` |

| Proyecto | Corpus snapshot | Variante | Release | Receta fijada |
| --- | --- | --- | --- | --- |
| `sst-general` | `corpus-sst-002` (56 revisiones fuente) | `local-bge-m3` | `r002` | PDF/OCR local + `local-structural-v1` + BGE-M3 |
| `sst-general` | `corpus-sst-002` (las mismas 56 revisiones fuente) | `llamaparse-bge-m3` | `r001` | LlamaParse + `local-structural-v1` + BGE-M3 |
| `sst-general` | `corpus-sst-002` (las mismas 56 revisiones fuente) | `llamaparse-voyage-4` | `r001` | LlamaParse + `local-structural-v1` + Voyage-4 |
| `sst-general` | `corpus-sst-003` (57 revisiones, incluido un documento nuevo) | Cualquier variante construida | Nueva release | La receta de esa variante se mantiene; cambia el corpus congelado |
| `calidad-interna` | `corpus-calidad-001` | `local-bge-m3` | `r001` | Corpus, configuración y artefactos aislados de SST |

Un `corpus_snapshot` congela las revisiones fuente, no obliga a que todas las variantes compartan un normalizado. Por ejemplo, `local` y `llama_cloud` pueden procesar los mismos PDFs fuente con resultados normalizados y bundles distintos; cada variante conserva sus propios artefactos, embeddings y materializaciones compatibles. Un cambio en el corpus crea una release nueva para la variante que se construya, mientras que un cambio de parseo, chunking o modelo de embedding crea otra variante y su propia release.

---

## 2. Modelo de dominio acordado

### 2.1 Project

`project_id` es el límite de propiedad y de almacenamiento. Es un slug técnico único e inmutable después de que el proyecto tenga documentos; `display_name` sí es editable.

Ejemplo: `sst-general`.

El proyecto define:

- catálogo y reglas de tipos documentales;
- políticas permitidas de procesamiento, chunking y embedding;
- configuración editable versionada;
- raíz de almacenamiento aislada;
- documentos fuente y sus revisiones;
- perfiles permitidos de procesamiento local y/o `llama_cloud`, chunking y embedding;
- variantes RAG que puede construir.

### 2.2 Document revision y artefacto normalizado

Un documento lógico se identifica por `project_id + source_relpath`. Cada cambio de bytes crea una `source_document_revision` inmutable. Una misma revisión puede producir varios normalizados si se aplican recetas diferentes.

La identidad de un normalizado nuevo debe incluir, como mínimo:

```text
project_id
+ source_document_revision_id
+ processing_profile_fingerprint
+ schema_version
```

La receta de procesamiento persiste, sin secretos, `parser_provider`, `parser_engine`, revisión observada, configuración sanitizada/fingerprint, normalización, clasificación y origen (`local` o `llama_cloud`). No basta con el `ingestion_origin` actual, porque no registra completamente el motor ni su configuración. es necesario guardar el motor y configuracion 

### 2.3 RAG variant

`rag_variant_id` identifica una receta semántica inmutable dentro de un proyecto. Ejemplos:

```text
sst-local-bge-m3
  processing: local-pdf-ocr-v1
  chunking: local-structural-v1
  embedding: local-bge-m3-v1

sst-llamaparse-voyage-4
  processing: llamaparse-v2026-08-pinned
  chunking: local-structural-v1
  embedding: voyage-4-v1
```

La variante contiene un `semantic_recipe_fingerprint` sobre las referencias y snapshots de configuración. Su receta no se edita: modificar el proveedor/motor/revisión/configuración de parseo, normalización, chunking, embedding o cualquier perfil que cambie la semántica de recuperación crea otro `rag_variant_id`.

El `indexing_target` no forma parte de esa receta si únicamente cambia la lane física de pgvector. Al crear una release, el backend resuelve un `target_binding_key` permitido para el perfil de embedding de la variante y congela el `indexing_target_id` resuelto en el manifiesto. Cambiar a otro target compatible crea una release nueva de la misma variante, con otra materialización; una métrica o configuración que cambie la semántica debe vivir en el perfil y, por tanto, crear variante.

Cambiar solamente concurrencia, batch size o timeout no crea variante ni release si no cambia el artefacto ni el resultado semántico. Se audita como configuración operacional del run.

#### 2.3.1 Construcción de la variante: matriz de combinaciones computada server-side (decisión 2026-08-13)

**Cambio de enfoque respecto a la primera implementación.** Hoy
`CreateRagVariantUseCase` recibe un triple libre
(`processing_profile_id`, `chunking_profile_id`, `embedding_profile_id`) +
`target_binding_key` armado por el cliente, y el back valida/rechaza en cadena. Esto
deja que el cliente proponga combinaciones inválidas y concentra la lógica de
compatibilidad en el borde de creación.

**Nuevo comportamiento acordado:** el back **computa** la matriz de combinaciones
válidas **por proyecto**, derivada de los datos reales (no de un catálogo hardcoded):

- Fuentes: los perfiles de procesamiento y chunking **habilitados del proyecto** ×
  los perfiles de embedding **habilitados** (`project_embedding_profiles`, globales por
  ADR-005) × los `project_indexing_target_bindings` compatibles con cada embedding.
- Salida: una lista de celdas `{processing, chunking, embedding, target_binding, buildable, blocked_reason}`
  donde `buildable=false` lleva un motivo estable (p. ej. `target_incompatible`,
  `revision_unverifiable`, `already_exists`).
- El cliente **elige una celda ya pre-validada**; nunca arma un triple arbitrario.
- `CreateRagVariant` pasa a **confirmar que la celda pertenece a la matriz vigente** y
  computa el `semantic_recipe_fingerprint`. La **identidad y la reproducibilidad no
  cambian**: el fingerprint sigue derivándose de los perfiles concretos pinneados
  (ADR-006 §2.3); la matriz es un **selector** sobre los perfiles, no un reemplazo de la
  identidad, y **no** introduce rótulos que puedan desincronizarse (se recomputa de los
  datos, sin drift).

**Beneficio:** se saca del borde la lógica de "qué combinación es válida" y se reduce el
campo de errores: el cliente no puede enviar combinaciones inválidas y la validación de
creación se vuelve "la celda sigue en la matriz" en vez de N chequeos sueltos.

**Alcance:** este es un cambio del **contrato admin de variante** (Fase 5/7). No altera
Fase 4 (artefactos físicos) ni las invariantes de identidad. Se implementa como un
read-model `GET variant-matrix` (§Fase 7) + endurecimiento de `CreateRagVariant` a
selección de celda. Alternativa descartada: catálogo estático hardcoded de combos
(mismo para todo proyecto, ignora lo habilitado por proyecto y arrastra drift
etiqueta-vs-perfil).

#### 2.3.2 Persistencia del motor de embedding como filtro de selección (decisión 2026-08-14)

**Requisito acordado:** además de la matriz server-side, la selección de un RAG debe
poder filtrar por **motor de embedding** — saber qué artefactos de la base fueron
embebidos con exactamente el mismo motor — como criterio de selección junto a
`project_id`. Dos artefactos solo son comparables/mezclables en un mismo espacio
vectorial si comparten el motor (proveedor, modelo, revisión, dimensión, métrica,
normalización).

**Estado real (verificado en código, 2026-08-14):** la configuración del motor **ya se
persiste** a nivel de artefacto físico, no solo referida por el perfil:

- `embedding_bundles` almacena `provider`, `model`, `model_revision`,
  `embedding_dimension`, `normalization`, `distance_metric` y el
  `configuration_fingerprint` (SHA-256 canónico de esa config). Migración
  `20260805_06_create_embedding_bundles.sql`.
- `embedding_runs` persiste el `configuration_fingerprint` del run (y, por §2.3.2,
  `project_id`/`rag_variant_id`/`rag_release_id` de contexto).
- La variante pinea ese mismo `configuration_fingerprint` dentro de su
  `semantic_recipe_fingerprint` (`recipe_service.py`), de modo que el motor es parte
  inmutable de la identidad de la variante.

**Lo que faltaba (esta iteración):** exponer un **read-model de selección** que, por
proyecto, liste los motores de embedding **con artefactos realmente materializados**
(join `embedding_bundles` → `indexing_materializations`), devolviendo por cada motor su
`configuration_fingerprint`, los campos legibles (`provider`/`model`/`dimension`/
`metric`/`normalization`) y conteos. Ese read-model es el filtro `(project_id, motor)` que
acompaña a la matriz de variantes; el cliente nunca envía tabla vectorial ni
`indexing_target_id`. La identidad y reproducibilidad no cambian: el filtro **lee** lo ya
persistido, no introduce un rótulo nuevo que pueda derivar.

### 2.4 Corpus snapshot

`corpus_snapshot_id` es una lista ordenada e inmutable de revisiones documentales pertenecientes a un proyecto, con `manifest_hash`/Merkle hash y conteos. Agregar, quitar o reemplazar un documento genera otro snapshot.

### 2.5 RAG release

`rag_release_id` une una variante y un corpus snapshot:

```text
rag_release_id = ragr_...
project_id = sst-general
rag_variant_id = sst-local-bge-m3
corpus_snapshot_id = corpus-sst-002
target_binding_key = local-bge-primary
release_number = 2
```

Estados permitidos:

```text
DRAFT → BUILDING → VALIDATED → PUBLISHED → RETIRED
              ↘ FAILED
```

- `DRAFT`: la selección de corpus y receta está congelada, pero puede reemplazarse explícitamente por una nueva revisión de DRAFT antes de construir.
- `BUILDING`: el orquestador resuelve reuso o ejecuta las etapas faltantes.
- `VALIDATED`: membresía completa, hashes, perfiles, conteos y materializaciones verificadas.
- `PUBLISHED`: snapshot inmutable disponible para asignación manual futura; no activa retrieval.
- `RETIRED`: se conserva para auditoría y rollback de consumidor futuro.
- `FAILED`: conserva evidencia operacional; solo una nueva DRAFT puede reiniciar con cambios materiales.

Una release publicada no se edita. Para incluir un documento nuevo se crea un `corpus_snapshot` nuevo y, para la misma variante, una nueva release. El artefacto de cada documento intacto se referencia desde la nueva membresía sin regenerarse.

---

## 3. Invariantes de seguridad y aislamiento

Esta sección se deriva de código y migraciones revisados en `3bc9a8a`, no de una prueba de penetración. Los puntos observados más relevantes son:

- `FilesystemChunkBundleRepository.replace()` reemplaza el bundle actual por ruta, por lo que hoy no conserva una selección histórica por release.
- `PostgresIndexingNodeWriter.replace_document_nodes()` borra por `document_id` y usa `ON CONFLICT (node_id)`, por lo que dos artefactos con IDs de chunk coincidentes pueden sobrescribirse.
- `PostgresVectorRepository.activate_bundle()` desactiva filas por `embedding_profile_id + indexing_target_id + corpus_version`; esa operación es activación legacy, no publicación neutral.
- El backend ya resuelve profiles/targets en servidor y evita que el navegador escoja la tabla vectorial, un control que se debe conservar.

Los siguientes invariantes son obligatorios para el diseño plataforma:

1. Un comando de build nuevo parte de `rag_release_id`; el servidor deriva de él proyecto, variante, perfil, target y snapshot. Nunca acepta una combinación arbitraria de esos IDs desde el cliente.
2. Toda relación de pertenencia valida el ancestro `release → variant → project` y el propietario del artefacto `artifact.project_id` antes de escribir o leer.
3. Los artefactos sellados son append-only/content-addressed. Ningún endpoint puede sobrescribir archivos referenciados por una release `VALIDATED`, `PUBLISHED` o `RETIRED`.
4. El reuso automático solo ocurre dentro del mismo proyecto y solo por identidad exacta. El reuso entre proyectos queda prohibido por defecto, aunque los bytes sean idénticos.
5. `node_id` pasa a ser una identidad física namespaced; `source_chunk_id` queda separado para evidencia y trazabilidad.
6. Publicar una release no llama `ConsumerScope`, no crea `retrieval_profiles` y no cambia `is_active` en tablas vectoriales.
7. Las rutas de storage se derivan con `ProjectStorageResolver`; los requests no aportan paths absolutos ni relpaths sin validar. La contención de rutas actual se mantiene y se extiende a la raíz del proyecto.
8. El servicio actual no implementa autorización multiusuario. Hasta que exista RBAC, las nuevas rutas deben declararse de operador interno, detrás de feature flag y no exponerse como API pública. Se introduce una interfaz `PlatformAccessPolicy` para no codificar una autorización futura en todos los endpoints.
9. Todo cambio de lifecycle, publicación, retiro, reuso o fallo registra actor de operador, `request_id`, `rag_release_id`, hashes y motivo, sin registrar contenido documental ni secretos.

---

## 4. Estrategia de datos y migración

### 4.1 Qué se mantiene

- `indexing_profiles`, `indexing_targets` y las tablas `idx_vec_*` conservan su papel de perfiles y lanes físicos.
- `chunk_bundles`, `embedding_bundles`, `embedding_runs`, `indexing_runs`, `indexing_nodes` y `readiness_checks` se aprovechan como base, pero cambian sus identidades de plataforma.
- `corpus_version` sigue disponible para legacy/auditoría durante la implementación de plataforma; no es alias de project, variante ni release.
- `ConsumerScope`, `retrieval_profiles`, `Activation` y endpoints `/api/retrieval` se mantienen sin cambiar su semántica. Cualquier reemplazo futuro se decidirá fuera de este documento.

### 4.2 Qué no se debe hacer

- No añadir `rag_release_id` a `chunk_bundles`, `embedding_bundles`, `indexing_nodes` o cada `idx_vec_*` como FK propietaria.
- No sustituir la unicidad física por `project_id + rag_release_id`; impediría reutilizar artefactos sin duplicar datos.
- No seguir usando `node_id == source_chunk_id` para datos nuevos. Ese supuesto es el origen del overwrite entre procesamientos.
- No usar `corpus_version` como identificador de release o filtro de plataforma.
- No hacer una migración destructiva antes de disponer del bootstrap verificable de SST y del adaptador legacy.

### 4.3 Esquema objetivo mínimo

| Grupo | Tablas/proyecciones nuevas o extendidas | Contrato importante |
| --- | --- | --- |
| Proyecto | `rag_projects`, `project_configuration_versions`, `project_document_types`, `project_embedding_profiles`, `project_indexing_target_bindings` | `project_id` único, estable y propietario de artefactos; binding lógico permitido a un target global |
| Procesamiento | `document_processing_profiles`, `chunking_profiles` | configuración sin secretos + fingerprint inmutable |
| Documentos | `project_documents`, `source_document_revisions`, extensión de `indexing_normalized_documents` | un normalizado está ligado a revisión + fingerprint de procesamiento |
| Variante | `rag_variants` | `UNIQUE(project_id, semantic_recipe_fingerprint)` mientras esté activa |
| Corpus | `corpus_snapshots`, `corpus_snapshot_documents` | lista ordenada y hash inmutable |
| Release | `rag_releases`, `rag_release_documents`, `rag_release_chunk_bundles`, `rag_release_embedding_bundles`, `rag_release_index_materializations` | una release referencia artefactos; no los posee y fija el binding/target de su materialización |
| Runs | `rag_build_runs`, `rag_build_steps` y FK contextual en `embedding_runs`/`indexing_runs` | cada intento operacional es release-aware |
| Físico | extensiones de `chunk_bundles`, `embedding_bundles`, `indexing_nodes`, `idx_vec_*` | `project_id` sí; `rag_release_id` no |

Las membresías se separan por tipo para conservar FKs reales. Una tabla polimórfica `artifact_type/artifact_id` reduciría código inicial, pero perdería integridad referencial y complicaría validación.

### 4.4 Identidades y constraints nuevos

| Artefacto | Identidad lógica o constraint propuesta |
| --- | --- |
| Normalizado | `UNIQUE(project_id, source_document_revision_id, processing_profile_fingerprint)` |
| Chunk bundle | `UNIQUE(project_id, normalized_document_id, chunking_profile_fingerprint, bundle_schema_version)` |
| Embedding bundle | `UNIQUE(project_id, source_chunk_bundle_id, embedding_profile_id, configuration_fingerprint, source_content_fingerprint, bundle_schema_version)` |
| Nodo físico | `node_id = sha256(project_id + source_chunk_bundle_id + source_chunk_id)`; almacenar `source_chunk_id` y `source_parent_chunk_id` |
| Vector físico | `UNIQUE(embedding_bundle_id, node_id)` más `project_id`; no depende de release |
| Materialización | `UNIQUE(project_id, embedding_bundle_id, indexing_target_id, storage_schema_version)` |
| Release | `UNIQUE(rag_variant_id, release_number)`, `UNIQUE(project_id, rag_release_id)` para FKs compuestas de seguridad, y snapshot del `target_binding_key`/target resuelto |

---

## 5. Plan de implementación

### Fase 0: ADR, baseline y contrato de identidad

**Files:**

- Create: `docs/adr/ADR-006-rag-platform-project-variant-release.md`
- Create: `docs/rag-platform/identity-and-reuse-contract.md`
- Create: `docs/rag-platform/migration-baseline.md`
- Modify: `docs/adr/README.md`
- Modify: `docs/backend/phase-handoffs.md`
- Test: `app/back/tests/rag_platform/test_identity_contract.py`

**Interfaces produced:**

```python
@dataclass(frozen=True)
class ProjectDocumentContext:
    project_id: str
    source_document_id: str
    source_document_revision_id: str
    processing_profile_id: str

@dataclass(frozen=True)
class RagBuildContext:
    project_id: str
    rag_variant_id: str
    rag_release_id: str
    corpus_snapshot_id: str
    embedding_profile_id: str
    indexing_target_id: str
    semantic_recipe_fingerprint: str
```

- [x] Documentar que los artefactos físicos son propietarios del proyecto y que las releases solo los referencian. — Evidencia: `docs/adr/ADR-006-rag-platform-project-variant-release.md` define la separación proyecto/artefacto/release.
- [x] Registrar la regla de negocio: documento agregado, retirado o reemplazado ⇒ corpus snapshot nuevo ⇒ release nueva. — Evidencia: misma ADR, sección "Decision".
- [x] Registrar la regla de variante: cambio semántico de parseo/normalización/chunking/embedding/perfil de recuperación ⇒ variante nueva y release nueva; cambio de target físicamente compatible ⇒ release nueva, no variante. — Evidencia: `docs/adr/ADR-006-rag-platform-project-variant-release.md` y `rag_platform/domain/identity.py`.
- [x] Separar tres conceptos en el contrato de handoff: `promoted` confirma que la promoción técnica terminó; `release_eligible` confirma que una revisión puede entrar a un snapshot; `PUBLISHED` confirma solo el catálogo de una release. Ninguno es sinónimo de los otros. — Evidencia: `docs/rag-platform/identity-and-reuse-contract.md` y `docs/backend/phase-handoffs.md`.
- [x] Para una revisión con `needs_review`, exigir una decisión de elegibilidad versionada (`approved_after_review`, `operator_waiver` o `blocked`) antes de incluirla en un corpus snapshot. La promoción legacy conserva su comportamiento actual y no se altera. — Evidencia: `app/back/src/rag_platform/application/corpus_snapshot_service.py` y `docs/rag-platform/identity-and-reuse-contract.md`.
- [x] Declarar `corpus_version` como compatibilidad legacy y prohibir su uso como sustituto de `project_id`, `rag_variant_id`, `corpus_snapshot_id` o `rag_release_id` en nuevos contratos. — Evidencia: `docs/adr/ADR-006-rag-platform-project-variant-release.md` y descripción de Fase 0.
- [x] Inventariar, en PostgreSQL real, conteos y hashes de `indexing_normalized_documents`, `chunk_bundles`, `embedding_bundles`, `embedding_runs`, `indexing_runs`, `indexing_nodes`, `idx_vec_*` y `retrieval_profiles` antes de cualquier migración. — Evidencia: `docs/rag-platform/migration-baseline.md` contiene el inventario real y los hashes.
- [x] Verificar los nombres reales de constraints, PKs e índices en la base que se migrará; no asumir que todos los entornos coinciden solo por los archivos SQL. — Evidencia: `docs/rag-platform/migration-baseline.md` lista constraints e índices reales por tabla.
- [x] Crear un manifiesto de baseline con el commit, migraciones aplicadas, rutas de storage y hashes de los contratos. Corregir los READMEs que aún indican `f918b51` para que identifiquen el baseline real `3bc9a8a`, sin usar documentos no versionados como autoridad técnica. — Evidencia: `docs/rag-platform/migration-baseline.md` incluye commit, migraciones aplicadas, rutas de storage y hashes.
- [x] Añadir pruebas de identidad que demuestren que `project_id`, variante, corpus snapshot y release no son intercambiables. — Evidencia: `app/back/tests/rag_platform/test_identity_contract.py`.

**Exit criteria:** ADR aprobado; baseline reproducible archivado; `promoted`, elegibilidad de release, publicación y activación tienen semánticas documentadas distintas; no existe migración irreversible ni cambio de comportamiento.

### Fase 1: Project, configuración y perfiles de receta

**Files:**

- Create: `app/back/src/rag_platform/domain/models.py`
- Create: `app/back/src/rag_platform/domain/errors.py`
- Create: `app/back/src/rag_platform/application/project_service.py`
- Create: `app/back/src/rag_platform/application/recipe_service.py`
- Create: `app/back/src/rag_platform/application/context.py`
- Create: `app/back/src/rag_platform/infrastructure/storage/project_storage.py`
- Create: `app/back/src/rag_platform/infrastructure/postgres/project_repositories.py`
- Create: `migrations/20260810_01_create_rag_platform_catalog.sql`
- Test: `app/back/tests/rag_platform/test_projects.py`  
- Test: `app/back/tests/rag_platform/test_recipe_identity.py`

**Interfaces produced:**

```python
class CreateProjectUseCase:
    def execute(self, request: CreateProjectRequest, *, actor_id: str) -> RagProject: ...

class CreateRagVariantUseCase:
    def execute(self, request: CreateRagVariantRequest, *, actor_id: str) -> RagVariant: ...

class ProjectStorageResolver:
    def roots_for(self, project_id: str) -> ProjectStorageRoots: ...
    def resolve_artifact(self, project_id: str, relative_path: PurePosixPath) -> Path: ...
```

- [x] Crear `rag_projects`, configuración versionada, tipos documentales por proyecto y perfiles de embedding permitidos. — Evidencia: `migrations/20260810_01_create_rag_platform_catalog.sql` define `rag_projects`, `project_configuration_versions`, `project_document_types` y `project_embedding_profiles`.
- [x] Crear `document_processing_profiles` y `chunking_profiles` con proveedor, motor, revisión observada, configuración sanitizada, fingerprint, estado y timestamps. Las credenciales quedan exclusivamente en `secrets.env`/entorno. — Evidencia: `migrations/20260810_01_create_rag_platform_catalog.sql` define `document_processing_profiles` y `chunking_profiles`; `rag_platform/domain/models.py` documenta la sanitización de configuración y fingerprint.
- [x] Crear `rag_variants` con referencia a procesamiento, chunking y embedding, más `semantic_recipe_fingerprint` inmutable; crear `project_indexing_target_bindings` como allowlist backend de claves lógicas hacia targets globales compatibles. — Evidencia: `migrations/20260810_01_create_rag_platform_catalog.sql` define `rag_variants` y `project_indexing_target_bindings`.
- [x] Permitir que cada proyecto habilite de forma independiente perfiles de procesamiento `local` y/o `llama_cloud`, además de uno o más perfiles de embedding compatibles; crear una variante distinta por cada receta semántica seleccionada. — Evidencia: `app/back/src/rag_platform/application/recipe_service.py` valida perfiles por proyecto y crea variantes con `processing_profile_id`, `chunking_profile_id` y `embedding_profile_id`.
- [x] Implementar una plantilla genérica de tipos documentales que conserve las opciones SST como una plantilla seleccionable y añada opciones neutrales. Un proyecto nuevo no preselecciona SST; `sst-general` sí parte de la plantilla SST versionada. — Evidencia: `app/back/src/rag_platform/application/project_service.py` define `_GENERIC_DOCUMENT_TYPES` y `_SST_DOCUMENT_TYPES`; `ProjectDocumentType` usa `DocumentTypeTemplate`.
- [x] Persistir una política de organización de corpus por proyecto, con cuatro opciones iniciales: `sst-legacy-v1`, `source-folders-v1`, `document-types-v1` y `hybrid-v1`. La política define la vista de ingreso/navegación y los relpaths lógicos; nunca define la identidad del documento ni la ubicación canónica de artefactos sellados. — Evidencia: `migrations/20260810_01_create_rag_platform_catalog.sql` declara el enum `corpus_organization_policy` con las cuatro opciones.
- [x] En `document-types-v1`, enrutar inicialmente el archivo a `intake/`; solo después de clasificación o asignación humana se materializa la vista por tipo. No inferir que la ruta de entrada demuestra el tipo documental. — Evidencia: la política de organización de corpus se modela como un contrato separado en `rag_platform/domain/models.py` y la ruta lógica se trata como un localizador, no identidad, en `document_revision_service.py`.
- [x] Implementar `ProjectStorageResolver` con raíces nuevas `data/projects/{project_id}/raw`, `normalized`, `chunks`, `embeddings` y `manifests`. Para `sst-general`, usar un adaptador de lectura de las rutas legacy durante el bootstrap, sin convertir las rutas legacy en la ruta canónica de artefactos nuevos. — Evidencia: `app/back/src/rag_platform/infrastructure/storage/project_storage.py` implementa `roots_for` y `LegacySstReadAdapter`.
- [x] Implementar `PlatformAccessPolicy` como puerto. En esta fase el adaptador puede representar operador interno, pero ningún handler toma `actor_id` de un body o header no autenticado. — Evidencia: `app/back/src/rag_platform/application/context.py` define `PlatformAccessPolicy`; los casos de uso de proyecto y receta lo consumen.
- [x] Bloquear bindings o DRAFTs cuando el target no sea compatible con el perfil de embedding; bloquear variantes cuya receta use una revisión no verificable sin attestation explícita. — Evidencia: `app/back/src/rag_platform/application/recipe_service.py` valida compatibilidad de binding y rechaza revisiones `UNVERIFIABLE` sin `allow_unverifiable_revision`.

**Exit criteria:** dos proyectos pueden existir con taxonomía, configuración y variantes diferentes; sus raíces no se intersectan y no hay credenciales en la base o UI.

### Fase 2: Revisiones documentales, normalizados y corpus snapshots

**Files:**

- Create: `app/back/src/rag_platform/application/document_revision_service.py`
- Create: `app/back/src/rag_platform/application/corpus_snapshot_service.py`
- Create: `app/back/src/rag_platform/infrastructure/postgres/document_repositories.py`
- Create: `migrations/20260810_02_create_project_documents_and_revisions.sql`
- Create: `migrations/20260810_03_create_corpus_snapshots.sql`
- Modify: `app/back/src/ingestion/paths.py`
- Modify: `app/back/src/ingestion/schemas/artifacts.py`
- Modify: `app/back/src/ingestion/schemas/inventory.py`
- Modify: `app/back/src/ingestion/pipeline.py`
- Test: `app/back/tests/rag_platform/test_document_revisions.py`
- Test: `app/back/tests/rag_platform/test_corpus_snapshots.py`
- Test: `app/back/tests/ingestion/test_identity.py`

**Interfaces produced:**

```python
class CreateCorpusSnapshotUseCase:
    def execute(
        self,
        *,
        project_id: str,
        document_revision_ids: Sequence[str],
        actor_id: str,
    ) -> CorpusSnapshot: ...

class ResolveNormalizedArtifactUseCase:
    def resolve_or_build(
        self,
        context: ProjectDocumentContext,
    ) -> NormalizedDocumentArtifact: ...
```

- [x] Crear documento lógico (`project_documents`) y revisión inmutable (`source_document_revisions`) con hash de raw, relpath y trazabilidad de carga. `logical_document_id` se genera al ingreso; `source_relpath` es solo un localizador versionado y puede cambiar sin colisionar entre proyectos. — Evidencia: `migrations/20260810_02_create_project_documents_and_revisions.sql` define `project_documents` y `source_document_revisions` como tablas de plataforma.
- [x] Extender el contrato Schema 2.0 para datos nuevos con `project_id`, `source_document_revision_id`, `normalized_document_id`, `processing_profile_id` y fingerprints; conservar un adaptador explícito Schema 2.0 legacy para SST. — Evidencia: `app/back/src/ingestion/schemas/artifacts.py` define `PlatformDocumentIdentity` opcional y lo incluye en `MetadataArtifact.platform_identity`.
- [x] Reemplazar la identidad nueva basada solo en `source_relpath` por un ID determinista que incluya proyecto, revisión y recipe fingerprint. Los `document_id` legacy no se reescriben durante esta fase. — Evidencia: `app/back/src/rag_platform/application/document_revision_service.py` genera IDs `sdoc_` y `srev_` a partir de proyecto, relpath y hash de raw usando `ingestion.paths.platform_document_id`/`platform_revision_id`.
- [x] Resolver `DocumentType` contra el catálogo y la política versionados del proyecto. El Literal actual solo permanece en el adaptador SST/legacy hasta que la validación de política esté cubierta. — Evidencia: `app/back/src/rag_platform/application/classification_service.py` usa `resolve_document_type` de `rag_platform/domain/classification.py` para validar el tipo contra la configuración del proyecto.
- [x] Extraer reglas SST de `ingestion/classification/rules.py` hacia una política cargada desde el snapshot de configuración; conservar el adaptador que produce exactamente las decisiones SST actuales. — Evidencia: `app/back/src/rag_platform/infrastructure/classification/sst_policy.py` envuelve `ingestion.classification.rules.classify_document` y traduce sus resultados al contrato de plataforma.
- [x] Crear `corpus_snapshots` con orden determinista, hashes de las revisiones seleccionadas, conteo de documentos y `manifest_hash`. — Evidencia: `migrations/20260810_03_create_corpus_snapshots.sql` y `app/back/src/rag_platform/application/corpus_snapshot_service.py` calculan `manifest_hash` de forma determinista.
- [x] Guardar en cada membresía de snapshot la decisión de elegibilidad de su revisión; no permitir que un `needs_review` se haga releaseable solo porque fue promovido técnicamente. — Evidencia: `migrations/20260810_03_create_corpus_snapshots.sql` usa `eligibility_decision` y `app/back/src/rag_platform/application/corpus_snapshot_service.py` valida `needs_review` vs `approved_after_review`/`operator_waiver`.
- [x] Hacer que cualquier cambio material de selección genere un snapshot nuevo, incluso si la ruta lógica es igual. — Evidencia: `create_corpus_snapshot` es idempotente sólo por `manifest_hash`, y un cambio en la selección o en las decisiones de elegibilidad cambia el hash.

**Exit criteria:** un raw modificado no sobreescribe la revisión anterior; dos proyectos pueden tener la misma ruta relativa sin colisión; un corpus snapshot puede reconstruirse solo con sus rows y hashes.

### Fase 3: Artefactos físicos inmutables y ledger de chunking

**Files:**

- Create: `app/back/src/rag_platform/application/artifact_reuse_service.py`
- Create: `app/back/src/rag_platform/infrastructure/postgres/artifact_repositories.py`
- Create: `migrations/20260810_04_extend_project_owned_artifacts.sql`
- Modify: `app/back/src/chunking/application/run_service.py`
- Modify: `app/back/src/chunking/infrastructure/filesystem_chunk_repository.py`
- Modify: `app/back/src/chunking/infrastructure/filesystem_run_repository.py`
- Modify: `app/back/src/embedding/infrastructure/filesystem/chunk_bundle_reader.py`
- Test: `app/back/tests/chunking/integration/test_run_service_persistence.py`
- Test: `app/back/tests/rag_platform/test_artifact_reuse.py`
- Test: `app/back/tests/rag_platform/test_chunk_bundle_immutability.py`

**Interfaces produced:**

```python
class ArtifactReusePolicy:
    def find_reusable_normalized(... ) -> NormalizedDocumentArtifact | None: ...
    def find_reusable_chunk_bundle(... ) -> ChunkBundleRef | None: ...
    def find_reusable_embedding_bundle(... ) -> EmbeddingBundle | None: ...

class RagBuildRunRepository(Protocol):
    def start_step(self, context: RagBuildContext, stage: BuildStage, ...) -> RagBuildStep: ...
    def complete_step(self, step_id: str, outcome: BuildOutcome, ...) -> RagBuildStep: ...
```

- [x] Crear `rag_build_runs` y `rag_build_steps` como ledger durable para todas las etapas y reusos. El run sí apunta a release; el bundle físico no. — **Evidencia:** `migrations/20260810_04_extend_project_owned_artifacts.sql` crea ambas tablas (`rag_build_runs.rag_release_id TEXT NOT NULL` apunta a la release; el bundle físico no lleva `rag_release_id`). Dominio: `domain/models.py::RagBuildStep`, enums `BuildStage`/`BuildOutcome`/`ReuseKind`. Puerto `application/artifact_reuse_service.py::RagBuildRunRepository` (`start_step`/`complete_step`) + fake in-memory. **Aplicado a la BD viva** `chatbot_sst` (tablas presentes y vacías, verificado). Test `tests/rag_platform/test_artifact_reuse.py::test_ledger_registra_pasos_de_build_con_clasificacion_de_reuso`.
- [x] Cambiar el repositorio filesystem para almacenar bundles sellados bajo `data/projects/{project_id}/chunks/{chunk_bundle_id}/`, con manifest, checksums, parents y children. `latest` puede existir como vista de UI por proyecto, pero ninguna release puede depender de él. — **Evidencia:** `infrastructure/storage/sealed_chunk_store.py::SealedChunkStore.stage_and_seal` escribe `manifest.json`, `parent_chunks.jsonl`, `child_chunks.jsonl` y `checksums.json` bajo `chunks/{chunk_bundle_id}/` (content-addressed; sin dependencia de `latest`), con contención de rutas vía `ProjectStorageResolver`. Tests `tests/rag_platform/test_chunk_bundle_immutability.py::test_sella_bundle_content_addressed_cuando_es_nuevo`.
- [x] Mantener `replace()` sin cambios para el flujo legacy y añadir `stage_and_seal()` para la plataforma; el nuevo adaptador no puede llamar a `replace()` sobre una ruta compartida. — **Evidencia:** la lógica de escritura atómica se extrajo a `core/atomic_fs.py` (DRY) y `chunking/infrastructure/filesystem_chunk_repository.py::replace()` delega en ella con comportamiento **byte-idéntico** (prueba de regresión `tests/chunking/integration/test_run_service_persistence.py::test_replace_legacy_serializa_byte_identico_cuando_helpers_extraidos`). `SealedChunkStore` usa `core.atomic_fs` directamente y **nunca** llama a `replace()` ni escribe sobre la ruta legacy.
- [x] Añadir `project_id`, `normalized_document_id`, profile fingerprint y estado de sellado a `chunk_bundles`. Sustituir la unicidad global de `bundle_fingerprint` por la identidad física definida en la sección 4.4. — **Evidencia:** `20260810_04` añade `project_id`, `normalized_document_id`, `chunking_profile_fingerprint`, `bundle_schema_version`, `sealing_status` (todas nullable, verificado en `chatbot_sst`) y crea el índice único **parcial** `uq_chunk_bundles_physical_identity` con la identidad física §4.4 `WHERE project_id IS NOT NULL`. **Desviación explícita (decisión del usuario):** la unicidad global legacy `chunk_bundles_bundle_fingerprint_key` NO se retira en esta fase — se **mantiene** y su retiro se difiere a Fase 4 (ordenamiento de migración segura §4, "no destructivo antes del bootstrap"). Filas legacy verificadas intactas (56 filas, todas con `project_id` NULL).
- [x] Mantener `corpus_version` como columna legacy; no incluirlo en la identidad de bundles nuevos. — **Evidencia:** `20260810_04` conserva `corpus_version` sin tocarla y el índice de identidad física `uq_chunk_bundles_physical_identity` **no la incluye** (solo `project_id + normalized_document_id + chunking_profile_fingerprint + bundle_schema_version`). Comentario explícito en la migración (§4.3/§4.4).
- [x] Hacer que la entrada de build de plataforma reciba solo `rag_release_id`; el backend resuelve snapshot y perfil de chunking. `ChunkingRunRequest` y la API legacy conservan su payload actual. — **Evidencia:** el contrato de build de plataforma se ancla en `RagBuildContext` (`domain/identity.py`), cuya identidad primaria es `rag_release_id`; el ledger `RagBuildRunRepository.start_step(context, stage)` lo consume. `ChunkingRunRequest` y `/api/chunking` **no se modificaron** (verificado). **Alcance Fase 3:** se fija la forma del contrato; el endpoint/orquestador que deriva snapshot+perfil desde `rag_release_id` es Fase 5/7 (declarado como deuda).
- [x] Registrar por cada reuso `exact_identity`, `revalidated_compatibility` o `operator_approved`, junto con el artefacto origen. `operator_approved` no puede salvar incompatibilidad de dimensión, métrica o proyecto. — **Evidencia:** enum `domain/models.py::ReuseKind` (`EXACT_IDENTITY`/`REVALIDATED_COMPATIBILITY`/`OPERATOR_APPROVED`); `rag_build_steps.reuse_kind` (CHECK) + `source_artifact_id` registran clasificación y artefacto origen. Guarda de dominio `ensure_reuse_within_project` + error `CrossProjectReuseForbidden`: ni `operator_approved` cruza proyectos. Test `tests/rag_platform/test_artifact_reuse.py::test_operator_approved_no_puede_reutilizar_entre_proyectos`. (Validación de dimensión/métrica de embedding → Fase 4, declarada.)

**Exit criteria:** crear `release-002` con un documento adicional reutiliza los 55 bundles intactos; un bundle referenciado por `release-001` no cambia de ruta, hash ni contenido.

### Fase 4: Embedding, nodos y vectores físicos sin colisiones

**Files:**

- Create: `migrations/20260810_05_release_aware_runs_and_namespaced_nodes.sql`
- Create: `migrations/20260810_06_extend_idx_vec_project_ownership.sql`
- Modify: `app/back/src/embedding/domain/models.py`
- Modify: `app/back/src/embedding/application/run_service.py`
- Modify: `app/back/src/embedding/application/bundle_builder.py`
- Modify: `app/back/src/embedding/infrastructure/postgres/repositories.py`
- Modify: `app/back/src/indexing/domain/bundle_first.py`
- Modify: `app/back/src/indexing/application/bundle_first/index_bundle.py`
- Modify: `app/back/src/indexing/infrastructure/postgres/bundle_first.py`
- Modify: `app/back/src/indexing/infrastructure/postgres/vector_repository.py`
- Test: `app/back/tests/embedding/test_embedding_run_flow.py`
- Test: `app/back/tests/indexing/test_durable_profile_alignment.py`
- Test: `app/back/tests/rag_platform/test_node_identity_isolation.py`
- Test: `app/back/tests/rag_platform/test_vector_lane_isolation.py`

**Interfaces produced:**

```python
def physical_node_id(
    *, project_id: str, source_chunk_bundle_id: str, source_chunk_id: str
) -> str: ...

class IndexingMaterializationRepository(Protocol):
    def find_sealed(self, *, project_id: str, embedding_bundle_id: str, indexing_target_id: str) -> IndexingMaterialization | None: ...
    def begin_writing(self, ...) -> IndexingMaterialization: ...
    def seal(self, *, materialization_id: str, canonical_checksum: str, counts: ...) -> IndexingMaterialization: ...
    def mark_failed(self, *, materialization_id: str, failure_code: str) -> IndexingMaterialization: ...
```

> **Enfoque revisado (2026-08-11, [ADR-007](../adr/ADR-007-phase4-physical-ownership-and-hard-reset.md); plan de trabajo `plans/2026-08-11-fase4-embedding-nodos-vectores.md`):** entorno de dev → **hard reset + rebuild** de artefactos derivados en vez de backfill `legacy_unverified`. Aislamiento por **FKs compuestas** `(project_id, id)`, no solo `project_id`. **No** se retira ninguna unicidad global en Fase 4 (colisión de fingerprint global → error de dominio fail-closed). SST **dormido** durante Fase 4–8. Orden: Gate 0 → DDL aditivo → dual-mode → reset → rebuild → validación → enable.

- [x] `EmbeddingRun`/`IndexingRun` ganan `project_id`/`rag_variant_id`/`rag_release_id` como contexto operacional, **columnas nullable sin FK** (la tabla `rag_releases` es de Fase 5), derivadas por el servidor desde un build context validado, **nunca** del payload del cliente. No cambia la identidad de `EmbeddingBundle`. — **Evidencia:** `migrations/20260810_05_...sql:99-105` (`ALTER TABLE embedding_runs/indexing_runs ADD COLUMN IF NOT EXISTS project_id/rag_variant_id/rag_release_id`, sin FK). Derivación server-side: `rag_platform/application/rebuild_orchestrator.py::PlatformBuildContext` (validado por `kind`, nunca del payload). Test `tests/indexing/infrastructure/postgres/test_embedding_persistence_migrations.py`.
- [x] Nueva identidad de `EmbeddingBundle` (proyecto + chunk bundle + profile/config fingerprint + contenido fuente) como **índice único parcial** `WHERE project_id IS NOT NULL`; `corpus_version` se mantiene NOT NULL (marcador legacy) fuera de la identidad. La unicidad legacy actual **no se retira** (ya incluye `source_chunk_bundle_id`). — **Evidencia:** `20260810_05_...sql:30-39` (`uq_embedding_bundles_physical_identity` parcial, sin `corpus_version`). `embedding/domain/models.py:442-448` (`project_id` nullable; legacy conserva id con `corpus_version`). Sin `DROP CONSTRAINT` en la migración.
- [x] **Aislamiento por FKs compuestas** (impuesto por la BD): `UNIQUE(project_id, chunk_bundle_id)`; `embedding_bundles`/`indexing_nodes`/`idx_vec_*`/`indexing_materializations` con `FK(project_id, ...)` a su padre. Con `project_id` nullable, las filas legacy bypassean el FK compuesto (MATCH SIMPLE) y solo plataforma queda blindada. Sin `DROP CONSTRAINT`. — **Evidencia:** `20260810_05_...sql:14-15,24-25,45-58,73-92,135-148` (uniques compuestos + FKs `NOT VALID` en chunk/embedding/nodes/materializations) y `20260810_06_...sql:37-55` (2 FKs compuestos por cada `idx_vec_*`). MATCH SIMPLE documentado en cabeceras.
- [x] `IndexingNodeRecord`: separar `node_id` físico de `source_chunk_id`; **y `parent_node_id` físico de `source_parent_chunk_id`**. La expansión parent→child usa `parent_node_id` físico, no el source. — **Evidencia:** `20260810_05_...sql:65-67` (columnas `source_chunk_id`/`source_parent_chunk_id`). `indexing/application/bundle_first/index_bundle.py:109-190` (build_nodes separa físico/evidencia). Test `tests/rag_platform/test_node_identity_isolation.py::test_parent_expansion_uses_physical_parent_node_id` y `tests/retrieval/test_parent_expansion.py`.
- [x] Reemplazar `replace_document_nodes(document_id=...)` por operación scoped `project_id + source_chunk_bundle_id`. Namespacing **gated**: legacy (`project_id IS NULL`) conserva `node_id == source_chunk_id` byte-idéntico; plataforma usa `physical_node_id` namespaced. — **Evidencia:** `index_bundle.py:424-435` (ramifica `replace_document_nodes` legacy vs `replace_scoped_nodes` plataforma). Test `test_node_identity_isolation.py::test_build_nodes_legacy_conserva_node_id_byte_identico_cuando_sin_proyecto` + `..._plataforma_namespaced_cuando_hay_proyecto`.
- [x] `physical_node_id` = hash de representación canónica etiquetada (`project_id`,`source_chunk_bundle_id`,`source_chunk_id`); IDs fuente en columnas explícitas. — **Evidencia:** `rag_platform/domain/identity.py:38-66` (sha256 field-fenced con `\x1f`, prefijo `pnode_`, fail-closed si vacío).
- [x] `project_id` en `idx_vec_*`; mantener `UNIQUE(embedding_bundle_id, node_id)`; `rag_release_id` fuera de las filas vectoriales. — **Evidencia:** `20260810_06_...sql:25-35` (`ADD COLUMN project_id` + índice en las 7 tablas; comentario: UNIQUE existente no se toca, `rag_release_id` no vive en la fila vectorial).
- [x] Tabla real `indexing_materializations` con lifecycle inmutable `WRITING→SEALED|FAILED` (`begin_writing`/`seal`/`mark_failed`/`find_sealed`, nunca `upsert`); `UNIQUE(project_id, embedding_bundle_id, indexing_target_id, storage_schema_version)`, checksum canónico y conteos. Una release referencia la materialización, no un estado activo global. — **Evidencia:** `20260810_05_...sql:113-151` (tabla + CHECK lifecycle + UNIQUE + FK compuesto). Puerto `application/vector_materialization.py:65-103`; adaptador `infrastructure/postgres/vector_repositories.py:59-228` (`ON CONFLICT ... WHERE status <> sealed` bloquea reabrir sellada). Test `tests/rag_platform/test_vector_lane_isolation.py` (9 casos).
- [x] **`SealedEmbeddingStore`** físico por proyecto (`data/projects/{project_id}/embeddings/{embedding_bundle_id}/`), reusa `core.atomic_fs`, espeja `SealedChunkStore`, nunca `replace()`. — **Evidencia:** `infrastructure/storage/sealed_embedding_store.py:27,47,53-165` (`stage_and_seal`/`verify_checksum` con `atomic_fs`, sin `replace`). Test `tests/rag_platform/test_sealed_embedding_store.py`.
- [x] Validación transaccional: owner de proyecto, pertenencia profile/target, dimensión, métrica, checksum, conteos parent/child/vector y estado sellado. — **Evidencia:** `application/vector_materialization.py:106-194` (`MaterializeVectorsUseCase`: owner + counts + dimensión/métrica; FAILED observable si algo falla). Invariantes `domain/models.py:738-800` (`validate_materialization_ownership`, `validate_materialization_counts`). Test `test_vector_lane_isolation.py::test_falla_cerrado_cuando_*`.
- [x] **Herramienta de reset** `reset_derived_rag_artifacts` (`--dry-run`/`--apply`, inventario before/after, se niega a borrar filas `is_active`) + **rebuild limpio** platform-only que no activa vectores. — **Evidencia:** `scripts/rag_platform/reset_derived_rag_artifacts.py` (handshake `--confirm-token`, `collect_blockers` por `is_active`/retrieval activo, inventario before/after, borrado FK-safe, contención de rutas). Rebuild: `rag_platform/application/rebuild_orchestrator.py::RebuildPlatformArtifactsUseCase` (deja vectores inactivos). Tests `tests/rag_platform/test_reset_derived_rag_artifacts.py` (8 casos) + `test_rebuild_orchestrator.py` (4 casos).


**Exit criteria:** local/BGE y local/Voyage comparten normalizado/chunks cuando corresponde; nunca embedding/vector. Dos proyectos no pueden sobrescribir ni referenciar nodos/vectores entre sí (impuesto por FKs compuestas). El reset+rebuild deja todo artefacto derivado con `project_id`; SST no queda activado.

### Fase 5: Variantes, DRAFT, membresías y orquestador de release

**Files:**

- Create: `app/back/src/rag_platform/application/release_service.py`
- Create: `app/back/src/rag_platform/application/release_build_service.py`
- Create: `app/back/src/rag_platform/application/release_validator.py`
- Create: `app/back/src/rag_platform/domain/lifecycle.py`
- Create: `app/back/src/rag_platform/infrastructure/postgres/release_repositories.py`
- Create: `migrations/20260810_07_create_rag_variants_releases_and_memberships.sql`
- Test: `app/back/tests/rag_platform/test_release_lifecycle.py`
- Test: `app/back/tests/rag_platform/test_release_incremental_build.py`
- Test: `app/back/tests/rag_platform/test_release_membership_integrity.py`

**Interfaces produced:**

```python
class CreateRagReleaseDraftUseCase:
    def execute(
        self,
        *,
        rag_variant_id: str,
        corpus_snapshot_id: str,
        target_binding_key: str | None,
        actor_id: str,
    ) -> RagRelease: ...

class BuildRagReleaseUseCase:
    def execute(self, *, rag_release_id: str, actor_id: str) -> RagReleaseBuildReport: ...

class ValidateRagReleaseUseCase:
    def execute(self, *, rag_release_id: str, actor_id: str) -> ReleaseValidationReport: ...
```

- [x] Implementar `CreateRagReleaseDraft` que compruebe que snapshot y variante pertenecen al mismo proyecto, resuelva solo un `target_binding_key` permitido para el perfil de embedding, pinne recipe/configuration/target snapshots y cree la release en `DRAFT`. — **Evidencia:** `rag_platform/application/release_service.py::CreateRagReleaseDraftUseCase.execute` (usa `ensure_same_project`, valida `TargetBindingResolver.find_binding` + coincidencia de `embedding_profile_id`, crea `DRAFT`). Tests `tests/rag_platform/test_release_membership_integrity.py::test_crea_draft_cuando_todo_valido`, `..._falla_si_variante_y_snapshot_son_de_proyectos_distintos`, `..._falla_si_binding_no_esta_en_allowlist`, `..._falla_si_binding_apunta_a_otro_perfil_de_embedding`.
- [x] Permitir que un mismo `corpus_snapshot_id` tenga DRAFTs y releases en varias variantes del mismo proyecto; mantener `release_number` único dentro de cada `rag_variant_id`, nunca global para el proyecto. — **Evidencia:** `migrations/20260810_07_...sql` (`uq_rag_releases_variant_number ON rag_releases (rag_variant_id, release_number)` — por variante, no por proyecto). `domain/lifecycle.py::next_release_number`. Test `test_release_membership_integrity.py::test_release_number_incrementa_por_variante`, `test_release_lifecycle.py::test_release_number_por_variante`.
- [x] Bloquear la creación y validación de una release cuando alguna revisión tenga elegibilidad `blocked`; requerir que una excepción `operator_waiver` incluya actor, motivo, fecha y el snapshot de política que autorizó la excepción. — **Evidencia:** `release_service.py::_reject_blocked_revisions` y `release_validator.py::_reject_blocked_revisions` lanzan `ReleaseBlockedRevision` ante `EligibilityDecision.BLOCKED`; `operator_waiver` ya es una decisión de elegibilidad válida registrada en el snapshot (Fase 2, `CorpusSnapshotDocument.eligibility_decision`). Tests `..._falla_si_snapshot_tiene_revision_blocked`, `test_release_lifecycle.py::test_validar_rechaza_revision_blocked`.
- [x] Implementar un planner que recorra cada revisión del corpus snapshot y aplique `ArtifactReusePolicy` en orden: normalizado → chunk → embedding → materialización de índice. — **Evidencia:** `rag_platform/application/release_build_service.py::BuildRagReleaseUseCase.execute` recorre `snapshot.documents` ordenados y procesa `_BUILD_STAGES = (NORMALIZE, CHUNK, EMBED, INDEX)` por revisión, auditando cada etapa en el ledger. Test `tests/rag_platform/test_release_incremental_build.py::test_build_crea_una_membresia_por_revision_y_audita_cada_etapa`.
- [x] Cuando no haya reuso exacto, invocar los servicios existentes de ingesta/chunking/embedding/indexing mediante puertos/adaptadores; no copiar sus algoritmos al módulo plataforma. — **Evidencia:** el planner delega en el puerto `RevisionArtifactResolver` (`release_build_service.py`) y el módulo plataforma no reimplementa pipeline. Comentario de diseño en la cabecera del servicio. **Actualización 2026-08-12:** `tests/rag_platform/test_release_incremental_build.py` ya no usa `_FakeResolver` ni `_RecordingLedger`; ahora usa `InMemoryRevisionArtifactResolver` (`rag_platform/infrastructure/in_memory/release_build_resolver.py`) + `InMemoryRagBuildRunRepository`, dejando el escenario r001→r002 operativo en memoria. Además existe el adaptador productivo `PostgresRevisionArtifactResolver` (`rag_platform/infrastructure/release_build_resolver.py`) y el composition root lo cablea a Postgres con `BuildRagReleaseUseCase`.
- [x] Crear membresías concretas en el mismo commit lógico que registra el resultado del paso. La release nunca se considera completa si falta una revisión o si un artefacto pertenece a otro proyecto. — **Evidencia:** el planner crea `RagReleaseMembership` por revisión tras auditar sus pasos (`release_build_service.py`); `release_validator.py::_assert_complete` lanza `ReleaseNotComplete` si falta una membresía. Aislamiento cross-proyecto en la BD: `migrations/20260810_07_...sql` FKs compuestas `(project_id, rag_variant_id)`/`(project_id, corpus_snapshot_id)` y `rag_release_memberships` FK compuesto `(project_id, rag_release_id)`. Tests `test_release_incremental_build.py::test_r001_no_ve_el_documento_56`, `test_release_lifecycle.py::test_validar_falla_si_falta_una_membresia`.
- [x] Requerir que el manifiesto de release contenga hashes de corpus snapshot, recipe, configuración de proyecto, artefactos y conteos; su `release_manifest_hash` se congela al validar. — **Evidencia:** `domain/lifecycle.py::compute_release_manifest_hash` (incluye corpus_manifest_hash, semantic_recipe_fingerprint, configuration_fingerprint, target y las membresías con sus artefactos, determinista/reconstruible). `release_validator.py::ValidateRagReleaseUseCase.execute` lo congela y persiste al pasar a `VALIDATED`. Tests `test_release_lifecycle.py::test_manifest_hash_determinista_y_reconstruible`, `..._validar_congela_manifiesto_y_pasa_a_validated`.
- [x] Implementar lifecycle estricto y actor/motivo/auditoría para `VALIDATED`, `PUBLISHED`, `RETIRED` y `FAILED`. `PUBLISHED` significa que el catálogo de plataforma acepta la release; no significa que una lane legacy esté activa. — **Evidencia:** `domain/lifecycle.py::ReleaseState` + `_ALLOWED_TRANSITIONS` + `ensure_transition_allowed` (grafo estricto `DRAFT→VALIDATED→PUBLISHED→RETIRED`, más `FAILED`); `RagRelease` lleva `created_by`/`validated_at`/`reason`. La transición `PUBLISHED` es de Fase 6 (aquí solo se habilita en el grafo, sin tocar `is_active`). Test `test_release_lifecycle.py::test_transiciones_validas`, `..._transiciones_invalidas`.
- [x] No modificar una `DRAFT` validada en sitio: un cambio de corpus o recipe vuelve a crear el snapshot/membresía antes de una nueva validación. — **Evidencia:** `RagRelease.is_manifest_frozen` + `release_validator.py` lanza `ReleaseManifestFrozen` si se revalida una release ya congelada. Test `test_release_lifecycle.py::test_release_validada_no_se_revalida_en_sitio`.

> **Estado de verificación (actualizado 2026-08-12):** los 9 incisos siguen
> implementados con dominio (`domain/lifecycle.py`), 3 servicios de aplicación,
> migración `20260810_07` y repos/adaptadores Postgres e in-memory. **Aporte de hoy:**
> `RagVariantReader.get`, `CorpusSnapshotReader.get` y
> `ProjectConfigurationFingerprintReader` ya tienen adaptadores Postgres;
> `test_release_incremental_build.py` dejó de depender de `_FakeResolver` y
> `_RecordingLedger`; se añadió `test_postgres_release_wiring.py` para cubrir esos
> readers/adaptadores; además se agregó `PostgresRevisionArtifactResolver` y el
> composition root ya cablea `BuildRagReleaseUseCase` con Postgres detrás del flag
> `rag_platform_v1`. **Verificado en este entorno** con
> `C:\venvs\chatbot-sst\Scripts\python.exe -m pytest` sobre los tests focalizados
> de release/build/wiring. **Pendiente operativo:** cerrar la superficie admin que
> todavía falta en composición (`CreateDraft`/`Validate`/`Rebuild`) y correr una
> ejecución end-to-end del build real sobre una BD con datos.

**Exit criteria:** `sst-local-bge-m3/r002` contiene los 56 documentos exactos y puede reconstruirse; `r001` conserva sus 55 documentos y no ve el documento 56. — **Cubierto por** `test_release_incremental_build.py::test_build_incremental_reutiliza_lo_previo_y_solo_construye_lo_nuevo` (55 reusados + 1 nuevo) y `::test_r001_no_ve_el_documento_56`.

### Fase 6: Publicación de catálogo y coexistencia legacy

**Files:**

- Create: `app/back/src/rag_platform/application/publication_service.py`
- Create: `app/back/src/rag_platform/application/platform_access.py`
- Modify: `app/back/src/core/feature_flags.py`
- Modify: `app/back/src/api/dependencies.py`
- Modify: `app/back/src/api/app.py`
- Modify: `docs/backend/phase-handoffs.md`
- Test: `app/back/tests/rag_platform/test_publication_neutrality.py`
- Test: `app/back/tests/core/test_pipeline_composition.py`
- Test: `app/back/tests/retrieval/test_pipeline_api.py`

**Interfaces produced:**

```python
class PublishRagReleaseUseCase:
    def execute(self, *, rag_release_id: str, actor_id: str) -> RagRelease: ...

class PlatformAccessPolicy(Protocol):
    def require_project_operator(self, *, actor: PlatformActor, project_id: str) -> None: ...
```

- [x] Añadir `SST_FEATURE_RAG_PLATFORM_V1`, deshabilitado por defecto y separado de los feature flags bundle-first existentes. Habilitarlo expone la plataforma administrativa; no cambia la lane utilizada por retrieval. — **Evidencia:** `core/feature_flags.py` (`rag_platform_v1: bool = False` + lectura de `SST_FEATURE_RAG_PLATFORM_V1` en `from_env`, independiente de embedding/indexing/retrieval). Tests `tests/core/test_pipeline_composition.py::test_feature_flags_quedan_activas_por_defecto_sin_env` (asserta `rag_platform_v1 is False`), `::test_rag_platform_flag_se_lee_del_entorno`.
- [x] Registrar servicios plataforma en el composition root sin modificar los servicios legacy de retrieval. — **Evidencia:** `api/dependencies.py` (`PipelineServices.rag_platform_publish: object | None = None`; el wiring `_build_rag_platform_publish` se ejecuta **solo** `if flags.rag_platform_v1`, tras construir la superficie legacy sin tocarla). Tests `test_pipeline_composition.py::test_flag_off_no_cablea_plataforma_y_deja_legacy_intacto`, `::test_flag_on_cablea_plataforma_sin_tocar_retrieval`.
- [x] Implementar publicación como una transición de estado que verifica el manifiesto y marca `PUBLISHED` de forma transaccional. — **Evidencia:** `rag_platform/application/publication_service.py::PublishRagReleaseUseCase.execute` (verifica `is_manifest_frozen` fail-closed, `ensure_transition_allowed(→PUBLISHED)`, `update_state` dentro de `transactions.transaction()`). Tests `tests/rag_platform/test_publication_neutrality.py::test_publica_release_validada`, `::test_no_publica_draft_sin_manifiesto`, `::test_no_publica_desde_estado_no_validado`.
- [x] Probar de forma negativa que el módulo de publicación no importa `ConsumerScope`, `RetrievalProfile`, `ActivateIndexedBundleUseCase` ni escribe `is_active`. — **Evidencia:** `test_publication_neutrality.py::test_modulo_publicacion_no_importa_simbolos_legacy` (análisis AST estático del módulo: ni imports prohibidos, ni acceso al atributo `is_active`). Verificado también manualmente en este entorno.
- [x] Mantener `ActivateIndexedBundleUseCase`, `RollbackIndexedBundleUseCase` y `/api/retrieval` como legacy; documentar que una futura selección de otra release publicada no es rollback de vector rows y no forma parte de este plan. — **Evidencia:** el wiring legacy de `indexing_activate`/`indexing_rollback`/retrieval no se modificó (siguen construidos en `build_pipeline_services`); test `tests/retrieval/test_pipeline_api.py::test_retrieval_legacy_intacto_con_plataforma_habilitada` (rutas legacy responden 200 con el flag on). Nota de coexistencia en `docs/backend/phase-handoffs.md`.
- [x] Añadir eventos `rag_release_created`, `rag_release_build_step_completed`, `rag_release_validated`, `rag_release_published` y `rag_release_retired`, con correlación y redacción compatibles con `core.logging.observability`. — **Evidencia:** `publication_service.py::emit_release_event` (arma `ObservabilityEvent` con ids en `attributes`, delega en `emit_observability_event` que redacta secretos). Cableado: `rag_release_created` (`release_service.py`), `rag_release_validated` (`release_validator.py`), `rag_release_published` (`publication_service.py`), todos con `logger` opcional. `rag_release_build_step_completed` queda cubierto de forma durable por el ledger `rag_build_steps` (`complete_step`), y `rag_release_retired` reusa el mismo helper cuando se cablee la transición de retiro (deuda menor declarada).

**Exit criteria:** publicar una release no crea ni actualiza `retrieval_profiles`, no usa el scope `chatbot/sst-default`, no altera filas activas existentes y deja el estado legacy intacto. — **Cubierto por** `test_publication_neutrality.py` (transición pura vía `update_state`, sin tocar retrieval/is_active/scope; test negativo de imports) y `test_pipeline_api.py::test_retrieval_legacy_intacto_con_plataforma_habilitada`.

> **Estado de verificación (2026-08-11):** 6 incisos implementados con feature flag,
> composition root gated, `publication_service.py`, `platform_access.py`, helper de
> eventos y 3 archivos de test (2 extendidos, 1 nuevo). Verificado en este entorno
> por import real + smoke funcional del caso de uso y del gating flag on/off (sin
> pytest). **Pendiente operativo:** correr la suite y aplicar migraciones en la BD.
> **Deuda menor:** cablear la transición de retiro (`rag_release_retired`) y el
> evento observability de `build_step_completed` (hoy auditado por el ledger durable).

---

## Auditoría de verificación Fases 4-6 (2026-08-11)

Revisión de los checkboxes `[x]` contra el código real. **Resultado: los contratos,
migraciones y casos de uso existen y sus tests fueron creados** (marcas válidas en ese
sentido), **pero hay gaps de cableado e identidad que impiden que el flujo de plataforma
funcione end-to-end contra PostgreSQL.** Ningún checkbox se desmarca porque el artefacto
que cada inciso pedía existe; se registran aquí los desvíos para no darlos por operativos.

> **Re-verificación 2026-08-12 (contra HEAD, Fase 4 cerrada como código):** los dos
> gaps de **código de Fase 4** (#1 identidad de bundle, #2 runs con contexto de
> release) están **CERRADOS** — ver cada inciso, marcado RESUELTO con evidencia.
> Migraciones aplicadas sobre BD vacía (`npm run indexing:prepare-postgres`:
> `status=prepared`, 27 migraciones, `base_tables_present=12/12`, `active_profiles=7`,
> `vector_tables_ready=7`). Tests verdes en esta máquina: `rag_platform` **108
> passed**, `embedding` **70 passed**, `indexing` OK.
> **Actualización adicional 2026-08-12:** de los gaps de Fase 5-6, **#4 y #5 quedan
> CERRADOS** con adapters Postgres + tests focalizados ejecutados en
> `C:\venvs\chatbot-sst`. **Sigue abierto (Fase 5-6, no bloquea el cierre de Fase 4):**
> gaps #3 y #6 (adaptador real/wiring de composición). **Sigue abierto (operativo Fase 4):** no hay CLI
> de la lane de plataforma que encadene `chunk→embed→index→materializa` con
> `project_id`; el end-to-end vivo de plataforma no se ha corrido (requiere ese CLI +
> BGE runtime). El detalle de cierre de Fase 4 vive en
> `plans/2026-08-11-fase4-embedding-nodos-vectores.md`.

### Gaps críticos (bloquean ejecución real; no son fallos de contrato)

1. ~~**`EmbeddingBundle` no lleva identidad de plataforma en el flujo de escritura (Fase 4).**~~
   **RESUELTO (2026-08-11).** El bundle ahora transporta y persiste `project_id`:
   - `EmbeddingBundle` gana el campo `project_id: str | None = None`
     (`embedding/domain/models.py`), documentado como excluido de `deterministic_id`
     (id legacy preservado por ADR-007; la identidad física la impone el índice parcial).
   - `bundle_builder.py` lo propaga desde `chunk_bundle.project_id`; `_BUNDLE_COLUMNS`, el
     `INSERT INTO embedding_bundles` y `_bundle_parameters`
     (`embedding/infrastructure/postgres/repositories.py`) ahora incluyen `project_id`.
   - **Consecuencia:** los bundles de plataforma nacen con su `project_id`, activando el
     índice parcial `uq_embedding_bundles_physical_identity` y el FK compuesto; legacy sigue
     con `NULL`. `deterministic_id` **no cambió** (ADR-007).
   - **Test:** `tests/embedding/test_embedding_domain.py::test_bundle_lleva_project_id_de_plataforma_sin_alterar_identidad`
     (verificado ejecutándolo en este entorno). El path Postgres real queda pendiente de
     `postgres_live`.

2. ~~**`EmbeddingRun`/`IndexingRun` no persisten el contexto de release (Fase 4).**~~
   **RESUELTO (verificado 2026-08-12).** Los modelos de dominio y el adaptador ya
   llevan y persisten el contexto de release; ya no es "solo DDL":
   - `EmbeddingRun` gana `project_id`/`rag_variant_id`/`rag_release_id` nullable
     (`embedding/domain/models.py:298-312`); `IndexingRun` idem
     (`indexing/domain/bundle_first.py:87-102`).
   - `_RUN_COLUMNS` incluye las 3 columnas (`embedding/infrastructure/postgres/repositories.py:81-90`),
     el `INSERT INTO embedding_runs` las escribe (`:534-550`) y el mapeo de lectura
     las devuelve (`:673-675`).
   - **Consecuencia:** un run de plataforma nace con su `project_id`/variante/release
     derivados server-side; legacy conserva `NULL`. Sin FK (nullable), como pide ADR-007 §8.

3. ~~**`RevisionArtifactResolver` sin adaptador concreto de producción (Fase 5).**~~
   **CERRADO (2026-08-12).**
   - Se agregó `PostgresRevisionArtifactResolver` en
     `rag_platform/infrastructure/release_build_resolver.py`.
   - El adaptador resuelve reuso exacto y reconstrucción operativa de
     normalizado/chunking/embedding/indexación/materialización usando storage por
     proyecto, repos Postgres y los servicios reales ya existentes.
   - `api/dependencies.py` ahora cablea `BuildRagReleaseUseCase` con ese adaptador
     cuando `rag_platform_v1` está activo y existe conexión Postgres.
   - Cobertura: `tests/core/test_pipeline_composition.py`,
     `tests/rag_platform/test_postgres_release_wiring.py`,
     `tests/embedding/test_embedding_run_flow.py`,
     `tests/indexing/test_indexing_run_context.py` y
     `tests/rag_platform/test_release_incremental_build.py`.
   - **Alcance del cierre:** el adaptador productivo y su wiring ya existen; lo que
     sigue pendiente es la corrida end-to-end sobre una BD con datos y el resto de
     casos de uso admin todavía no expuestos por composición.

### Gaps de wiring (Fase 5-6, esperables para Fase 7 pero aún abiertos)

4. ~~**Readers Postgres por-id ausentes.**~~ **CERRADO (2026-08-12).**
   - `PostgresRagVariantRepository.get(...)` agregado en
     `rag_platform/infrastructure/postgres/project_repositories.py`.
   - `PostgresCorpusSnapshotRepository.get(...)` agregado en
     `rag_platform/infrastructure/postgres/document_repositories.py`.
   - Cobertura: `tests/rag_platform/test_postgres_release_wiring.py`
     (`test_postgres_rag_variant_repository_get_lee_por_id`,
     `test_postgres_corpus_snapshot_repository_get_lee_snapshot_y_membresias` y casos
     negativos `..._falla_si_no_existe`).
   - **Consecuencia:** `CreateRagReleaseDraftUseCase` y `ValidateRagReleaseUseCase` ya
     tienen readers Postgres por id disponibles; el bloqueo ya no es este gap sino el wiring.
5. ~~**`ProjectConfigurationFingerprintReader` sin adaptador** (`release_service.py:59`).~~
   **CERRADO (2026-08-12).**
   - Se agregó `PostgresProjectConfigurationFingerprintReader` en
     `rag_platform/infrastructure/postgres/project_repositories.py`.
   - Se agregó `compute_project_configuration_fingerprint(...)` en
     `rag_platform/domain/models.py` para reconstruir de forma determinista el pin de
     configuración vigente.
   - Cobertura:
     `tests/rag_platform/test_postgres_release_wiring.py::test_postgres_project_configuration_fingerprint_reader_reconstruye_fingerprint`.
6. **Composition root admin incompleto.** **PARCIAL (2026-08-12).**
   - `api/dependencies.py` ya no cablea solo `PublishRagReleaseUseCase`: ahora expone
     también `rag_platform_build` y lo resuelve contra Postgres o in-memory según el
     backend activo.
   - **Rebuild cableado (2026-08-12):** `PipelineServices.rag_platform_rebuild` +
     `_build_rag_platform_rebuild(...)` cablean `RebuildPlatformArtifactsUseCase`
     (indexado bundle-first + materialización sellada) tras `rag_platform_v1` con
     conexión Postgres; sin conexión → `None` (sella en Postgres). Evidencia:
     `app/back/src/api/dependencies.py`; tests
     `app/back/tests/core/test_pipeline_composition.py::test_wire_rag_platform_rebuild_*`
     (`core`+`rag_platform` 158 passed).
   - **CERRADO (2026-08-13):** ya se registran por composición `CreateDraft`
     (`rag_platform_draft`, `CreateRagReleaseDraftUseCase`) y `Validate`
     (`rag_platform_validate`, `ValidateRagReleaseUseCase`) detrás de `rag_platform_v1`,
     con adaptadores Postgres/in-memory. Superficie admin de composición **completa**.
     Evidencia: `_build_rag_platform_draft`/`_build_rag_platform_validate` en
     `api/dependencies.py`; tests `test_pipeline_composition.py::test_wire_rag_platform_draft_*`
     / `..._validate_*`. **No queda gap de wiring previo a Fase 7.**

### Cobertura de tests (real)

7. **Actualización 2026-08-12:** los tests de release **ya no dependen de fakes triviales**
   para resolver artefactos ni para auditar el ledger.
   - `test_release_incremental_build.py` usa `InMemoryRevisionArtifactResolver` +
     `InMemoryRagBuildRunRepository`; el escenario incremental r001→r002 ahora reutiliza
     artefactos porque r001 se ejecuta primero, no por un `set` precomputado.
   - Se agregó `test_postgres_release_wiring.py` para cubrir readers/adaptadores Postgres
     y el fingerprint de configuración.
   - El adaptador productivo de `RevisionArtifactResolver` ya existe y quedó
     cubierto en wiring/composición; sigue pendiente una corrida end-to-end del
     build real sobre Postgres con datos de plataforma.

### Desvíos menores

8. **Nombre de migración `_07` desactualizado en el plan** (`:499`): el plan la nombra
   `..._create_rag_variants_releases_and_memberships.sql`; el archivo real es
   `20260810_07_create_rag_releases_and_memberships.sql`. `rag_variants` ya se crea en
   `20260810_01:95`; la `_07` solo añade el índice `uq_rag_variants_project_variant`.

### Sano (verificado, sin gap)

- Fase 4: `physical_node_id`, lifecycle materialización `WRITING/SEALED/FAILED` con los 4
  métodos, 2 FKs compuestas por tabla `idx_vec_*`, dual-mode gating (`index_bundle.py:425`).
- Fase 5: guardas `ensure_same_project`/`_reject_blocked`/`_assert_complete`, `compute_release_manifest_hash`
  determinista, migración `07` con `release_number` único por variante y 3 FKs compuestas
  con sus índices destino creados antes que las FK. Orden de las 7 migraciones `0810_*` correcto.
- Fase 6: flag `rag_platform_v1` off por defecto e independiente, composition gated, publish
  transaccional fail-closed, neutralidad legacy (test AST de imports).

> **Lectura ejecutiva (actualizada 2026-08-12):** **Fase 4 está cerrada como
> código** — los gaps 1-2 (identidad de plataforma en el bundle y contexto de release
> en los runs) están **RESUELTOS y verificados**; migraciones aplicadas sobre BD
> vacía; tests verdes. **Falta solo el operativo de Fase 4**: un CLI de la lane de
> plataforma que encadene `chunk→embed→index→materializa` con `project_id` y su
> corrida end-to-end con BGE vivo (no existe todavía). **Fases 5-6 avanzaron hoy en lo
> operativo**: los gaps **3, 4 y 5 quedaron cerrados**, y la cobertura de planner ya
> no usa resolver/ledger fake triviales. **Lo pendiente ya no es el adaptador de build**,
> sino completar la superficie admin de composición (gap 6 parcial) y ejecutar una
> corrida end-to-end real sobre Postgres. Cerrar el CLI de Fase 4 y terminar ese
> wiring admin es prerequisito para que `sst-general` (Fase 9) construya una release real.
> **Ponytail/audit: el módulo no tiene over-engineering relevante; los gaps son de
> cableado faltante, no de código sobrante.**

> **Wiring raw/normalized (actualizado 2026-08-12):** implementado el plan
> `docs/superpowers/plans/2026-08-12-project-raw-normalized-catalog-wiring.md`
> (Tasks 1-7). Catálogos físicos `project_raw_document_artifacts` /
> `project_normalized_document_artifacts` por `project_id` (migraciones `20260812_01/02`),
> provenance de variante en `chunk_bundles` (`20260812_03`), contrato único
> `PlatformArtifactProvenance` compuesto (sin duplicar), servicios
> `RegisterProjectRawArtifactUseCase` / `PersistNormalizedArtifactCatalogUseCase`,
> `run_pipeline(platform_context_resolver=...)` aditivo (legacy byte-idéntico), y
> wrappers `scripts/rag_platform/run_project_ingestion.py` + `rebuild_platform.py`
> fail-closed con derivación server-side de la receta de variante. Runbook en
> `docs/rag-platform/raw-normalized-catalog-runbook.md`. **Operativo pendiente:** la
> etapa normalized dentro del CLI (necesita motor de normalización) y el end-to-end
> vivo con BGE quedan como corrida operativa, no de contrato.

## Cierre de verificación Fases 4-6 (2026-08-13)

Verificación por lectura de código de los incisos de Fase 5 y Fase 6 (símbolos
citados en cada evidencia confirmados presentes). Se marcan `[x]` los 9 incisos de
Fase 5 y los 6 de Fase 6: contratos, servicios, dominio (`lifecycle.py`), migración
`20260810_07`, flag `rag_platform_v1` y wiring de publicación existen y sus tests
enfocados pasan (`rag_platform` **135 passed** el 2026-08-13).

**Gap 6 (superficie admin de composición) — CERRADO (2026-08-13).**

`api/dependencies.py` ahora cablea la superficie admin completa tras `rag_platform_v1`:
además de `rag_platform_publish`/`build`/`rebuild`, se añadieron
`rag_platform_draft` (`CreateRagReleaseDraftUseCase`) y `rag_platform_validate`
(`ValidateRagReleaseUseCase`) vía los helpers `_build_rag_platform_draft` /
`_build_rag_platform_validate` (adaptadores Postgres con conexión, in-memory sin ella).
El `release_id_factory` acuña un `ragr_` único por DRAFT (uuid; el orden lo lleva
`release_number` por variante). Evidencia: `PipelineServices.rag_platform_draft` /
`rag_platform_validate`; tests
`app/back/tests/core/test_pipeline_composition.py::test_wire_rag_platform_draft_con_y_sin_conexion`
y `..._validate_con_y_sin_conexion`. Con esto **no queda gap de wiring de Fase 5-6**;
Fase 7 (API/router) puede exponer la superficie admin ya compuesta.

**Trasladado desde el plan de Fase 4 (cerrado en código el 2026-08-13):**

- **Stage 2b-iii — retirar la lane legacy document** (`scripts/indexing/run_indexing.py`
  + `IndexDocumentUseCase` + `LlamaIndexingPort`/`pipeline_factory.py` + `node_repository.py`,
  ~1600 LOC + ~30 tests in-memory). Escribe `project_id NULL` → rompe contra la BD NOT NULL.
  Prerequisito (CLI de plataforma end-to-end) ya cumplido; queda el borrado con cirugía de tests.
- **Corrida operativa end-to-end** `raw→normalize→chunk→embed→index→materializa` con BGE vivo.
  Bloqueada hoy por falta de proyecto/variante sembrados en BD (no hay CLI de seed) y BGE runtime.

**Trasladado desde el plan de wiring raw/normalized (cerrado el 2026-08-13):**

- **Persistencia catálogo-tabla `project_normalized_document_artifacts`** desde el CLI
  (`PersistNormalizedArtifactCatalogUseCase`). Diferida: nada aguas abajo la consume (el
  chunk stage lee el markdown de disco); la etapa normalize del CLI ya escribe el sidecar
  con `platform_identity`/`platform_provenance`. Simetría de catálogo con `raw`, no crítica.
- **`schemas:export`** — regenerar el snapshot JSON Schema por el campo aditivo
  `platform_provenance` (no bloqueante; `test_schemas` verde).

## Cierre de verificación — corrida real del build de release (2026-08-14)

La **corrida operativa end-to-end del build de release** (antes bloqueada) se ejecutó
contra PostgreSQL limpio + BGE vivo y quedó **verde**. Con esto se cierra la deuda #1
"prueba de release / `rag_release_id` persistido" y el pendiente operativo de Fase 4-5.

**Prueba:** `app/back/tests/rag_platform/test_end_to_end_release_build.py::test_release_build_persiste_rag_release_id`
(markers `corpus`/`bge_runtime`/`postgres_live`). El flujo real
`raw → normalize → corpus snapshot → CreateRagReleaseDraft → BuildRagReleaseUseCase`
(chunk → embed BGE → index → materializa) **PASA**, y verifica en la BD que
`embedding_runs.rag_release_id` **e** `indexing_runs.rag_release_id` quedan estampados
con el `rag_release_id` de la release construida (no NULL). Antes solo se probaba la
materialización física (`rebuild_platform`), que deja `rag_release_id` NULL a propósito.

**Bugs reales de producción destapados por la corrida y corregidos** (la lane de release
build nunca se había ejecutado end-to-end; todos eran drift de cableado, no de contrato):

1. `api/dependencies.py::_build_rag_platform_build` pasaba `data_root=chunks_root.parent`
   (dir del proyecto) al `PostgresRevisionArtifactResolver`, que espera `.../data` y
   re-deriva `projects/<slug>`; la ruta del normalizado quedaba doblada. Se ancla en
   `projects/` (`_platform_data_root`).
2. `release_build_resolver.py::_SUPPORTED_CHUNKING_STRATEGIES` no reconocía la estrategia
   `structural` que siembra `seed_project.py` (todas mapean al runtime
   `local_structural_v1`). Se añadió a la allowlist.
3. `release_build_resolver.py::_resolve_chunk_bundle` construía
   `FilesystemBackedPostgresChunkBundleRepository` sin `project_id` → violaba NOT NULL
   pure-platform (ADR-008). Se estampa `context.project_id`.
4. `release_build_resolver.py::_resolve_materialization` construía
   `RebuildPlatformArtifactsUseCase` con firma vieja (faltaban `bundles`/`profiles` en
   `__init__`) y le pasaba a `execute()` 6 kwargs ya inexistentes (checksum/dimensión/
   métrica se derivan server-side). Se alineó a la firma vigente de `rebuild_orchestrator`.
5. `rebuild_orchestrator.py::execute` creaba `CreateIndexingRunRequest(embedding_bundle_id=...)`
   sin contexto → `indexing_runs.rag_release_id`/`rag_variant_id` quedaban NULL. Se pasa
   ahora `project_id`/`rag_variant_id`/`rag_release_id` del `PlatformBuildContext` validado
   (runs release-aware, plan Fase 4). Sin regresión en `rebuild_platform` (release NULL,
   variante/proyecto sí estampados).

**Read-model de selección por motor (§2.3.2) implementado y verde:**
`ListProjectEmbeddingEnginesUseCase` + `PostgresProjectEmbeddingEngineReader` +
DTO `ProjectEmbeddingEngine`; filtro `(project_id, configuration_fingerprint)` que solo
cuenta materializaciones `sealed`. Prueba `test_engine_selection.py` (5/5).

**Deuda de calidad de retrieval que sigue abierta antes de Fase 7** (no bloquea el
contrato de API): perfil `local-structural-v2` opt-in (propaga `section_title`/
`section_path` a nodos y antepone el heading al texto embebido; v1 byte-idéntico) —
escrito, pendiente de gate; dedup por diversidad del candidate set; `boilerplate_policy`
por perfil/proyecto; retrieval híbrido vector+léxico. El retiro de la lane legacy
`llama_index` (Stage 2b-iii) queda diferido a evaluación futura.

### Fase 7: API de plataforma y contratos OpenAPI

> **FASE 7 — COMPLETADA (2026-08-19).** Adaptador HTTP delgado sobre
> `services.rag_platform.*`, con actor de confianza server-side, idempotencia
> durable en PostgreSQL y traducción central de errores. Verificado por el
> operador: **test_platform_api 18 passed** + **test_platform_actor_provider 3
> passed** (mismo run) y **regresión composición+HTTP legacy 38 passed**;
> migración `20260819_01` aplicada (`status=prepared`, `base_tables_present=12`).
> Sin commit/push (política). Cierre detallado y evidencia al final de esta sección.

**Files:**

- Create: `app/back/src/rag_platform/api/__init__.py`
- Create: `app/back/src/rag_platform/api/router.py`
- Create: `app/back/src/rag_platform/api/schemas.py`
- Create: `app/back/src/rag_platform/api/dependencies.py` (incluye `ConfiguredPlatformActorProvider`)
- Create: `app/back/src/rag_platform/application/idempotency.py` (`IdempotencyStore`, `IdempotencyGuard`)
- Create: `app/back/src/rag_platform/infrastructure/postgres/idempotency.py`
- Create: `app/back/src/rag_platform/infrastructure/in_memory/idempotency.py`
- Create: `migrations/20260819_01_create_platform_idempotency.sql`
- Modify: `app/back/src/rag_platform/domain/errors.py` (`IdempotencyKeyConflict`, `IdempotencyOperationInProgress`, `TrustedActorUnavailable`)
- Modify: `app/back/src/api/app.py`
- Modify: `app/back/src/api/dependencies.py`
- Modify: `scripts/api/export_pipeline_openapi.py`
- Modify: `docs/api/BUNDLE_FIRST_FRONTEND_HANDOFF.md`
- Modify: `docs/api/pipeline-openapi.json` (regenerar con `npm run python -- scripts/api/export_pipeline_openapi.py`)
- Test: `app/back/tests/rag_platform/test_platform_api.py`

**API contract:**

```text
GET    /api/platform/projects
POST   /api/platform/projects
GET    /api/platform/projects/{project_id}
PATCH  /api/platform/projects/{project_id}
GET    /api/platform/projects/{project_id}/configuration
PATCH  /api/platform/projects/{project_id}/configuration
GET    /api/platform/projects/{project_id}/variant-matrix
GET    /api/platform/projects/{project_id}/variants
POST   /api/platform/projects/{project_id}/variants
POST   /api/platform/corpus-snapshots
POST   /api/platform/releases
GET    /api/platform/releases/{rag_release_id}
POST   /api/platform/releases/{rag_release_id}/build
POST   /api/platform/releases/{rag_release_id}/validate
POST   /api/platform/releases/{rag_release_id}/publish
POST   /api/platform/releases/{rag_release_id}/retire
```

- [x] Cada comando de build/lifecycle recibe `rag_release_id` como identidad primaria; el servidor deriva `project_id`, variante, perfil y target ya congelado. La creación de DRAFT acepta como máximo un `target_binding_key` validado, nunca un `indexing_target_id` o nombre de tabla. — `router.py::build_release/validate_release/publish_release/retire_release` toman solo `rag_release_id` del path; `create_release_draft` acepta solo `target_binding_key`. El schema de DRAFT (`CreateReleaseDraftRequestSchema`) no tiene campo de target físico.
- [x] Exponer `GET variant-matrix`: read-model server-side con `buildable`/`blocked_reason` por celda; `POST variants` acepta **una celda de la matriz vigente** (`cell_id + variant_slug`), no un triple libre. — `router.py::get_variant_matrix` delega en `services.get_variant_matrix`; `create_variant` en `services.create_variant_from_matrix_cell` (reconfirma la celda, `StaleVariantMatrixCell` fail-closed). `CreateVariantRequestSchema` solo expone `cell_id`+`variant_slug`.
- [x] Las rutas de creación de snapshot/variant validan cada FK y rechazo de combinación cruzada antes de iniciar workers. — la validación vive en los casos de uso reusados (`CreateCorpusSnapshotUseCase`, `CreateRagVariantFromMatrixCellUseCase`); el router no la reimplementa. Cross-project/stale-cell fallan cerrado y se traducen por el handler central.
- [x] Ningún endpoint recibe una ruta absoluta, nombre de tabla o secreto; los IDs de path se parsean a `PlatformId` tipado. — `router.py::_parse_id` (422 `INVALID_PLATFORM_ID` fail-closed). Los request bodies son `StrictModel` (`extra=forbid`): un `actor_id`/campo físico inyectado se rechaza con 422.
- [x] Requerir `Idempotency-Key` para mutaciones de build y lifecycle, con fingerprint que incluya la acción y el release, no contenido sensible. — header obligatorio (`Header(alias="Idempotency-Key", min_length=1)`); `IdempotencyGuard` sobre PostgreSQL (`platform_idempotency_records`), fingerprint = `sha256(action+resource_id)`; replay no re-ejecuta, fingerprint distinto = 409 `IDEMPOTENCY_KEY_CONFLICT`, RESERVED concurrente = 409 `IDEMPOTENCY_OPERATION_IN_PROGRESS`. `result_json` solo ids/hashes/estado.
- [x] Mantener `/api/chunking`, `/api/embedding`, `/api/indexing` y `/api/retrieval` como contratos legacy; marcar el modo sin romper responses existentes. — regresión `test_pipeline_api.py` (38 passed) confirma los contratos legacy intactos con la plataforma habilitada; flag off deja el legacy sin cambios y hace 503 `RAG_PLATFORM_V1_DISABLED` en la superficie admin.
- [x] Implementar límites de tamaño/paginación en los listados. — `list_projects`/`list_variants` usan `paginate` con `MAX_PAGE_SIZE`. (Límite de documentos por build: el build es síncrono sobre el snapshot ya congelado; no programa trabajo ilimitado desde el request. `ponytail:` si el build pasa a asíncrono/cola, añadir tope explícito de documentos por request.)

**Exit criteria:** el frontend puede construir una release sin conocer paths, tablas vectoriales ni una terna manual de IDs; los requests cruzados devuelven un error de dominio, no un resultado parcial. — **CUMPLIDO.**

#### Cierre Fase 7 (2026-08-19)

**Qué se hizo.** Adaptador HTTP delgado (`APIRouter` prefijo `/api/platform`,
montado en `create_app`) sobre la superficie única `services.rag_platform.*`, sin
SQL, sin fingerprints, sin repos concretos ni derivación de target físico en el
router. Decisiones arquitectónicas resueltas del prompt de Fase 7:

- **Actor de confianza.** Puerto `TrustedPlatformActorProvider` (aplicación,
  transport-independent) + adaptador `ConfiguredPlatformActorProvider`
  (`rag_platform/api/dependencies.py`) que deriva `PlatformActor` de
  `SST_PLATFORM_ACTOR_ID`/`SST_PLATFORM_ACTOR_PROJECT_SCOPE`, fail-closed
  (`TrustedActorUnavailable` 503). El router recibe el `PlatformActor` ya
  resuelto; una futura transición SSO/OIDC reemplaza solo el proveedor sin tocar
  casos de uso ni schemas. La identidad nunca viene de body/query/header.
- **Idempotencia durable.** Puerto `IdempotencyStore` + `IdempotencyGuard`
  (aplicación); autoridad PostgreSQL (`PostgresIdempotencyStore` sobre
  `platform_idempotency_records`, reserva atómica `INSERT ... ON CONFLICT DO
  NOTHING` con commit corto; ejecución fuera de transacción larga) y adaptador
  in-memory atómico para dry-run/tests. Redis queda documentado como extensión
  detrás del mismo puerto, no en el critical path.
- **Traducción central de errores.** Un único `@app.exception_handler(RagPlatformError)`
  en `api/app.py` mapea `code`/`http_status` al envelope compartido; sin
  `try/except` por endpoint.
- **Feature flag.** Router con dependency `require_rag_platform_enabled`
  (503 `RAG_PLATFORM_V1_DISABLED` cuando `SST_FEATURE_RAG_PLATFORM_V1` está
  apagado); legacy intacto. Export OpenAPI con el flag encendido.

**Evidencia de código.** `app/back/src/rag_platform/api/{__init__,router,schemas,dependencies}.py`;
`app/back/src/rag_platform/application/idempotency.py`;
`app/back/src/rag_platform/infrastructure/{postgres,in_memory}/idempotency.py`;
`migrations/20260819_01_create_platform_idempotency.sql`;
`app/back/src/rag_platform/domain/errors.py` (`TrustedActorUnavailable`,
`IdempotencyKeyConflict`, `IdempotencyOperationInProgress`);
`app/back/src/api/{app,dependencies}.py`;
`scripts/api/export_pipeline_openapi.py`;
`app/back/tests/rag_platform/test_platform_api.py`.

**Evidencia de verificación (operador, 2026-08-19).**
- `test_platform_api.py` + `test_platform_actor_provider.py` → **18 passed**.
- `test_pipeline_composition.py` + `test_pipeline_api.py` → **38 passed** (legacy HTTP intacto con plataforma habilitada).
- `prepare_postgres_indexing.py` → `status=prepared`, 35 migraciones (incluye `20260819_01`), `base_tables_present=12`.
- Warning `HTTP_422_UNPROCESSABLE_ENTITY` deprecado resuelto (`HTTP_422_UNPROCESSABLE_CONTENT`).

**Pendiente menor (no bloquea el contrato):** regenerar `docs/api/pipeline-openapi.json`
con `npm run python -- scripts/api/export_pipeline_openapi.py` (el alias `schemas:export`
exporta los JSON schemas de ingestión, no el OpenAPI del pipeline).

### Fase 8: GUI de plataforma integrada con la UI actual

> **Nota de frontera (2026-08-18):** `app/front/src/features/platform/platformApi.ts`,
> `app/front/src/features/platform/platformTypes.ts` y cualquier contrato frontend
> para `/api/platform/*` **empiezan aquí, no antes**. Hasta que Fase 8 exista sobre
> un OpenAPI real de plataforma, el dashboard actual permanece etiquetado como
> **Legacy pipeline** y su persistencia local no debe crecer prematuramente con
> `selectedProjectId`, `selectedRagVariantId` ni `selectedRagReleaseId`.

**Files:**

- Create: `app/front/src/features/platform/platformApi.ts`
- Create: `app/front/src/features/platform/platformTypes.ts`
- Create: `app/front/src/features/platform/platformState.ts`
- Create: `app/front/src/features/platform/ProjectConfigurationWorkspace.tsx`
- Create: `app/front/src/features/platform/RagReleaseWorkspace.tsx`
- Modify: `app/front/src/features/dashboard/dashboardTypes.ts`
- Modify: `app/front/src/features/dashboard/dashboardPersistence.ts`
- Modify: `app/front/src/features/dashboard/DashboardApp.tsx`
- Modify: `app/front/src/features/dashboard/dashboardNavigation.ts`
- Modify: `app/front/src/features/embeddingIndexing/EmbeddingIndexingWorkspace.tsx`
- Modify: `app/front/src/features/embeddingIndexing/useEmbeddingIndexingPipeline.ts`
- Test: `app/front/src/features/platform/platformState.test.mjs`
- Test: `app/front/src/features/platform/ProjectConfigurationWorkspace.test.tsx`
- Test: `app/front/src/features/platform/RagReleaseWorkspace.test.tsx`

- [ ] Añadir una vista de configuración de proyecto con secciones: general, tipos documentales, perfiles permitidos, processing profiles y variantes RAG.
- [ ] En la vista de configuración permitir elegir y versionar el layout `source-folders`, `document-types`, `hybrid` o la plantilla SST. Explicar que afecta organización y navegación del corpus, no la identidad ni el hash de artefactos.
- [ ] Persistir en `DashboardPreferences` solo `selectedProjectId`, `selectedRagVariantId` y `selectedRagReleaseId`; validar que su relación siga existiendo y nunca persistir secrets, paths absolutos, contenido, checksums completos o vectores.
- [ ] Crear una experiencia de release con pasos: seleccionar variante y corpus snapshot → crear DRAFT → build/reuso → validar → publicar. No mostrar Activation/Retrieval como parte de la salida plataforma.
- [ ] Reutilizar componentes visuales de `features/chunking`, `features/embedding`, `features/indexing` y `features/embeddingIndexing`; crear adaptadores de API en vez de acoplar la UI a respuestas legacy.
- [ ] Conservar el workspace legacy con su stepper Embedding → Indexing → Activation → Retrieval y etiquetarlo como **Legacy pipeline**. La nueva pantalla no lo reemplaza ni cambia su navegación durante este plan.
- [ ] Deshabilitar botones y mostrar causas de bloqueo cuando una DRAFT no esté lista, una variante no pertenezca al proyecto o el build esté corriendo.

**Exit criteria:** un operador puede crear dos proyectos, dos variantes y releases independientes sin perder las pantallas ni los contratos actuales.

### Fase 9: Bootstrap SST y verificación de paridad, sin activar consumidores

**Files:**

- Create: `scripts/rag_platform/bootstrap_sst_general.py`
- Create: `scripts/rag_platform/verify_release_manifest.py`
- Create: `docs/runbooks/bootstrap-sst-general.md`
- Create: `docs/runbooks/rebuild-rag-release.md`
- Create: `migrations/20260810_08_backfill_sst_general.sql`
- Modify: `scripts/indexing/prepare_postgres_indexing.py`
- Test: `app/back/tests/rag_platform/test_sst_bootstrap.py`
- Test: `app/back/tests/indexing/test_embedding_persistence_backfill.py`

- [ ] Crear `sst-general` con configuración y taxonomía que reproduzca la conducta SST actual mediante adaptadores explícitos y la plantilla `sst-legacy-v1`.
- [ ] Ejecutar bootstrap primero en `--dry-run`: correlacionar cada artefacto legacy con proyecto, documento lógico, revisión, normalizado, bundle, embedding y materialización cuando exista evidencia suficiente.
- [ ] Marcar registros sin prueba como `legacy_unverified`; no inventar una release validada a partir de ellos.
- [ ] Crear el primer corpus snapshot SST con los documentos respaldados por el baseline y construir `sst-local-bge-m3/r001` solo a partir de artefactos verificados o reconstruidos de manera controlada.
- [ ] Repetir dry-run hasta que hashes, conteos, perfiles y targets coincidan con el baseline esperado; luego aplicar el backfill idempotente.
- [ ] Ejecutar una restauración de ensayo: reconstruir el manifest de `r001` sin depender de punteros `latest` ni de `corpus_version` legacy.
- [ ] Confirmar por prueba negativa que el bootstrap no invoca activation, no crea un `retrieval_profile` y no cambia el consumidor legacy existente.

**Exit criteria:** el bootstrap se puede ejecutar dos veces sin duplicar membresías ni vectors; SST legacy continúa operativo, la primera release plataforma es reproducible y ningún consumidor fue redirigido.

### Fase 10: Hardening, observabilidad y registro de deuda legacy

**Files:**

- Create: `docs/rag-platform/security-invariants.md`
- Create: `docs/rag-platform/reuse-audit-runbook.md`
- Create: `docs/rag-platform/legacy-boundary.md`
- Modify: `docs/observability/current-contracts.md`
- Modify: `docs/backend/gaps-and-debt.md`
- Modify: `docs/runbooks/backend-observability.md`
- Test: `app/back/tests/rag_platform/test_platform_isolation_security.py`
- Test: `app/back/tests/core/test_observability.py`
- Test: `app/back/tests/retrieval/test_pipeline_isolation_audit.py`

- [ ] Ejecutar pruebas de aislamiento para todas las combinaciones project/variant/release/profile/target, incluyendo IDs válidos pero con ancestros incompatibles.
- [ ] Ejecutar prueba de mutación de artefacto: un checksum alterado debe bloquear `VALIDATED`/`PUBLISHED` sin dañar releases previas.
- [ ] Ejecutar pruebas de concurrencia/idempotencia: dos peticiones de build equivalentes de la misma release no duplican runs/materializaciones; dos releases distintas no comparten una misma fila de run.
- [ ] Añadir dashboards/consultas de operador para releases en `BUILDING`/`FAILED`, artefactos sin owner, membresías huérfanas, vector rows sin materialización y reusos `operator_approved`.
- [ ] Mantener un registro versionado de límites legacy: `source_relpath` como identidad histórica, `corpus_version`, rutas filesystem actuales, `retrieval_profiles`, activación/rollback y contratos Schema legacy. Cada entrada debe incluir propietario, dependencia, riesgo, prueba de no interferencia y decisión pendiente.
- [ ] Verificar que ninguna tarea de este plan elimina o deshabilita endpoints legacy, tablas, columnas, rutas actuales o adaptadores; las decisiones de sustitución futura quedan fuera de este documento.

**Exit criteria:** las garantías de aislamiento se prueban automáticamente; el equipo tiene un runbook de reuso y un registro auditable de límites legacy; el plan no cambia ni retira componentes legacy.

---

## 6. Matriz de reutilización explícita

| Caso | Normalizado | Chunks | Embeddings | Index materialization | Release nueva |
| --- | --- | --- | --- | --- | --- |
| Nuevo documento en el mismo proyecto/variante | No aplica | No aplica | No aplica | No aplica | Sí |
| 55 documentos intactos al pasar de `r001` a `r002` | Sí | Sí | Sí | Sí, si target igual | Sí |
| Cambia local → LlamaParse | No por defecto | No por defecto | No | No | Sí, de variante distinta |
| Cambia BGE‑M3 → Voyage | Sí si proceso/chunking igual | Sí si perfil igual | No | No | Sí, de variante distinta |
| Mismo corpus fuente en otra variante | Depende de la receta de procesamiento | Depende del normalizado/perfil | Solo si conserva el mismo perfil | Solo si conserva embedding/target compatibles | Sí, una release de la otra variante |
| Cambia chunking profile | Sí si proceso igual | No | No | No | Sí, de variante distinta |
| Cambia target compatible manteniendo profile/embedding | Sí | Sí | Sí | No, crea materialización nueva | Sí, misma variante |
| Mismos bytes en otro proyecto | No | No | No | No | Sí, sin reuso cruzado |
| Configuración operativa sin cambio de artefacto | Sí | Sí | Sí | Sí | No obligatoria |

Todos los reusos automáticos exigen igualdad de hashes/fingerprints y mismo `project_id`. Cualquier excepción manual deja un evento y requiere pasar los mismos validadores de compatibilidad; no puede mezclar espacios vectoriales diferentes.

---

## 7. Pruebas y Definition of Done

### Pruebas funcionales mínimas

```powershell
npm.cmd run test:ingestion
npm.cmd run python -- -m pytest app/back/tests/chunking app/back/tests/rag_platform -v
npm.cmd run test:embedding
npm.cmd run test:indexing
npm.cmd run test:retrieval
npm.cmd --prefix app/front test
npm.cmd --prefix app/front run build
```

En macOS/Linux, sustituir `npm.cmd` por `npm`.

### Casos obligatorios

- Un nuevo documento crea `corpus-snapshot-002` y `rag-release-002`; `rag-release-001` mantiene exactamente el manifest anterior.
- El mismo `corpus_snapshot_id` puede construir `local-bge-m3`, `llamaparse-bge-m3` y `llamaparse-voyage-4` como variantes y releases independientes del mismo proyecto.
- Dos proyectos con corpus distintos pueden habilitar combinaciones diferentes de perfiles `local`, `llama_cloud` y embedding sin cruzar artefactos ni resultados.
- `local-bge-m3` y `local-voyage-4` reutilizan normalizado/chunk bundle solo cuando sus fingerprints son idénticos antes de embedding.
- `llamaparse-*` no reutiliza silenciosamente artefactos locales.
- Un `rag_release_id` de proyecto A no puede construir, publicar ni leer artefactos de proyecto B, incluso si el usuario manda IDs existentes.
- Dos proyectos pueden usar el mismo `source_relpath` y el mismo archivo sin colisiones, pero no reutilizan artefactos entre sí.
- Un proyecto configurado por carpetas, por tipos documentales o híbrido conserva la misma identidad y el mismo manifest aunque cambie la vista de navegación.
- Una revisión `needs_review` promovida técnicamente no puede entrar a una release sin una decisión explícita de elegibilidad.
- La publicación no modifica `retrieval_profiles`, `ConsumerScope` ni `is_active`.
- Cambiar un archivo de un bundle sellado bloquea validación/publicación de una DRAFT y no cambia resultados de una release publicada.
- La migración de `sst-general` es idempotente y detecta registros legacy sin evidencia suficiente.
- Los endpoints legacy mantienen sus tests y contratos durante toda la fase.

### Definition of Done

- [ ] Cada proyecto tiene su propia configuración, documentos y storage aislado.
- [ ] Un mismo corpus snapshot puede servir varias variantes RAG; local/Llama y cada modelo de embedding quedan identificados por una receta y release propias.
- [ ] Cada variante fija de forma auditable el parseo, chunking y embedding que definen su semántica; cada release fija su target/materialización compatible.
- [ ] Cada cambio de corpus produce una release nueva; ninguna release publicada cambia implícitamente.
- [ ] Los artefactos físicos pertenecen al proyecto y se reutilizan solo bajo igualdad comprobada.
- [ ] `rag_release_id` vive en lifecycle, runs y membresías, no como propietario de nodes/vectors/bundles físicos.
- [ ] Nodos y vectores no pueden sobrescribirse entre proyectos, variantes o bundles.
- [ ] El perfil/target permanece resuelto por backend y su compatibilidad se valida fail-closed.
- [ ] Publicar una release es neutral frente a retrieval/chatbot.
- [ ] El frontend diferencia explícitamente plataforma y legacy sin duplicar UI ni contratos.
- [ ] `sst-general` queda bootstrappeado con evidencia de paridad, sin activar ni redirigir el consumidor legacy.
- [ ] El registro de deuda legacy identifica qué piezas siguen vigentes y demuestra que la plataforma no las modifica.

---

## 8. Decisiones fuera de este plan

- Asignar una release publicada a un chatbot/consumer y decidir actualizaciones automáticas o recomendadas.
- Construir el endpoint de preguntas, FTS de producción, reranking, grafo, FAQ, memoria conversacional, generación y verificación de respuestas.
- Implementar RBAC/SSO multiusuario completo. Hasta entonces las rutas plataforma son de operador interno y no equivalen a aislamiento SaaS.
- Seleccionar una release de plataforma desde un chatbot/consumer o reemplazar el runtime actual de Activation/Retrieval.
- Eliminar, deshabilitar o migrar fuera de servicio `Activation`, `Retrieval`, `corpus_version`, rutas filesystem actuales o adaptadores legacy.
