"""End-to-end del tramo de release: prueba que ``rag_release_id`` se persiste.

El e2e físico (``test_end_to_end_local_platform.py``) solo materializa artefactos
con ``rebuild_platform`` y deja ``rag_release_id`` NULL a propósito (no construye una
release). Este test cierra esa deuda (#1): corre el tramo de release real
``corpus snapshot -> CreateRagReleaseDraft -> BuildRagReleaseUseCase`` y verifica en
PostgreSQL que ``embedding_runs``/``indexing_runs`` quedan estampados con el
``rag_release_id`` de la release construida.

Se **limpian los derivados** antes de construir para forzar el path BUILD del
resolver (no REUSE): solo un run recién creado por el build lleva el
``rag_release_id`` derivado server-side; un artefacto reusado no crea run nuevo.

Requiere corpus real + runtime BGE + PostgreSQL con proyecto/variante/binding
sembrados (``scripts/rag_platform/seed_project.py``) y el corpus normalizado en
disco. Marcado ``corpus``/``bge_runtime``/``postgres_live``; el usuario lo corre con
autorización explícita.

Uso:
    npm run python -- -m pytest app/back/tests/rag_platform/test_end_to_end_release_build.py -v
"""

from __future__ import annotations

import importlib.util
import sys
import uuid
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
_RAW_ROOT = _REPO_ROOT / "data" / "projects" / "sst-general" / "raw"
sys.path.insert(0, str(_REPO_ROOT / "app" / "back" / "src"))
sys.path.insert(0, str(_REPO_ROOT / "scripts" / "indexing"))

_PROJECT_ID = "proj_sst-general"
_VARIANT_ID = "ragv_local-bge"
_BINDING_KEY = "primary"
_ACTOR = "operator-release-e2e"

_MD = "convivencia_laboral/manual/introduccion.md"
_PDF_TEXTO = "convivencia_laboral/manual/1761580555950_syc_RE.RH-04SST23102025.pdf"
_PDF_ESCANEADO = "convivencia_laboral/manual/1781045303349_syc_politicadedesconexin.pdf"
_THREE_DOCS = (_MD, _PDF_TEXTO, _PDF_ESCANEADO)


def _load(module_name: str, relpath: str):
    spec = importlib.util.spec_from_file_location(module_name, _REPO_ROOT / relpath)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _dsn() -> str | None:
    from prepare_postgres_indexing import build_dsn_from_env, load_env_file

    return build_dsn_from_env(dict(load_env_file(_REPO_ROOT / "secrets.env")))


def _connect(dsn: str):
    import psycopg2
    from psycopg2.extensions import parse_dsn

    return psycopg2.connect(**parse_dsn(dsn))


def _variant_seeded(dsn: str) -> bool:
    connection = _connect(dsn)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM rag_variants WHERE rag_variant_id = %s", (_VARIANT_ID,)
            )
            return cursor.fetchone() is not None
    finally:
        connection.close()


def _clear_derived_artifacts(dsn: str) -> None:
    """Borra derivados (no raw/normalized/revisiones) para forzar el path BUILD."""

    connection = _connect(dsn)
    connection.autocommit = False
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
                " AND tablename LIKE 'idx_vec_%'"
            )
            derived = [row[0] for row in cursor.fetchall()] + [
                "indexing_materializations",
                "readiness_checks",
                "indexing_nodes",
                "indexing_run_documents",
                "indexing_runs",
                "embedding_bundle_chunks",
                "embedding_runs",
                "embedding_bundles",
                "rag_release_memberships",
                "rag_release_documents",
                "rag_build_steps",
                "rag_build_runs",
                "rag_releases",
                "chunk_bundles",
            ]
            for table in derived:
                cursor.execute("SELECT to_regclass(%s)", (f"public.{table}",))
                if cursor.fetchone()[0] is None:
                    continue
                cursor.execute(f"DELETE FROM {table}")
        connection.commit()
    finally:
        connection.close()
    import shutil

    for name in ("chunks", "embeddings"):
        path = _REPO_ROOT / "data" / "projects" / "sst-general" / name
        if path.exists():
            shutil.rmtree(path)


def _revision_ids_for(dsn: str, relpaths: tuple[str, ...]) -> list[str]:
    """Devuelve los ``srev_`` de los 3 documentos, en el orden pedido."""

    connection = _connect(dsn)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT source_relpath, source_document_revision_id"
                " FROM source_document_revisions WHERE project_id = %s",
                (_PROJECT_ID,),
            )
            by_relpath = {str(row[0]): str(row[1]) for row in cursor.fetchall()}
    finally:
        connection.close()
    return [by_relpath[relpath] for relpath in relpaths if relpath in by_relpath]


