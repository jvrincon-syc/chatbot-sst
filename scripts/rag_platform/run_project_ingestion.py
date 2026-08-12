"""Wrapper CLI de ingesta ``raw`` por proyecto (Fase 2, Task 4).

Delega en ``RegisterProjectRawArtifactUseCase``: escanea la raíz declarada
``raw`` del proyecto con ``scan_docs_raw`` (el mismo inventario del pipeline
legacy) y registra cada archivo como revisión lógica + sidecar físico. No
duplica ``run_pipeline`` ni reimplementa inventario/normalización.

Fail-closed: sin DSN de PostgreSQL o con un ``--project-id`` inexistente, el
comando aborta con código distinto de cero y no escribe nada.

Uso:
    npm run python -- scripts/rag_platform/run_project_ingestion.py \
        --project-id proj_sst-general [--actor-id operator] [--env-file secrets.env]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Sequence

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "app" / "back" / "src"))
sys.path.insert(0, str(_REPO_ROOT / "scripts" / "indexing"))

from prepare_postgres_indexing import build_dsn_from_env, load_env_file  # noqa: E402

from ingestion.inventory.scanner import scan_docs_raw  # noqa: E402
from rag_platform.application.document_revision_service import (  # noqa: E402
    CreateSourceDocumentRevisionUseCase,
)
from rag_platform.application.raw_ingestion_service import (  # noqa: E402
    RegisterProjectRawArtifactRequest,
    RegisterProjectRawArtifactUseCase,
)
from rag_platform.domain.errors import ProjectNotFound  # noqa: E402
from rag_platform.domain.identity import IdentityKind, PlatformId  # noqa: E402
from rag_platform.infrastructure.in_memory.repositories import (  # noqa: E402
    AllowAllAccessPolicy,
)
from rag_platform.infrastructure.postgres.artifact_catalog_repositories import (  # noqa: E402
    PostgresRawArtifactCatalogRepository,
)
from rag_platform.infrastructure.postgres.document_repositories import (  # noqa: E402
    PostgresSourceDocumentRepository,
)
from rag_platform.infrastructure.postgres.project_repositories import (  # noqa: E402
    PostgresProjectRepository,
)
from rag_platform.infrastructure.storage.project_storage import (  # noqa: E402
    ProjectStorageResolver,
)

# Metadatos de inventario: la revisión lógica es la fuente de identidad; estos
# solo etiquetan el escaneo determinista de bytes.
_CORPUS_VERSION = "platform-raw"
_PIPELINE_VERSION = "platform-raw-v1"


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-id", required=True, help="ID de proyecto (proj_...).")
    parser.add_argument("--actor-id", default="platform-operator")
    parser.add_argument("--env-file", default="secrets.env")
    parser.add_argument(
        "--data-dir",
        default=str(_REPO_ROOT / "data"),
        help="Directorio base de datos; las raíces cuelgan de projects/{slug}/.",
    )
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def _build_use_case(connection: object) -> RegisterProjectRawArtifactUseCase:
    """Cablea el orquestador con adaptadores PostgreSQL reales."""

    return RegisterProjectRawArtifactUseCase(
        projects=PostgresProjectRepository(connection),
        revisions=CreateSourceDocumentRevisionUseCase(
            documents=PostgresSourceDocumentRepository(connection),
            access_policy=AllowAllAccessPolicy(),
        ),
        raw_catalog=PostgresRawArtifactCatalogRepository(connection),
    )


def _emit(payload: dict[str, object], *, as_json: bool) -> None:
    print(json.dumps(payload, indent=None if as_json else 2, ensure_ascii=False))


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)

    env = dict(load_env_file(Path(args.env_file)))
    env.update(os.environ)
    dsn = build_dsn_from_env(env)
    if not dsn:
        _emit({"status": "blocked", "reason": "postgres_dsn_missing"}, as_json=args.json)
        return 2

    project_pid = PlatformId(kind=IdentityKind.PROJECT, value=args.project_id)

    import psycopg2
    from psycopg2.extensions import parse_dsn

    connection = psycopg2.connect(**parse_dsn(dsn))
    try:
        projects = PostgresProjectRepository(connection)
        try:
            project = projects.get(project_pid)
        except ProjectNotFound:
            _emit(
                {
                    "status": "blocked",
                    "reason": "project_not_found",
                    "project_id": args.project_id,
                },
                as_json=args.json,
            )
            return 2

        raw_root = ProjectStorageResolver(Path(args.data_dir)).resolve_declared_root(
            project, "raw"
        )
        records = scan_docs_raw(
            raw_root,
            corpus_version=_CORPUS_VERSION,
            pipeline_version=_PIPELINE_VERSION,
        )
        use_case = _build_use_case(connection)
        registered: list[str] = []
        with connection:  # una sola transacción para todo el escaneo
            for record in records:
                revision = use_case.execute(
                    RegisterProjectRawArtifactRequest(
                        project_id=args.project_id[len(f"{IdentityKind.PROJECT.value}_") :],
                        source_relpath=record.source_relpath,
                        raw_content_hash=record.content_hash,
                        file_size=record.file_size,
                    ),
                    actor_id=args.actor_id,
                )
                registered.append(revision.source_document_revision_id.value)
    finally:
        connection.close()

    _emit(
        {
            "status": "registered",
            "project_id": args.project_id,
            "raw_root": str(raw_root),
            "documents": len(registered),
            "revision_ids": registered,
        },
        as_json=args.json,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
