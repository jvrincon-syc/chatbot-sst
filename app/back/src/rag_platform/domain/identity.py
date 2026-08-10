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
import re


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
