"""Repositorios in-memory de releases y membresías (Fase 5, tests/dry-run).

Implementan el mismo contrato observable que los adaptadores PostgreSQL de
``20260810_07``: unicidad de ``release_number`` por variante, membresía única por
revisión y transición de estado. No consumen red.
"""

from __future__ import annotations

from datetime import datetime
import threading

from rag_platform.domain.errors import (
    CorpusSnapshotNotFound,
    RagReleaseNotFound,
    RagVariantNotFound,
)
from rag_platform.domain.identity import PlatformId
from rag_platform.domain.lifecycle import (
    RagRelease,
    RagReleaseMembership,
    ReleaseState,
)
from rag_platform.domain.models import CorpusSnapshot, RagVariant


class InMemoryRagVariantReader:
    """Lectura de variantes por id (Fase 5). Se siembra con variantes conocidas."""

    def __init__(self, variants: tuple[RagVariant, ...] = ()) -> None:
        self._by_id: dict[str, RagVariant] = {
            variant.rag_variant_id.value: variant for variant in variants
        }

    def add(self, variant: RagVariant) -> RagVariant:
        """Registra una variante para poder leerla por id."""

        self._by_id[variant.rag_variant_id.value] = variant
        return variant

    def get(self, rag_variant_id: PlatformId) -> RagVariant:
        try:
            return self._by_id[rag_variant_id.value]
        except KeyError as error:
            raise RagVariantNotFound(rag_variant_id.value) from error


class InMemoryCorpusSnapshotReader:
    """Lectura de corpus snapshots por id (Fase 5)."""

    def __init__(self, snapshots: tuple[CorpusSnapshot, ...] = ()) -> None:
        self._by_id: dict[str, CorpusSnapshot] = {
            snapshot.corpus_snapshot_id.value: snapshot for snapshot in snapshots
        }

    def add(self, snapshot: CorpusSnapshot) -> CorpusSnapshot:
        """Registra un snapshot para poder leerlo por id."""

        self._by_id[snapshot.corpus_snapshot_id.value] = snapshot
        return snapshot

    def get(self, corpus_snapshot_id: PlatformId) -> CorpusSnapshot:
        try:
            return self._by_id[corpus_snapshot_id.value]
        except KeyError as error:
            raise CorpusSnapshotNotFound(corpus_snapshot_id.value) from error


class StaticConfigurationFingerprintReader:
    """Fingerprint de configuración por ``(proyecto, versión)`` (determinista, tests).

    Acepta un fingerprint fijo por proyecto o, opcionalmente, por
    ``(project_id, version)`` para probar el pinning: dos versiones de un mismo
    proyecto pueden devolver fingerprints distintos.
    """

    def __init__(
        self,
        fingerprints: dict[str, str] | None = None,
        *,
        by_version: dict[tuple[str, int], str] | None = None,
    ) -> None:
        self._by_project = dict(fingerprints or {})
        self._by_version = dict(by_version or {})

    def configuration_fingerprint(
        self, project_id: PlatformId, configuration_version: int
    ) -> str:
        keyed = self._by_version.get((project_id.value, configuration_version))
        if keyed is not None:
            return keyed
        # Determinista: si no hay override, deriva un marcador estable del id.
        return self._by_project.get(project_id.value, "0" * 64)


class InMemoryCurrentConfigurationVersionReader:
    """Versión de configuración vigente por proyecto (mutable para tests de pinning).

    Permite simular que la configuración avanza entre crear un DRAFT y validar/
    construir, para verificar que la release usa la versión pinneada y no la
    vigente.
    """

    def __init__(
        self, versions: dict[str, int] | None = None, *, default: int = 1
    ) -> None:
        self._by_project = dict(versions or {})
        self._default = default

    def set_version(self, project_id: PlatformId, version: int) -> None:
        """Fija la versión vigente de un proyecto (helper de test)."""

        self._by_project[project_id.value] = version

    def current_configuration_version(self, project_id: PlatformId) -> int:
        return self._by_project.get(project_id.value, self._default)


class InMemoryRagReleaseRepository:
    """Releases en memoria con unicidad de ``release_number`` por variante."""

    def __init__(self) -> None:
        self._by_id: dict[str, RagRelease] = {}
        self._lock = threading.Lock()

    def add(self, release: RagRelease) -> RagRelease:
        with self._lock:
            self._by_id[release.rag_release_id.value] = release
        return release

    def get(self, rag_release_id: PlatformId) -> RagRelease:
        try:
            return self._by_id[rag_release_id.value]
        except KeyError as error:
            raise RagReleaseNotFound(rag_release_id.value) from error

    def list_for_project(self, project_id: PlatformId) -> list[RagRelease]:
        return [
            release
            for _, release in sorted(self._by_id.items())
            if release.project_id == project_id
        ]

    def list_release_numbers(self, rag_variant_id: PlatformId) -> list[int]:
        return [
            release.release_number
            for release in self._by_id.values()
            if release.rag_variant_id == rag_variant_id
        ]

    def update_state(
        self,
        *,
        rag_release_id: PlatformId,
        state: ReleaseState,
        release_manifest_hash: str | None = None,
        validated_at: datetime | None = None,
        reason: str | None = None,
    ) -> RagRelease:
        with self._lock:
            current = self.get(rag_release_id)
            updates: dict[str, object] = {"state": state}
            if release_manifest_hash is not None:
                updates["release_manifest_hash"] = release_manifest_hash
            if validated_at is not None:
                updates["validated_at"] = validated_at
            if reason is not None:
                updates["reason"] = reason
            updated = current.model_copy(update=updates)
            self._by_id[rag_release_id.value] = updated
        return updated


class InMemoryRagReleaseMembershipRepository:
    """Membresías en memoria, únicas por (release, revisión)."""

    def __init__(self) -> None:
        self._by_release: dict[str, dict[str, RagReleaseMembership]] = {}

    def add(self, membership: RagReleaseMembership) -> RagReleaseMembership:
        release_key = membership.rag_release_id.value
        revision_key = membership.source_document_revision_id.value
        self._by_release.setdefault(release_key, {})[revision_key] = membership
        return membership

    def list_for_release(
        self, rag_release_id: PlatformId
    ) -> list[RagReleaseMembership]:
        return list(self._by_release.get(rag_release_id.value, {}).values())
