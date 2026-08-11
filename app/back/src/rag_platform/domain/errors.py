"""Errores de dominio de la plataforma RAG multi-proyecto (Fase 1).

Cada error lleva un ``code`` público estable y un ``http_status`` sugerido para
que la capa API traduzca sin re-derivar una taxonomía desde las clases. La
política es *fail-closed*: ante evidencia insuficiente o incompatibilidad, se
lanza un error de dominio y nunca se degrada a la ruta legacy.
"""

from __future__ import annotations


class RagPlatformError(Exception):
    """Base de los errores de dominio de plataforma con código público estable."""

    code = "RAG_PLATFORM_ERROR"
    http_status = 400


class ProjectAlreadyExists(RagPlatformError):
    """Ya existe un proyecto con el mismo ``project_id`` (slug técnico)."""

    code = "PROJECT_ALREADY_EXISTS"
    http_status = 409


class ProjectNotFound(RagPlatformError):
    """El proyecto referenciado no está registrado."""

    code = "PROJECT_NOT_FOUND"
    http_status = 404


class UnknownDocumentTypeTemplate(RagPlatformError):
    """La plantilla de tipos documentales solicitada no existe."""

    code = "UNKNOWN_DOCUMENT_TYPE_TEMPLATE"
    http_status = 422


class ProcessingProfileNotFound(RagPlatformError):
    """El perfil de procesamiento referenciado por la receta no existe."""

    code = "PROCESSING_PROFILE_NOT_FOUND"
    http_status = 404


class ChunkingProfileNotFound(RagPlatformError):
    """El perfil de chunking referenciado por la receta no existe."""

    code = "CHUNKING_PROFILE_NOT_FOUND"
    http_status = 404


class ProfileProjectMismatch(RagPlatformError):
    """Un perfil pertenece a otro proyecto que el de la receta."""

    code = "PROFILE_PROJECT_MISMATCH"
    http_status = 409


class IncompatibleTargetBinding(RagPlatformError):
    """El ``target_binding_key`` no es compatible con el perfil de embedding."""

    code = "INCOMPATIBLE_TARGET_BINDING"
    http_status = 409


class UnverifiableRecipeRevision(RagPlatformError):
    """La receta usa una revisión no verificable y falta attestation explícita."""

    code = "UNVERIFIABLE_RECIPE_REVISION"
    http_status = 409


class DuplicateVariantRecipe(RagPlatformError):
    """Ya existe una variante activa con el mismo ``semantic_recipe_fingerprint``."""

    code = "DUPLICATE_VARIANT_RECIPE"
    http_status = 409


class PlatformAccessDenied(RagPlatformError):
    """El actor no es un operador autorizado para la operación de plataforma."""

    code = "PLATFORM_ACCESS_DENIED"
    http_status = 403


class UnsafeArtifactPath(RagPlatformError):
    """La ruta de artefacto sale de la raíz del proyecto o es absoluta."""

    code = "UNSAFE_ARTIFACT_PATH"
    http_status = 400


class SourceDocumentRevisionNotFound(RagPlatformError):
    """La revisión documental referenciada no está registrada."""

    code = "SOURCE_DOCUMENT_REVISION_NOT_FOUND"
    http_status = 404


class RevisionProjectMismatch(RagPlatformError):
    """Una revisión pertenece a un proyecto distinto al del snapshot."""

    code = "REVISION_PROJECT_MISMATCH"
    http_status = 409


class NormalizedArtifactNotBuilt(RagPlatformError):
    """No existe un normalizado para la identidad exacta y no hay build resuelto."""

    code = "NORMALIZED_ARTIFACT_NOT_BUILT"
    http_status = 409


class RevisionNotReleaseEligible(RagPlatformError):
    """Una revisión ``needs_review`` entró a un snapshot sin decisión válida.

    Fail-closed: sin ``approved_after_review`` u ``operator_waiver`` explícito, o
    con ``blocked``, la revisión no puede formar parte de un corpus snapshot.
    """

    code = "REVISION_NOT_RELEASE_ELIGIBLE"
    http_status = 409


class EmptyCorpusSnapshot(RagPlatformError):
    """Un corpus snapshot debe contener al menos una revisión."""

    code = "EMPTY_CORPUS_SNAPSHOT"
    http_status = 422


class DuplicateRevisionInSnapshot(RagPlatformError):
    """La misma revisión se incluyó dos veces en un corpus snapshot."""

    code = "DUPLICATE_REVISION_IN_SNAPSHOT"
    http_status = 422


class DocumentTypeNotPermitted(RagPlatformError):
    """El ``document_type`` clasificado no está en el catálogo del proyecto.

    Fail-closed: la plataforma no acepta un tipo documental que la configuración
    versionada del proyecto no declara. El ``Literal`` legacy solo vive en el
    adaptador SST; la identidad de plataforma valida contra el catálogo real.
    """

    code = "DOCUMENT_TYPE_NOT_PERMITTED"
    http_status = 422


class SealedBundleConflict(RagPlatformError):
    """Se intentó sellar contenido distinto sobre un ``chunk_bundle_id`` ya sellado.

    Fail-closed e inmutabilidad (invariante §3): un artefacto sellado es
    append-only/content-addressed. Re-sellar bytes idénticos es idempotente; sellar
    bytes distintos bajo la misma identidad se rechaza y jamás sobreescribe.
    """

    code = "SEALED_BUNDLE_CONFLICT"
    http_status = 409


class CrossProjectReuseForbidden(RagPlatformError):
    """Se intentó reutilizar un artefacto de otro proyecto (aunque los bytes coincidan).

    El reuso automático solo ocurre dentro del mismo proyecto y por identidad
    exacta (invariante §4). Ni siquiera ``operator_approved`` puede salvar una
    incompatibilidad de proyecto (ni de dimensión o métrica en fases de embedding).
    """

    code = "CROSS_PROJECT_REUSE_FORBIDDEN"
    http_status = 409


class BuildStepNotFound(RagPlatformError):
    """Se intentó cerrar un paso de build (``rag_build_steps``) que no existe.

    Fail-closed: un ``complete_step`` sobre un ``step_id`` desconocido produce un
    error de dominio controlado en vez de propagar un ``TypeError``/``KeyError``
    crudo con detalle de implementación.
    """

    code = "BUILD_STEP_NOT_FOUND"
    http_status = 404


class NoClassificationPolicyConfigured(RagPlatformError):
    """El snapshot de configuración del proyecto no resuelve una política de clasificación.

    Fail-closed: si la configuración versionada no permite derivar una política
    (p. ej. una taxonomía sin motor de reglas asociado), no se degrada a un
    clasificador por defecto; se exige configurar una política explícita.
    """

    code = "NO_CLASSIFICATION_POLICY_CONFIGURED"
    http_status = 409
