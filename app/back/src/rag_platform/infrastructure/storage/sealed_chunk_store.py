"""Sellado content-addressed de chunk bundles de plataforma (Fase 3).

Escribe bundles sellados bajo ``chunks/{chunk_bundle_id}/`` con ``manifest.json``,
``parent_chunks.jsonl``, ``child_chunks.jsonl`` y ``checksums.json``. Reutiliza la
escritura atómica staging→promote compartida (``core.atomic_fs``), la misma que
usa la lane legacy, pero **nunca** escribe sobre la ruta legacy ni llama a
``replace()``.

Inmutabilidad (invariante §3): un artefacto sellado es append-only. Re-sellar bytes
idénticos es idempotente y devuelve el mismo manifest/hash; sellar bytes distintos
bajo la misma identidad falla cerrado con ``SealedBundleConflict`` y jamás
sobreescribe archivos referenciados por una release.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
from typing import Any

from core import atomic_fs
from rag_platform.domain.errors import SealedBundleConflict
from rag_platform.domain.identity import PlatformId
from rag_platform.domain.models import SealedChunkBundle, SealingStatus
from rag_platform.infrastructure.storage.project_storage import ProjectStorageResolver


#: Raíz canónica de artefactos de chunking dentro del proyecto.
_CHUNKS_ROOT = "chunks"
_MANIFEST_NAME = "manifest.json"
_PARENTS_NAME = "parent_chunks.jsonl"
_CHILDREN_NAME = "child_chunks.jsonl"
#: Archivo de integridad; actúa como marker de commit (se promueve al final).
_CHECKSUMS_NAME = "checksums.json"


class SealedChunkStore:
    """Adaptador de sellado content-addressed por proyecto."""

    def __init__(self, resolver: ProjectStorageResolver) -> None:
        self._resolver = resolver

    def stage_and_seal(
        self,
        *,
        project_id: PlatformId,
        chunk_bundle_id: str,
        normalized_document_id: str,
        chunking_profile_fingerprint: str,
        bundle_schema_version: str,
        manifest: Mapping[str, Any],
        parent_chunks: Sequence[Mapping[str, Any]],
        child_chunks: Sequence[Mapping[str, Any]],
    ) -> SealedChunkBundle:
        """Sella un chunk bundle de forma atómica e idempotente.

        Args:
            project_id: Proyecto propietario del artefacto.
            chunk_bundle_id: Id content-addressed que nombra el directorio sellado.
            normalized_document_id: Normalizado del que deriva (parte de la identidad).
            chunking_profile_fingerprint: Fingerprint del perfil de chunking.
            bundle_schema_version: Versión del esquema de bundle sellado.
            manifest: Contenido del ``manifest.json`` (sin secretos ni texto completo).
            parent_chunks: Filas de parents a serializar como JSONL.
            child_chunks: Filas de children a serializar como JSONL.

        Returns:
            El ``SealedChunkBundle`` sellado (o el preexistente idéntico).

        Raises:
            SealedBundleConflict: Si ya existe un sellado con bytes distintos.
        """

        manifest_path = self._resolve(project_id, chunk_bundle_id, _MANIFEST_NAME)
        parents_path = self._resolve(project_id, chunk_bundle_id, _PARENTS_NAME)
        children_path = self._resolve(project_id, chunk_bundle_id, _CHILDREN_NAME)
        checksums_path = self._resolve(project_id, chunk_bundle_id, _CHECKSUMS_NAME)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)

        # ponytail: asume un único escritor por chunk_bundle_id. Los .tmp comparten
        # nombre y el chequeo de conflicto precede a la promoción (TOCTOU), así que
        # dos sellados simultáneos del mismo id no son seguros. No hay caller
        # concurrente en Fase 3; el orquestador de build paralelo (Fase 5) debe
        # tomar un lock por chunk_bundle_id (o crear el marker con O_EXCL) aquí.
        manifest_stage = _stage(manifest_path)
        parents_stage = _stage(parents_path)
        children_stage = _stage(children_path)
        checksums_stage = _stage(checksums_path)

        try:
            atomic_fs.write_json(manifest_stage, dict(manifest))
            atomic_fs.write_jsonl(parents_stage, parent_chunks)
            atomic_fs.write_jsonl(children_stage, child_chunks)
            checksums = {
                _MANIFEST_NAME: _digest(manifest_stage),
                _PARENTS_NAME: _digest(parents_stage),
                _CHILDREN_NAME: _digest(children_stage),
            }
            atomic_fs.write_json(checksums_stage, checksums)

            # Fail-closed: valida el contrato ANTES de promover. Si la identidad es
            # inválida, el except descarta los .tmp y NADA queda sellado (no se
            # promueve un artefacto cuyo contrato de retorno sería inconstruible).
            sealed_bundle = SealedChunkBundle(
                chunk_bundle_id=chunk_bundle_id,
                project_id=project_id,
                normalized_document_id=normalized_document_id,
                chunking_profile_fingerprint=chunking_profile_fingerprint,
                bundle_schema_version=bundle_schema_version,
                bundle_dir_relpath=f"{_CHUNKS_ROOT}/{chunk_bundle_id}",
                checksums=checksums,
                parent_count=len(parent_chunks),
                child_count=len(child_chunks),
                sealing_status=SealingStatus.SEALED,
            )

            if self._existing_if_sealed(
                checksums_path=checksums_path, checksums=checksums, bundle_id=chunk_bundle_id
            ):
                # Idempotente: ya sellado con bytes idénticos. No reescribe finales.
                self._discard(
                    manifest_stage, parents_stage, children_stage, checksums_stage
                )
            else:
                atomic_fs.promote_atomically(
                    [
                        (manifest_stage, manifest_path),
                        (parents_stage, parents_path),
                        (children_stage, children_path),
                        (checksums_stage, checksums_path),
                    ],
                    marker=checksums_path,
                )
        except Exception:
            # Borde de escritura: limpia staged y preserva la causa (incluida
            # SealedBundleConflict) sin dejar el sellado a medias.
            self._discard(
                manifest_stage, parents_stage, children_stage, checksums_stage
            )
            raise

        return sealed_bundle

    def _resolve(
        self, project_id: PlatformId, chunk_bundle_id: str, name: str
    ) -> Path:
        return self._resolver.resolve_artifact(
            project_id,
            PurePosixPath(f"{_CHUNKS_ROOT}/{chunk_bundle_id}/{name}"),
        )

    @staticmethod
    def _existing_if_sealed(
        *, checksums_path: Path, checksums: Mapping[str, str], bundle_id: str
    ) -> bool:
        if not checksums_path.exists():
            return False
        existing = json.loads(checksums_path.read_text(encoding="utf-8"))
        if existing == dict(checksums):
            return True
        raise SealedBundleConflict(
            f"chunk bundle {bundle_id!r} is already sealed with different content"
        )

    @staticmethod
    def _discard(*paths: Path) -> None:
        for path in paths:
            if path.exists():
                path.unlink()


def _stage(path: Path) -> Path:
    return path.with_suffix(path.suffix + ".tmp")


def _digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()
