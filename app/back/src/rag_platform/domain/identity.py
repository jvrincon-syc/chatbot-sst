"""Contratos de identidad de la plataforma RAG multi-proyecto (Fase 0).

Este módulo define las identidades nuevas y su regla central: ``project_id``,
``rag_variant_id``, ``corpus_snapshot_id`` y ``rag_release_id`` **no son
intercambiables**. Cada identidad lleva un prefijo tipado y se valida al
construirse, de modo que confundir una variante con una release falla cerrado en
runtime y no solo en el chequeo estático.

Regla de negocio (ADR-006):
    - Un cambio de corpus (documento agregado/retirado/reemplazado) crea un
      ``corpus_snapshot_id`` nuevo y, por tanto, una release nueva; nunca una
      variante nueva.
    - Un cambio semántico (parseo/normalización/chunking/embedding/perfil de
      recuperación) crea un ``rag_variant_id`` nuevo.
    - La identidad nueva de un documento **no depende solo de
      ``source_relpath``**: incluye proyecto, revisión y fingerprint de receta.
    - ``corpus_version`` es compatibilidad legacy y no puede sustituir a ninguna
      de estas identidades.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import re


#: Unit separator that fences each namespaced field so distinct tuples can never
#: alias by concatenation (same convention as ``ingestion.paths``).
_FIELD_SEP = "\x1f"
#: Prefix of every physical (project-namespaced) indexing node id.
_PHYSICAL_NODE_PREFIX = "pnode_"
#: Hex length kept from the digest; matches ``platform_document_id`` (128 bits).
_PHYSICAL_NODE_HEX_LEN = 32


def physical_node_id(
    *, project_id: str, source_chunk_bundle_id: str, source_chunk_id: str
) -> str:
    """Return the project-namespaced physical id of one indexing node.

    Mirrors :func:`ingestion.paths.platform_document_id`: the identity is the
    sha256 of a canonical, field-fenced representation that includes the owning
    project, so two projects that share a ``source_chunk_id`` (evidence) never
    collide on ``node_id`` (ADR-007 §2). The source chunk id is preserved
    separately as weak evidence; it is not the physical identity.

    Args:
        project_id: Owning project id value (``proj_...``); namespaces the node.
        source_chunk_bundle_id: Chunk bundle the node is adapted from.
        source_chunk_id: Source chunk id (parent or child) that seeds the node.

    Returns:
        A deterministic ``pnode_`` id, stable across runs and processes.

    Raises:
        ValueError: If any component is empty (fail-closed; an empty component
            would let two different tuples hash to the same fenced payload).
    """

    if not project_id or not source_chunk_bundle_id or not source_chunk_id:
        raise ValueError("physical_node_id requires non-empty components")
    payload = _FIELD_SEP.join((project_id, source_chunk_bundle_id, source_chunk_id))
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return _PHYSICAL_NODE_PREFIX + digest[:_PHYSICAL_NODE_HEX_LEN]


class IdentityKind(str, Enum):
    """Prefijos canónicos de cada identidad de plataforma.

    El valor del enum es el prefijo real que llevan los IDs persistidos. Se
    centraliza aquí para no repetir literales mágicos en repositorios ni
    servicios.
    """

    PROJECT = "proj"
    RAG_VARIANT = "ragv"
    CORPUS_SNAPSHOT = "corpus"
    RAG_RELEASE = "ragr"
    SOURCE_DOCUMENT = "sdoc"
    SOURCE_DOCUMENT_REVISION = "srev"
    PROCESSING_PROFILE = "pp"
    CHUNKING_PROFILE = "cp"


#: Cuerpo permitido tras el prefijo: hex/alfanumérico y guiones, sin espacios.
_ID_BODY = re.compile(r"^[a-z0-9][a-z0-9-]{0,127}$")


class InvalidIdentity(ValueError):
    """Se lanza cuando un ID no respeta el prefijo o el formato esperado.

    Es un error de dominio: el llamador entregó una identidad de otra clase o
    malformada. No se degrada silenciosamente a la ruta legacy.
    """


@dataclass(frozen=True, slots=True)
class PlatformId:
    """Identidad de plataforma tipada por su ``kind``.

    Dos ``PlatformId`` de ``kind`` distinto nunca son iguales aunque compartan
    cuerpo, lo que hace imposible pasar una variante donde se espera una release.

    Attributes:
        kind: Clase de identidad (proyecto, variante, snapshot, release, ...).
        value: Representación textual completa, incluido el prefijo.
    """

    kind: IdentityKind
    value: str

    def __post_init__(self) -> None:
        prefix = f"{self.kind.value}_"
        if not self.value.startswith(prefix):
            raise InvalidIdentity(
                f"{self.kind.name} id must start with {prefix!r}: {self.value!r}"
            )
        body = self.value[len(prefix) :]
        if not _ID_BODY.match(body):
            raise InvalidIdentity(
                f"{self.kind.name} id body is malformed: {self.value!r}"
            )

    @classmethod
    def parse(cls, kind: IdentityKind, value: str) -> "PlatformId":
        """Construye un ``PlatformId`` de la clase esperada o falla cerrado.

        Args:
            kind: Clase de identidad requerida por el consumidor.
            value: Texto del ID recibido.

        Returns:
            El ``PlatformId`` validado.

        Raises:
            InvalidIdentity: Si el prefijo no corresponde a ``kind`` o el cuerpo
                es inválido.
        """

        return cls(kind=kind, value=value)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class ProjectDocumentContext:
    """Contexto de un documento dentro de su proyecto (identidad física upstream).

    Reemplaza la identidad legacy basada solo en ``source_relpath``. La ruta se
    conserva únicamente como localizador versionado en las capas de
    persistencia; la identidad la fijan proyecto, revisión y perfil de proceso.
    """

    project_id: PlatformId
    source_document_id: PlatformId
    source_document_revision_id: PlatformId
    processing_profile_id: PlatformId

    def __post_init__(self) -> None:
        _require(self.project_id, IdentityKind.PROJECT)
        _require(self.source_document_id, IdentityKind.SOURCE_DOCUMENT)
        _require(self.source_document_revision_id, IdentityKind.SOURCE_DOCUMENT_REVISION)
        _require(self.processing_profile_id, IdentityKind.PROCESSING_PROFILE)


@dataclass(frozen=True, slots=True)
class RagBuildContext:
    """Contexto operacional de un build de release derivado del servidor.

    Un comando de build parte de ``rag_release_id``; el servidor deriva de él
    proyecto, variante, perfil, target y snapshot. El cliente nunca compone esta
    terna a mano (invariante de seguridad §1 del plan).
    """

    project_id: PlatformId
    rag_variant_id: PlatformId
    rag_release_id: PlatformId
    corpus_snapshot_id: PlatformId
    embedding_profile_id: str
    indexing_target_id: str
    semantic_recipe_fingerprint: str

    def __post_init__(self) -> None:
        _require(self.project_id, IdentityKind.PROJECT)
        _require(self.rag_variant_id, IdentityKind.RAG_VARIANT)
        _require(self.rag_release_id, IdentityKind.RAG_RELEASE)
        _require(self.corpus_snapshot_id, IdentityKind.CORPUS_SNAPSHOT)
        if not self.semantic_recipe_fingerprint:
            raise InvalidIdentity("semantic_recipe_fingerprint must not be empty")


def _require(identity: PlatformId, kind: IdentityKind) -> None:
    """Verifica que ``identity`` sea de la clase ``kind`` esperada."""

    if not isinstance(identity, PlatformId) or identity.kind is not kind:
        got = identity.kind.name if isinstance(identity, PlatformId) else type(identity).__name__
        raise InvalidIdentity(f"expected {kind.name} identity, got {got}")
