# Contrato de identidad y reutilización — plataforma RAG

Autoridad de este documento: describe el contrato tipado implementado en
`app/back/src/rag_platform/`. La decisión de fondo vive en
[ADR-006](../adr/ADR-006-rag-platform-project-variant-release.md).

## Identidades (no intercambiables)

Cada identidad es un `PlatformId` con prefijo validado. Confundir clases falla
cerrado con `InvalidIdentity`.

| Clase | Prefijo | Propietario / significado |
| --- | --- | --- |
| `PROJECT` | `proj_` | límite de propiedad, storage y configuración |
| `SOURCE_DOCUMENT` | `sdoc_` | documento lógico dentro de un proyecto |
| `SOURCE_DOCUMENT_REVISION` | `srev_` | revisión inmutable (cambio de bytes del raw) |
| `PROCESSING_PROFILE` | `pp_` | receta de parseo/normalización (proveedor+motor+config) |
| `CHUNKING_PROFILE` | `cp_` | receta de chunking |
| `RAG_VARIANT` | `ragv_` | receta semántica inmutable (proceso+chunking+embedding) |
| `CORPUS_SNAPSHOT` | `corpus_` | lista ordenada e inmutable de revisiones fuente |
| `RAG_RELEASE` | `ragr_` | snapshot inmutable de una variante sobre un corpus |

`embedding_profile_id` e `indexing_target_id` permanecen como `str` porque
apuntan a recursos globales ya verificados por el servidor (ADR-005); el cliente
nunca envía una tabla vectorial ni un target directo.

## Regla de creación

- documento agregado/retirado/reemplazado ⇒ **corpus snapshot nuevo** ⇒ release
  nueva. No crea variante.
- cambio semántico (parseo/normalización/chunking/embedding/perfil de
  recuperación) ⇒ **variante nueva** + release nueva.
- cambio de target compatible ⇒ **release nueva**, misma variante.
- cambio solo operacional (concurrencia/batch/timeout) ⇒ no crea variante ni
  release; se audita en el run.

## Cuatro semánticas separadas

Ninguna implica otra:

| Concepto | Qué confirma | Qué NO hace |
| --- | --- | --- |
| `promoted` | promoción técnica del normalizado terminó | no hace releaseable un `needs_review` |
| `release_eligible` | la revisión puede entrar a un snapshot | no es promoción ni publicación |
| `PUBLISHED` | el catálogo de plataforma acepta la release | no activa retrieval ni cambia el consumidor legacy |
| activación legacy | cambia qué consulta el chatbot (`is_active`) | no se toca en este plan |

Una revisión `needs_review` requiere una decisión de elegibilidad versionada
(`approved_after_review`, `operator_waiver`, `blocked`) antes de entrar a un
corpus snapshot. La promoción legacy conserva su comportamiento actual.

## Reutilización (resumen operativo)

Los artefactos físicos pertenecen al proyecto; una release los **referencia**
por membresía, no los duplica. El reuso automático solo ocurre dentro del mismo
proyecto y solo por identidad exacta (hash/fingerprint). El reuso entre
proyectos está prohibido por defecto aunque los bytes coincidan. La matriz
completa está en la sección 6 del plan.

## Identidad de plataforma en artefactos Schema 2.0 (Fase 2)

`MetadataArtifact.platform_identity` (opcional, `PlatformDocumentIdentity`) liga
un normalizado nuevo a `project_id + source_document_id +
source_document_revision_id + processing_profile_id + processing_profile_fingerprint`,
sin depender solo de `source_relpath`. Es **aditivo**: los artefactos legacy SST
lo dejan en `None` y validan sin cambios. Los IDs se validan por prefijo tipado
en `ingestion`; la autoridad de identidad sigue siendo
`rag_platform.domain.identity` (no se importa en `ingestion` para no acoplar la
lane legacy al módulo nuevo).

## Clasificación documental por proyecto (Fase 2)

El `document_type` de plataforma se resuelve **fail-closed** contra el catálogo
versionado del proyecto (`resolve_document_type` → `DocumentTypeNotPermitted` si
el código no está permitido). El `Literal` legacy de tipos queda confinado al
adaptador SST (`SstClassificationPolicy`), que **envuelve**
`ingestion.classification.rules.classify_document` sin reimplementar reglas y
reproduce las decisiones SST exactas. La aplicación solo conoce el puerto
`ClassificationPolicy`, de modo que otro proyecto puede aportar su política sin
tocar el dominio. La plantilla SST del catálogo se alineó con las etiquetas que
el clasificador legacy emite, para que una clasificación SST real no se rechace.

## Compatibilidad legacy

`corpus_version`, `stable_document_id(source_relpath)`, `retrieval_profiles`,
activación/rollback y los contratos Schema 2.0 legacy permanecen intactos.
`corpus_version` **no** puede usarse como sustituto de ninguna identidad de
plataforma en contratos nuevos.