@pytest.mark.corpus
@pytest.mark.bge_runtime
@pytest.mark.postgres_live
def test_release_build_persiste_rag_release_id(capsys) -> None:
    if not _RAW_ROOT.exists():
        pytest.skip(f"corpus ausente: {_RAW_ROOT}")
    dsn = _dsn()
    if not dsn:
        pytest.skip("sin DSN de PostgreSQL")
    if not _variant_seeded(dsn):
        pytest.skip("proyecto/variante no sembrados; corre scripts/rag_platform/seed_project.py")

    import os

    from rag_platform.application.corpus_snapshot_service import CreateCorpusSnapshotUseCase
    from rag_platform.application.release_service import CreateRagReleaseDraftUseCase
    from rag_platform.domain.identity import IdentityKind, PlatformId
    from rag_platform.infrastructure.postgres.document_repositories import (
        PostgresCorpusSnapshotRepository,
        PostgresSourceDocumentRepository,
    )
    from rag_platform.infrastructure.postgres.project_repositories import (
        PostgresRagVariantRepository,
        PostgresTargetBindingResolver,
    )
    from rag_platform.infrastructure.postgres.release_repositories import (
        PostgresRagReleaseRepository,
    )

    # --- 0) prerequisitos: raw + normalized en disco/BD -------------------------
    # Registra raw (crea source_document_revisions) y normaliza el corpus. El build
    # de release lee el normalizado de disco; sin él no hay artefacto que reusar.
    ingestion_cli = _load(
        "run_project_ingestion_rel", "scripts/rag_platform/run_project_ingestion.py"
    )
    rc = ingestion_cli.main(
        ["--project-id", _PROJECT_ID, "--rag-variant-id", _VARIANT_ID, "--normalize", "--force"]
    )
    assert rc == 0, "raw+normalize no debe reportar fallos"
    capsys.readouterr()

    revision_ids = _revision_ids_for(dsn, _THREE_DOCS)
    assert len(revision_ids) == len(_THREE_DOCS), (
        f"faltan revisiones para los 3 docs: {revision_ids}"
    )

    # Slate limpio de derivados => el build construye (no reusa) y estampa release.
    _clear_derived_artifacts(dsn)

    class _Operator:
        def require_operator(self, *, actor_id: str) -> None:  # noqa: D401
            return None

    # --- 1) corpus snapshot -----------------------------------------------------
    conn = _connect(dsn)
    conn.autocommit = False
    try:
        snapshot = CreateCorpusSnapshotUseCase(
            snapshots=PostgresCorpusSnapshotRepository(conn),
            documents=PostgresSourceDocumentRepository(conn),
            access_policy=_Operator(),
        ).execute(
            project_id="sst-general",
            document_revision_ids=revision_ids,
            actor_id=_ACTOR,
        )
        conn.commit()

        # --- 2) CreateRagReleaseDraft -------------------------------------------
        release = CreateRagReleaseDraftUseCase(
            variants=PostgresRagVariantRepository(conn),
            snapshots=PostgresCorpusSnapshotRepository(conn),
            bindings=PostgresTargetBindingResolver(conn),
            releases=PostgresRagReleaseRepository(conn),
            release_id_factory=lambda: PlatformId(
                kind=IdentityKind.RAG_RELEASE, value="ragr_" + uuid.uuid4().hex[:16]
            ),
        ).execute(
            rag_variant_id=PlatformId(kind=IdentityKind.RAG_VARIANT, value=_VARIANT_ID),
            corpus_snapshot_id=snapshot.corpus_snapshot_id,
            target_binding_key=_BINDING_KEY,
            actor_id=_ACTOR,
        )
        conn.commit()
    finally:
        conn.close()

    release_id = release.rag_release_id.value

    # --- 3) BuildRagReleaseUseCase (BGE vivo) -----------------------------------
    from api.dependencies import build_pipeline_services_from_env

    os.environ["SST_POSTGRES_DSN"] = dsn
    os.environ["SST_PERSISTENCE_MODE"] = "postgres"
    os.environ["SST_FEATURE_RAG_PLATFORM_V1"] = "true"
    chunks_root = _REPO_ROOT / "data" / "projects" / "sst-general" / "chunks"
    embeddings_root = _REPO_ROOT / "data" / "projects" / "sst-general" / "embeddings"
    services = build_pipeline_services_from_env(
        chunks_root=chunks_root, embeddings_root=embeddings_root
    )
    try:
        assert services.rag_platform_build is not None, "build no cableado tras el flag"
        report = services.rag_platform_build.execute(
            rag_release_id=release.rag_release_id, actor_id=_ACTOR
        )
        assert report.revisions_built == len(_THREE_DOCS)
        assert report.built_stages > 0, "el build debía construir (no solo reusar)"
    finally:
        services.close()

    # --- 4) PostgreSQL: rag_release_id persistido en los runs -------------------
    connection = _connect(dsn)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT DISTINCT rag_release_id FROM embedding_runs"
                " WHERE project_id = %s AND rag_release_id IS NOT NULL",
                (_PROJECT_ID,),
            )
            embed_releases = {row[0] for row in cursor.fetchall()}
            cursor.execute(
                "SELECT DISTINCT rag_release_id FROM indexing_runs"
                " WHERE project_id = %s AND rag_release_id IS NOT NULL",
                (_PROJECT_ID,),
            )
            index_releases = {row[0] for row in cursor.fetchall()}
            cursor.execute(
                "SELECT 1 FROM rag_releases WHERE rag_release_id = %s", (release_id,)
            )
            release_row = cursor.fetchone()
    finally:
        connection.close()

    assert release_row is not None, "la release DRAFT no se persistió"
    assert embed_releases == {release_id}, (
        f"embedding_runs.rag_release_id = {embed_releases}, esperado {{{release_id}}}"
    )
    assert index_releases == {release_id}, (
        f"indexing_runs.rag_release_id = {index_releases}, esperado {{{release_id}}}"
    )
