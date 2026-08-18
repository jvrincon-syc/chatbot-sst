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


class UnsupportedRuntimeChunkingRecipe(RagPlatformError):
    """La receta de chunking persistida no mapea a un runtime soportado.

    Fail-closed: una estrategia/configuración desconocida —o un fingerprint que no
    corresponde a su receta canónica— nunca se degrada silenciosamente a v1. El
    build se detiene con un error observable en vez de indexar con un perfil que
    no es el que la variante fijó.
    """

    code = "UNSUPPORTED_RUNTIME_CHUNKING_RECIPE"
    http_status = 409


class ChunkingProfileSeedConflict(RagPlatformError):
    """El ``chunking_profile_id`` ya existe con una receta distinta a la seedeada.

    Fail-closed: el seeder es idempotente solo para la receta exacta ya persistida
    (misma estrategia, configuración y fingerprint). Un ``chunking_profile_id`` que
    apunte a otra receta jamás se sobreescribe ni se ignora en silencio.
    """

    code = "CHUNKING_PROFILE_SEED_CONFLICT"
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


class MaterializationSealed(RagPlatformError):
    """Se intentó mutar una materialización de vectores ya ``SEALED``.

    Inmutabilidad (ADR-007 §3): una materialización sellada no cambia vectores,
    checksum ni conteos. Re-sellar con el mismo checksum es idempotente; cualquier
    intento de re-escritura con contenido distinto se rechaza fail-closed y nunca
    sobreescribe la fila sellada.
    """

    code = "MATERIALIZATION_SEALED"
    http_status = 409


class MaterializationValidationFailed(RagPlatformError):
    """La validación transaccional de una materialización falló (fail-closed).

    Owner de proyecto, pertenencia profile/target, dimensión, métrica, checksum o
    conteos parent/child/vector no cuadran. La materialización se marca ``FAILED``
    con un ``failure_code`` observable y nunca se sella a medias.
    """

    code = "MATERIALIZATION_VALIDATION_FAILED"
    http_status = 409


class CrossProjectLegacyFingerprintCollision(RagPlatformError):
    """Dos proyectos chocaron en la unicidad global legacy de ``bundle_fingerprint``.

    Fail-closed (ADR-007 §9): la unicidad global de ``chunk_bundles`` no se retira en
    Fase 4, así que dos proyectos con bytes idénticos colisionan. El adaptador traduce
    la ``UniqueViolation`` a este error y **nunca** reutiliza, renombra ni borra el
    artefacto del otro proyecto.
    """

    code = "CROSS_PROJECT_LEGACY_FINGERPRINT_COLLISION"
    http_status = 409


class NodeProjectMismatch(RagPlatformError):
    """Un nodo/artefacto derivado pertenece a un proyecto distinto al solicitado.

    Fail-closed: la propiedad física la impone la BD por FK compuesta; en la capa de
    aplicación este error protege la misma invariante antes de tocar la BD.
    """

    code = "NODE_PROJECT_MISMATCH"
    http_status = 409


class NoClassificationPolicyConfigured(RagPlatformError):
    """El snapshot de configuración del proyecto no resuelve una política de clasificación.

    Fail-closed: si la configuración versionada no permite derivar una política
    (p. ej. una taxonomía sin motor de reglas asociado), no se degrada a un
    clasificador por defecto; se exige configurar una política explícita.
    """

    code = "NO_CLASSIFICATION_POLICY_CONFIGURED"
    http_status = 409


# --------------------------------------------------------------------------- #
# Fase 5: releases, membresías y lifecycle                                    #
# --------------------------------------------------------------------------- #


class ReleaseProjectMismatch(RagPlatformError):
    """La variante y el corpus snapshot de una release no son del mismo proyecto.

    Fail-closed: una release solo puede combinar artefactos del proyecto que la
    posee; una variante o un snapshot de otro proyecto se rechaza sin degradar.
    """

    code = "RELEASE_PROJECT_MISMATCH"
    http_status = 409


class InvalidReleaseTransition(RagPlatformError):
    """Se intentó una transición de estado no permitida por el lifecycle de release.

    Fail-closed: el lifecycle ``DRAFT → VALIDATED → PUBLISHED → RETIRED`` (más
    ``FAILED``) es estricto; una transición fuera de ese grafo se rechaza y jamás
    se aplica en sitio.
    """

    code = "INVALID_RELEASE_TRANSITION"
    http_status = 409


class ReleaseNotComplete(RagPlatformError):
    """Se intentó validar una release a la que le falta la membresía de una revisión.

    Fail-closed: una release solo es válida si cada revisión del corpus snapshot
    tiene su membresía con artefactos concretos; una revisión sin construir la
    invalida.
    """

    code = "RELEASE_NOT_COMPLETE"
    http_status = 409


class ReleaseBlockedRevision(RagPlatformError):
    """El corpus snapshot de la release contiene una revisión ``blocked`` sin waiver.

    Fail-closed: una revisión con elegibilidad ``blocked`` impide crear o validar
    la release salvo excepción ``operator_waiver`` explícita (actor, motivo, fecha
    y snapshot de política que la autorizó).
    """

    code = "RELEASE_BLOCKED_REVISION"
    http_status = 409


class ReleaseManifestFrozen(RagPlatformError):
    """Se intentó mutar una release cuyo ``release_manifest_hash`` ya está congelado.

    Fail-closed: una release ``VALIDATED`` no se edita en sitio; un cambio de
    corpus o receta obliga a crear un nuevo snapshot/membresía antes de revalidar.
    """

    code = "RELEASE_MANIFEST_FROZEN"
    http_status = 409


class RagVariantNotFound(RagPlatformError):
    """Se referenció una variante que no existe."""

    code = "RAG_VARIANT_NOT_FOUND"
    http_status = 404


class CorpusSnapshotNotFound(RagPlatformError):
    """Se referenció un corpus snapshot que no existe."""

    code = "CORPUS_SNAPSHOT_NOT_FOUND"
    http_status = 404


class RagReleaseNotFound(RagPlatformError):
    """Se referenció una release que no existe."""

    code = "RAG_RELEASE_NOT_FOUND"
    http_status = 404


# --------------------------------------------------------------------------- #
# Fase 7: matriz de variantes                                                 #
# --------------------------------------------------------------------------- #


class InvalidVariantMatrixCell(RagPlatformError):
    """El ``cell_id`` de la matriz de variantes está malformado.

    Fail-closed: un ``cell_id`` que no respeta el formato
    ``processing|chunking|embedding|binding|configuration_version`` no se
    interpreta de forma laxa; se rechaza antes de construir nada.
    """

    code = "INVALID_VARIANT_MATRIX_CELL"
    http_status = 422


class StaleVariantMatrixCell(RagPlatformError):
    """La celda de la matriz de variantes ya no refleja la configuración vigente.

    Fail-closed contra TOCTOU: si la configuración del proyecto avanzó entre el
    ``GET`` de la matriz y el ``POST`` de la variante, la celda pinneada a una
    versión anterior deja de ser construible y se rechaza; el operador debe
    releer la matriz vigente. Nunca se re-resuelve la versión "actual" en
    silencio para forzar el éxito.
    """

    code = "STALE_VARIANT_MATRIX_CELL"
    http_status = 409
