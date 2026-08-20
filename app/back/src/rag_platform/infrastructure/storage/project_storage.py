"""Resolver de almacenamiento aislado por proyecto (Fase 1).

Deriva las raíces ``data/projects/{project_id}/{raw,normalized,chunks,
embeddings,manifests}`` y resuelve rutas de artefacto validando contención
(sin absolutos, sin ``..``, sin drive) con el mismo estilo que
``ingestion/paths.py:canonical_relpath`` (invariante §7 del plan). Para
``sst-general`` ofrece una vista de **lectura** de rutas legacy sin convertirlas
en la ubicación canónica de artefactos nuevos.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath

from rag_platform.domain.errors import UnsafeArtifactPath
from rag_platform.domain.identity import IdentityKind, PlatformId, _require
from rag_platform.domain.models import ProjectStorageRoots, RagProject


#: Subdirectorios canónicos bajo la raíz de cada proyecto.
_ARTIFACT_ROOTS: tuple[str, ...] = (
    "raw",
    "normalized",
    "chunks",
    "embeddings",
    "manifests",
)


def _project_slug(project_id: PlatformId) -> str:
    """Devuelve el cuerpo del ``project_id`` (sin el prefijo ``proj_``)."""

    _require(project_id, IdentityKind.PROJECT)
    return project_id.value[len(f"{IdentityKind.PROJECT.value}_") :]


class ProjectStorageResolver:
    """Deriva raíces y resuelve rutas de artefacto contenidas en el proyecto."""

    def __init__(self, base_dir: Path) -> None:
        """Inicializa el resolver.

        Args:
            base_dir: Directorio raíz de datos (típicamente ``.../data``). Las
                raíces de proyecto cuelgan de ``base_dir/projects/{slug}/``.
        """

        self._base_dir = Path(base_dir)
        self._projects_dir = self._base_dir / "projects"

    def roots_for(self, project_id: PlatformId) -> ProjectStorageRoots:
        """Devuelve las raíces relativas y aisladas de un proyecto.

        Las raíces se expresan como relpaths POSIX bajo ``base_dir`` para que dos
        proyectos nunca se intersecten y para no filtrar rutas absolutas.
        """

        slug = _project_slug(project_id)
        prefix = f"projects/{slug}"
        return ProjectStorageRoots(
            project_id=project_id,
            raw=f"{prefix}/raw",
            normalized=f"{prefix}/normalized",
            chunks=f"{prefix}/chunks",
            embeddings=f"{prefix}/embeddings",
            manifests=f"{prefix}/manifests",
        )

    def resolve_root(self, project_id: PlatformId, root_name: str) -> Path:
        """Return the absolute path of one canonical project root."""

        if root_name not in _ARTIFACT_ROOTS:
            raise UnsafeArtifactPath(f"unknown project root: {root_name!r}")
        slug = _project_slug(project_id)
        return (self._projects_dir / slug / root_name).resolve()

    def resolve_declared_root(self, project: RagProject, root_name: str) -> Path:
        """Resuelve una raíz desde el catálogo (``project.storage_roots``).

        Honra el relpath declarado en el catálogo (p. ej. ``docs_raw`` legacy) en
        vez de asumir el layout canónico, para que el drift ``raw``/``docs_raw`` sea
        catalog-driven y no una constante. Mantiene contención bajo ``base_dir``.
        """

        if root_name not in _ARTIFACT_ROOTS:
            raise UnsafeArtifactPath(f"unknown project root: {root_name!r}")
        relpath = str(getattr(project.storage_roots, root_name))
        if not relpath or "\\" in relpath or relpath.startswith("/"):
            raise UnsafeArtifactPath(f"declared root must be relative POSIX: {relpath!r}")
        if any(part in {"", ".", ".."} for part in relpath.split("/")):
            raise UnsafeArtifactPath(f"declared root has unsafe component: {relpath!r}")
        base = self._base_dir.resolve()
        candidate = (base / relpath).resolve()
        if base != candidate and base not in candidate.parents:
            raise UnsafeArtifactPath(f"declared root escapes base dir: {relpath!r}")
        return candidate

    def resolve_artifact(
        self, project_id: PlatformId, relative_path: PurePosixPath
    ) -> Path:
        """Resuelve una ruta de artefacto contenida en la raíz del proyecto.

        Args:
            project_id: Proyecto propietario del artefacto.
            relative_path: Ruta POSIX relativa a la raíz del proyecto. Debe
                empezar por uno de los subdirectorios canónicos.

        Returns:
            La ruta absoluta resuelta dentro de la raíz del proyecto.

        Raises:
            UnsafeArtifactPath: Si la ruta es absoluta, contiene ``..`` o ``.``,
                usa separadores no POSIX, o escapa de la raíz del proyecto.
        """

        raw = str(relative_path)
        if not raw:
            raise UnsafeArtifactPath("artifact path must not be empty")
        if "\\" in raw or raw.startswith("/"):
            raise UnsafeArtifactPath(f"artifact path must be relative POSIX: {raw!r}")
        parts = raw.split("/")
        if any(part in {"", ".", ".."} for part in parts):
            raise UnsafeArtifactPath(f"artifact path has unsafe component: {raw!r}")
        if parts[0] not in _ARTIFACT_ROOTS:
            raise UnsafeArtifactPath(
                f"artifact path must start with a canonical root: {raw!r}"
            )

        slug = _project_slug(project_id)
        project_root = (self._projects_dir / slug).resolve()
        candidate = (project_root / raw).resolve()
        # Contención: el candidato resuelto debe quedar bajo la raíz del proyecto.
        if project_root != candidate and project_root not in candidate.parents:
            raise UnsafeArtifactPath(f"artifact path escapes project root: {raw!r}")
        return candidate


class FilesystemProjectRawStorage:
    """Escribe bytes subidos bajo la raíz ``raw`` declarada del proyecto.

    Adaptador del puerto ``ProjectRawStorage``: resuelve la raíz ``raw`` desde el
    catálogo (``resolve_declared_root``, la misma autoridad que usa el sidecar
    físico) y persiste el ``source_relpath`` validando contención, de modo que la
    ubicación física coincida con el ``artifact_relpath`` catalogado.
    """

    def __init__(self, resolver: ProjectStorageResolver) -> None:
        self._resolver = resolver

    def write_raw_bytes(
        self, project: RagProject, source_relpath: str, content: bytes
    ) -> None:
        raw_root = self._resolver.resolve_declared_root(project, "raw")
        if not source_relpath or "\\" in source_relpath or source_relpath.startswith("/"):
            raise UnsafeArtifactPath(
                f"source_relpath must be relative POSIX: {source_relpath!r}"
            )
        if any(part in {"", ".", ".."} for part in source_relpath.split("/")):
            raise UnsafeArtifactPath(
                f"source_relpath has unsafe component: {source_relpath!r}"
            )
        destination = (raw_root / source_relpath).resolve()
        if raw_root != destination and raw_root not in destination.parents:
            raise UnsafeArtifactPath(
                f"source_relpath escapes raw root: {source_relpath!r}"
            )
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)


class LegacySstReadAdapter:
    """Vista de **lectura** de rutas legacy para ``sst-general`` (bootstrap).

    No convierte rutas legacy en la ubicación canónica de artefactos nuevos: solo
    permite leerlas durante el bootstrap (plan §Fase 1). No expone escritura.
    """

    def __init__(self, legacy_root: Path) -> None:
        self._legacy_root = Path(legacy_root).resolve()

    def resolve_legacy(self, relative_path: PurePosixPath) -> Path:
        """Resuelve una ruta legacy de solo lectura, con contención.

        Raises:
            UnsafeArtifactPath: Si la ruta escapa de la raíz legacy o es insegura.
        """

        raw = str(relative_path)
        if not raw or "\\" in raw or raw.startswith("/"):
            raise UnsafeArtifactPath(f"legacy path must be relative POSIX: {raw!r}")
        if any(part in {"", ".", ".."} for part in raw.split("/")):
            raise UnsafeArtifactPath(f"legacy path has unsafe component: {raw!r}")
        candidate = (self._legacy_root / raw).resolve()
        if self._legacy_root != candidate and self._legacy_root not in candidate.parents:
            raise UnsafeArtifactPath(f"legacy path escapes legacy root: {raw!r}")
        return candidate
