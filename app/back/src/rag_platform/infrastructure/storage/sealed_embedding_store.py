"""Sellado content-addressed de embedding bundles de plataforma (Fase 4).

Espeja :mod:`rag_platform.infrastructure.storage.sealed_chunk_store`: escribe el
bundle sellado bajo ``embeddings/{embedding_bundle_id}/`` con ``manifest.json``,
``vectors.jsonl``, ``chunk_map.jsonl`` y ``checksums.json``, reutilizando la
escritura atómica staging→promote compartida (:mod:`core.atomic_fs`) y **nunca**
``replace()`` sobre una ruta sellada.

Decisión (ADR-007 §4): se reusa ``core.atomic_fs`` (JSON/JSONL) en vez del
``vectors.npy`` binario de la lane legacy de embedding, para compartir exactamente
el mismo patrón de sellado atómico y marker de commit que ``SealedChunkStore``. El
vector se serializa como una fila JSONL ``{"offset", "values"}`` por vector.

Inmutabilidad (ADR-007 §3/§4): un artefacto sellado es append-only. Re-sellar bytes
idénticos es idempotente; sellar bytes distintos bajo la misma identidad falla
cerrado con ``SealedBundleConflict`` y jamás sobreescribe archivos ya sellados.
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
from rag_platform.domain.models import (
    PhysicalDistanceMetric,
    SealedEmbeddingBundle,
    SealingStatus,
)
from rag_platform.infrastructure.storage.project_storage import ProjectStorageResolver


#: Raíz canónica de artefactos de embedding dentro del proyecto.
_EMBEDDINGS_ROOT = "embeddings"
_MANIFEST_NAME = "manifest.json"
_VECTORS_NAME = "vectors.jsonl"
_CHUNK_MAP_NAME = "chunk_map.jsonl"
#: Archivo de integridad; actúa como marker de commit (se promueve al final).
_CHECKSUMS_NAME = "checksums.json"


class SealedEmbeddingStore:
    """Adaptador de sellado content-addressed de embeddings por proyecto."""

    def __init__(self, resolver: ProjectStorageResolver) -> None:
        self._resolver = resolver

    def stage_and_seal(
        self,
        *,
        project_id: PlatformId,
        embedding_bundle_id: str,
        source_chunk_bundle_id: str,
        dimension: int,
        distance_metric: PhysicalDistanceMetric,
        manifest: Mapping[str, Any],
        vectors: Sequence[Sequence[float]],
        chunk_map: Sequence[Mapping[str, Any]],
    ) -> SealedEmbeddingBundle:
        """Sella un embedding bundle de forma atómica e idempotente.

        Args:
            project_id: Proyecto propietario del artefacto.
            embedding_bundle_id: Id que nombra el directorio sellado.
            source_chunk_bundle_id: Chunk bundle de origen (parte de la evidencia).
            dimension: Dimensión de cada vector (debe ser > 0).
            distance_metric: Métrica de distancia del espacio vectorial.
            manifest: Contenido del ``manifest.json`` (sin secretos ni texto completo).
            vectors: Filas densas; cada una debe tener longitud ``dimension``.
            chunk_map: Mapa child-chunk→slot a serializar como JSONL.

        Returns:
            El ``SealedEmbeddingBundle`` sellado (o el preexistente idéntico).

        Raises:
            ValueError: Si algún vector no respeta ``dimension`` o el mapa no cubre
                los vectores (fail-closed antes de escribir nada).
            SealedBundleConflict: Si ya existe un sellado con bytes distintos.
        """

        if len(vectors) != len(chunk_map):
            raise ValueError("vector count and chunk map length must match before sealing")
        for offset, values in enumerate(vectors):
            if len(values) != dimension:
                raise ValueError(
                    f"vector at offset {offset} has length {len(values)} != {dimension}"
                )

        manifest_path = self._resolve(project_id, embedding_bundle_id, _MANIFEST_NAME)
        vectors_path = self._resolve(project_id, embedding_bundle_id, _VECTORS_NAME)
        chunk_map_path = self._resolve(project_id, embedding_bundle_id, _CHUNK_MAP_NAME)
        checksums_path = self._resolve(project_id, embedding_bundle_id, _CHECKSUMS_NAME)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)

        # ponytail: un único escritor por embedding_bundle_id (mismo límite TOCTOU
        # que SealedChunkStore). El orquestador de build paralelo (Fase 5) debe tomar
        # un lock por bundle o crear el marker con O_EXCL aquí.
        manifest_stage = _stage(manifest_path)
        vectors_stage = _stage(vectors_path)
        chunk_map_stage = _stage(chunk_map_path)
        checksums_stage = _stage(checksums_path)

        vector_rows = [
            {"offset": offset, "values": [float(value) for value in values]}
            for offset, values in enumerate(vectors)
        ]
        try:
            atomic_fs.write_json(manifest_stage, dict(manifest))
            atomic_fs.write_jsonl(vectors_stage, vector_rows)
            atomic_fs.write_jsonl(chunk_map_stage, chunk_map)
            checksums = {
                _MANIFEST_NAME: _digest(manifest_stage),
                _VECTORS_NAME: _digest(vectors_stage),
                _CHUNK_MAP_NAME: _digest(chunk_map_stage),
            }
            atomic_fs.write_json(checksums_stage, checksums)

            # Fail-closed: valida el contrato ANTES de promover (lección Fase 3). Si
            # la identidad es inválida, el except descarta los .tmp y NADA queda sellado.
            sealed_bundle = SealedEmbeddingBundle(
                embedding_bundle_id=embedding_bundle_id,
                project_id=project_id,
                source_chunk_bundle_id=source_chunk_bundle_id,
                bundle_dir_relpath=f"{_EMBEDDINGS_ROOT}/{embedding_bundle_id}",
                checksums=checksums,
                dimension=dimension,
                distance_metric=distance_metric,
                vector_count=len(vectors),
                sealing_status=SealingStatus.SEALED,
            )

            if self._existing_if_sealed(
                checksums_path=checksums_path,
                checksums=checksums,
                bundle_id=embedding_bundle_id,
            ):
                self._discard(
                    manifest_stage, vectors_stage, chunk_map_stage, checksums_stage
                )
            else:
                atomic_fs.promote_atomically(
                    [
                        (manifest_stage, manifest_path),
                        (vectors_stage, vectors_path),
                        (chunk_map_stage, chunk_map_path),
                        (checksums_stage, checksums_path),
                    ],
                    marker=checksums_path,
                )
        except Exception:
            # Borde de escritura: limpia staged y preserva la causa (incluida
            # SealedBundleConflict) sin dejar el sellado a medias.
            self._discard(
                manifest_stage, vectors_stage, chunk_map_stage, checksums_stage
            )
            raise

        return sealed_bundle

    def verify_checksum(
        self,
        *,
        project_id: PlatformId,
        embedding_bundle_id: str,
        expected: Mapping[str, str],
    ) -> bool:
        """Recomputa los checksums del artefacto sellado y los compara.

        Returns:
            ``True`` solo si cada archivo esperado existe y su digest coincide.
        """

        for filename, digest in expected.items():
            candidate = self._resolve(project_id, embedding_bundle_id, filename)
            if not candidate.exists() or _digest(candidate) != digest:
                return False
        return True

    def _resolve(
        self, project_id: PlatformId, embedding_bundle_id: str, name: str
    ) -> Path:
        return self._resolver.resolve_artifact(
            project_id,
            PurePosixPath(f"{_EMBEDDINGS_ROOT}/{embedding_bundle_id}/{name}"),
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
            f"embedding bundle {bundle_id!r} is already sealed with different content"
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
