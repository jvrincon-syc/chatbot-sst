"""Modelos de dominio de la plataforma RAG multi-proyecto (Fase 1).

Estos modelos son el contrato de propiedad y de receta que ADR-006 separa de la
lane legacy bundle-first:

- ``RagProject`` es el límite de propiedad y almacenamiento. Su ``project_id`` es
  un slug técnico estable (ver ADR-006 §2.1); nunca guarda credenciales.
- ``DocumentProcessingProfile`` y ``ChunkingProfile`` persisten proveedor, motor,
  revisión observada y **configuración sanitizada** con su fingerprint inmutable.
  Las credenciales viven solo en ``secrets.env``/entorno, jamás en estos modelos.
- ``RagVariant`` fija una receta semántica inmutable mediante
  ``semantic_recipe_fingerprint``; cambiar proveedor/motor/revisión/configuración
  de la receta crea otra variante (no se edita in situ).

Los contratos con validación de campos son ``StrictModel`` (Pydantic 2,
``extra="forbid"``). Las identidades tipadas reutilizan ``PlatformId`` del módulo
``rag_platform.domain.identity``; ``embedding_profile_id`` e
``indexing_target_id`` quedan como ``str`` porque referencian recursos globales
verificados por el servidor (ADR-005/ADR-006).
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
import hashlib
import json
import re
from typing import Annotated, Any, Mapping, Sequence

from pydantic import AfterValidator, Field

from ingestion.schemas.common import StrictModel
from rag_platform.domain.identity import IdentityKind, PlatformId, _require


def _kind(expected: IdentityKind):
    """Construye un validador Pydantic que exige un ``PlatformId`` de ``expected``."""

    def _check(value: PlatformId) -> PlatformId:
        _require(value, expected)
        return value

    return _check


#: Identidades tipadas usadas por los modelos de plataforma.
ProjectId = Annotated[PlatformId, AfterValidator(_kind(IdentityKind.PROJECT))]
ProcessingProfileId = Annotated[
    PlatformId, AfterValidator(_kind(IdentityKind.PROCESSING_PROFILE))
]
ChunkingProfileId = Annotated[
    PlatformId, AfterValidator(_kind(IdentityKind.CHUNKING_PROFILE))
]
RagVariantId = Annotated[PlatformId, AfterValidator(_kind(IdentityKind.RAG_VARIANT))]
SourceDocumentId = Annotated[
    PlatformId, AfterValidator(_kind(IdentityKind.SOURCE_DOCUMENT))
]
SourceDocumentRevisionId = Annotated[
    PlatformId, AfterValidator(_kind(IdentityKind.SOURCE_DOCUMENT_REVISION))
]
CorpusSnapshotId = Annotated[
    PlatformId, AfterValidator(_kind(IdentityKind.CORPUS_SNAPSHOT))
]

#: Marcadores de claves que jamás entran a un fingerprint ni a un modelo.
_SECRET_MARKERS = ("secret", "token", "password", "key", "credential")
#: Claves de root de storage que no son parte de la semántica de la receta.
_ROOT_KEYS = frozenset({"docs_raw", "docs_normalized", "root", "roots", "base_path"})


class ProjectLifecycleState(str, Enum):
    """Estado de un proyecto en el catálogo de plataforma."""

    ACTIVE = "active"
    ARCHIVED = "archived"


class ProfileVerificationStatus(str, Enum):
    """Verificabilidad de una receta de procesamiento o chunking.

    ``VERIFIED`` significa que la revisión del motor fue observada y probada;
    ``UNVERIFIABLE`` obliga a una attestation explícita antes de fijar una
    variante (política fail-closed de ADR-006).
    """

    VERIFIED = "verified"
    UNVERIFIABLE = "unverifiable"


class RagVariantState(str, Enum):
    """Estado de una variante RAG. La unicidad de receta aplica mientras activa."""

    ACTIVE = "active"
    RETIRED = "retired"


class ProcessingOrigin(str, Enum):
    """Origen del motor de procesamiento documental permitido por el proyecto."""

    LOCAL = "local"
    LLAMA_CLOUD = "llama_cloud"


class DocumentTypeTemplate(str, Enum):
    """Plantillas seleccionables de taxonomía documental.

    ``GENERIC`` es neutral y es la única preseleccionable por defecto; ``SST`` es
    la plantilla versionada que ``sst-general`` toma como base (ADR-006, plan
    §Fase 1). Un proyecto nuevo no preselecciona ``SST``.
    """

    GENERIC = "generic"
    SST = "sst"


class CorpusOrganizationPolicy(str, Enum):
    """Política de organización/navegación del corpus de un proyecto.

    Define la vista de ingreso y los relpaths lógicos; **nunca** la identidad del
    documento ni la ubicación canónica de artefactos sellados (plan §Fase 1).
    """

    SST_LEGACY_V1 = "sst-legacy-v1"
    SOURCE_FOLDERS_V1 = "source-folders-v1"
    DOCUMENT_TYPES_V1 = "document-types-v1"
    HYBRID_V1 = "hybrid-v1"


class ProjectDocumentType(StrictModel):
    """Un tipo documental permitido por el catálogo del proyecto.

    Attributes:
        code: Identificador estable dentro del proyecto (slug).
        display_name: Nombre legible mostrado en la UI.
        template: Plantilla de la que proviene el tipo.
    """

    code: str = Field(min_length=1, max_length=128)
    display_name: str = Field(min_length=1, max_length=256)
    template: DocumentTypeTemplate


class ProjectEmbeddingProfile(StrictModel):
    """Perfil de embedding habilitado para un proyecto.

    ``embedding_profile_id`` referencia un recurso global (ADR-005); el proyecto
    solo declara que puede usarlo, no lo redefine.
    """

    embedding_profile_id: str = Field(min_length=1)
    enabled: bool = True


class ProjectIndexingTargetBinding(StrictModel):
    """Allowlist backend de una clave lógica hacia un target global compatible.

    El cliente elige un ``binding_key``; nunca un ``indexing_target_id`` ni una
    tabla vectorial (invariante §1/§7 del plan). La compatibilidad con el perfil
    de embedding se valida en el servidor de forma fail-closed.
    """

    binding_key: str = Field(min_length=1, max_length=128)
    indexing_target_id: str = Field(min_length=1)
    embedding_profile_id: str = Field(min_length=1)


class ProjectStorageRoots(StrictModel):
    """Raíces de almacenamiento aisladas por proyecto.

    Todas cuelgan de ``data/projects/{project_id}/`` y no se intersectan con las
    de otro proyecto. Son relpaths POSIX validados por el resolver de infra.
    """

    project_id: ProjectId
    raw: str
    normalized: str
    chunks: str
    embeddings: str
    manifests: str


class ProjectConfiguration(StrictModel):
    """Configuración editable y **versionada** de un proyecto.

    Cada edición materializa una versión nueva (``version`` monótona) para poder
    congelar la configuración exacta que usó una receta o release.
    """

    version: int = Field(ge=1)
    document_types: tuple[ProjectDocumentType, ...] = Field(default_factory=tuple)
    embedding_profiles: tuple[ProjectEmbeddingProfile, ...] = Field(
        default_factory=tuple
    )
    target_bindings: tuple[ProjectIndexingTargetBinding, ...] = Field(
        default_factory=tuple
    )
    corpus_organization_policy: CorpusOrganizationPolicy
    created_at: datetime


class RagProject(StrictModel):
    """Proyecto: límite de propiedad, almacenamiento y configuración aislados.

    ``project_id`` es un slug técnico único e inmutable una vez que el proyecto
    tiene documentos; ``display_name`` sí es editable (ADR-006 §2.1). El modelo
    nunca contiene credenciales.
    """

    project_id: ProjectId
    display_name: str = Field(min_length=1, max_length=256)
    state: ProjectLifecycleState = ProjectLifecycleState.ACTIVE
    storage_roots: ProjectStorageRoots
    configuration: ProjectConfiguration
    created_at: datetime


class DocumentProcessingProfile(StrictModel):
    """Receta de procesamiento (parseo/normalización) con fingerprint inmutable.

    Persiste proveedor, motor, revisión observada, origen y **configuración
    sanitizada**; nunca credenciales (plan §2.2, §4.3). ``fingerprint`` se computa
    de forma determinista sobre la configuración sanitizada y las referencias.
    """

    processing_profile_id: ProcessingProfileId
    project_id: ProjectId
    provider: str = Field(min_length=1)
    engine: str = Field(min_length=1)
    observed_revision: str = Field(min_length=1)
    origin: ProcessingOrigin
    sanitized_config: Mapping[str, Any] = Field(default_factory=dict)
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: ProfileVerificationStatus
    created_at: datetime


class ChunkingProfile(StrictModel):
    """Receta de chunking con fingerprint inmutable.

    Un cambio de chunking reindexa sin reparsear (AGENTS §6) y crea una variante
    distinta, no un normalizado nuevo.
    """

    chunking_profile_id: ChunkingProfileId
    project_id: ProjectId
    strategy: str = Field(min_length=1)
    sanitized_config: Mapping[str, Any] = Field(default_factory=dict)
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: ProfileVerificationStatus
    created_at: datetime


class RagVariant(StrictModel):
    """Receta semántica inmutable dentro de un proyecto (ADR-006 §2.3).

    ``semantic_recipe_fingerprint`` identifica la receta y es único por proyecto
    mientras la variante está ``ACTIVE``. El ``indexing_target`` **no** forma
    parte de la receta: cambiar de target compatible crea release, no variante.
    """

    rag_variant_id: RagVariantId
    project_id: ProjectId
    processing_profile_id: ProcessingProfileId
    chunking_profile_id: ChunkingProfileId
    embedding_profile_id: str = Field(min_length=1)
    semantic_recipe_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    state: RagVariantState = RagVariantState.ACTIVE
    created_at: datetime


def _sanitize(value: Any) -> Any:
    """Devuelve una copia portable de ``value`` sin secretos ni claves de root.

    Réplica del patrón de ``ingestion/fingerprint.py``: ordena claves y excluye
    marcadores de secreto y claves de root de storage, de modo que una credencial
    presente en la configuración nunca altera el fingerprint semántico.
    """

    if isinstance(value, Mapping):
        return {
            key: _sanitize(child)
            for key, child in sorted(value.items())
            if key not in _ROOT_KEYS and not _is_secret_key(key)
        }
    if isinstance(value, (list, tuple)):
        return [_sanitize(child) for child in value]
    return value


def _is_secret_key(key: str) -> bool:
    folded = str(key).casefold()
    return any(marker in folded for marker in _SECRET_MARKERS)


def compute_semantic_recipe_fingerprint(
    *,
    processing_provider: str,
    processing_engine: str,
    processing_revision: str,
    processing_config: Mapping[str, Any],
    chunking_strategy: str,
    chunking_config: Mapping[str, Any],
    embedding_profile_id: str,
) -> str:
    """Computa el fingerprint determinista de una receta semántica.

    El resultado depende solo de las referencias y de la configuración
    **sanitizada**: cambiar una credencial no lo altera; cambiar proveedor,
    motor, revisión, estrategia, configuración semántica o perfil de embedding sí
    produce un fingerprint distinto (ADR-006 §2.3).

    Args:
        processing_provider: Proveedor de parseo/normalización.
        processing_engine: Motor concreto del proveedor.
        processing_revision: Revisión observada y probada del motor.
        processing_config: Configuración de procesamiento (se sanitiza).
        chunking_strategy: Estrategia de chunking.
        chunking_config: Configuración de chunking (se sanitiza).
        embedding_profile_id: Perfil de embedding global de la variante.

    Returns:
        Digest hex sha256 de 64 caracteres.
    """

    payload = {
        "processing": {
            "provider": processing_provider,
            "engine": processing_engine,
            "revision": processing_revision,
            "config": _sanitize(processing_config),
        },
        "chunking": {
            "strategy": chunking_strategy,
            "config": _sanitize(chunking_config),
        },
        "embedding_profile_id": embedding_profile_id,
    }
    serialized = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# Fase 2: revisiones documentales, normalizados y corpus snapshots            #
# --------------------------------------------------------------------------- #


class EligibilityDecision(str, Enum):
    """Decisión versionada de elegibilidad de una revisión para un snapshot.

    Separa la promoción técnica de la elegibilidad de release (ADR-006 §3). Una
    revisión ``needs_review`` exige una decisión explícita (``APPROVED_AFTER_REVIEW``
    u ``OPERATOR_WAIVER``) antes de entrar a un corpus snapshot; ``BLOCKED`` la
    rechaza. ``NOT_REQUIRED`` aplica a revisiones ya procesadas sin ``needs_review``.
    """

    NOT_REQUIRED = "not_required"
    APPROVED_AFTER_REVIEW = "approved_after_review"
    OPERATOR_WAIVER = "operator_waiver"
    BLOCKED = "blocked"


class RevisionReviewState(str, Enum):
    """Estado de revisión técnica de una ``SourceDocumentRevision``.

    Refleja el ``processing_status`` legacy relevante para elegibilidad: una
    revisión ``NEEDS_REVIEW`` no es releaseable solo por estar promovida.
    """

    PROCESSED = "processed"
    NEEDS_REVIEW = "needs_review"


class SourceDocument(StrictModel):
    """Documento lógico dentro de un proyecto.

    Su identidad es ``project_id + logical_document_id``; ``source_relpath`` es
    solo un localizador versionado que puede cambiar sin colisionar entre
    proyectos (ADR-006 §2.2).
    """

    logical_document_id: SourceDocumentId
    project_id: ProjectId
    source_relpath: str = Field(min_length=1)
    created_at: datetime


class SourceDocumentRevision(StrictModel):
    """Revisión inmutable de un documento lógico.

    Cada cambio de bytes crea una revisión nueva (``raw_content_hash`` distinto);
    la anterior nunca se sobreescribe. Conserva trazabilidad de carga sin filtrar
    contenido documental.
    """

    source_document_revision_id: SourceDocumentRevisionId
    logical_document_id: SourceDocumentId
    project_id: ProjectId
    source_relpath: str = Field(min_length=1)
    raw_content_hash: str = Field(min_length=1)
    file_size: int = Field(ge=0)
    uploaded_by: str = Field(min_length=1)
    uploaded_at: datetime
    review_state: RevisionReviewState = RevisionReviewState.PROCESSED


class NormalizedDocumentArtifact(StrictModel):
    """Artefacto normalizado ligado a una revisión y una receta de procesamiento.

    Su identidad exacta es ``project_id + source_document_revision_id +
    processing_profile_fingerprint`` (plan §4.4). ``artifact_relpath`` es ``None``
    hasta que un build real produzca el artefacto (esta fase solo lo resuelve).
    """

    project_id: ProjectId
    source_document_revision_id: SourceDocumentRevisionId
    processing_profile_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    schema_version: str = Field(min_length=1)
    artifact_relpath: str | None = None


class CorpusSnapshotDocument(StrictModel):
    """Membresía de una revisión en un corpus snapshot.

    Guarda el orden determinista y la ``eligibility_decision`` de la revisión, de
    modo que un ``needs_review`` no se hace releaseable solo por promoción técnica.
    """

    ordinal: int = Field(ge=0)
    source_document_revision_id: SourceDocumentRevisionId
    eligibility_decision: EligibilityDecision


class CorpusSnapshot(StrictModel):
    """Lista ordenada e inmutable de revisiones de un proyecto (ADR-006 §2.4).

    ``manifest_hash`` es determinista y reconstruible solo con las filas: mismo
    conjunto ordenado de revisiones y decisiones produce el mismo hash. Agregar,
    quitar o reemplazar una revisión genera otro snapshot.
    """

    corpus_snapshot_id: CorpusSnapshotId
    project_id: ProjectId
    documents: tuple[CorpusSnapshotDocument, ...]
    document_count: int = Field(ge=0)
    manifest_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    created_at: datetime


def compute_corpus_manifest_hash(
    *,
    project_id: str,
    documents: Sequence[CorpusSnapshotDocument],
) -> str:
    """Computa el ``manifest_hash`` determinista de un corpus snapshot.

    Depende solo del proyecto y de la lista ordenada de ``(ordinal, revision_id,
    eligibility_decision)``; reconstruible únicamente con las filas persistidas.

    Args:
        project_id: Valor textual del ``project_id`` propietario.
        documents: Membresías en su orden final.

    Returns:
        Digest hex sha256 de 64 caracteres.
    """

    payload = {
        "project_id": project_id,
        "documents": [
            {
                "ordinal": doc.ordinal,
                "revision_id": doc.source_document_revision_id.value,
                "eligibility": doc.eligibility_decision.value,
            }
            for doc in documents
        ],
    }
    serialized = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
