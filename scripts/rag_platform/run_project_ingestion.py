"""Wrapper CLI de ingesta ``raw`` (+ normalize opcional) por proyecto (Fase 2).

Etapa raw (siempre): delega en ``RegisterProjectRawArtifactUseCase``: escanea la
raíz declarada ``raw`` del proyecto con ``scan_docs_raw`` (el mismo inventario del
pipeline legacy) y registra cada archivo como revisión lógica + sidecar físico.

Etapa normalize (``--normalize``): corre el motor real ``run_pipeline`` de
``raw`` a ``normalized`` del proyecto, adjuntando identidad y provenance de
plataforma al sidecar vía un ``platform_context_resolver`` construido con las
revisiones recién registradas. Requiere ``--rag-variant-id`` (o
``--processing-profile-id``) para resolver el perfil de procesamiento; sin
ninguno aborta fail-closed. Deja el markdown normalizado en disco, que es lo que
consume aguas abajo la etapa chunk de ``rebuild_platform.py``.

Fail-closed: sin DSN de PostgreSQL, con un ``--project-id`` inexistente o (en
normalize) sin perfil de procesamiento resoluble, el comando aborta con código
distinto de cero.

Uso:
    npm run python -- scripts/rag_platform/run_project_ingestion.py \
        --project-id proj_sst-general [--normalize --rag-variant-id ragv_local_bge]
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

from ingestion.application.platform_metadata import (  # noqa: E402
    PlatformContextResolutionError,
    resolve_platform_contexts_or_raise,
)
from ingestion.inventory.scanner import scan_docs_raw  # noqa: E402
from ingestion.paths import canonical_relpath  # noqa: E402
from rag_platform.application.document_revision_service import (  # noqa: E402
    CreateSourceDocumentRevisionUseCase,
)
from rag_platform.application.raw_ingestion_service import (  # noqa: E402
    RegisterProjectRawArtifactRequest,
    RegisterProjectRawArtifactUseCase,
)
from rag_platform.domain.errors import (  # noqa: E402
    ProcessingProfileNotFound,
    ProjectNotFound,
    RagVariantNotFound,
)
from rag_platform.domain.identity import (  # noqa: E402
    IdentityKind,
    PlatformId,
)
from rag_platform.domain.models import SourceDocumentRevision  # noqa: E402
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
    PostgresProcessingProfileRepository,
    PostgresProjectRepository,
    PostgresRagVariantRepository,
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
    parser.add_argument(
        "--normalize",
        action="store_true",
        help="Tras registrar raw, corre run_pipeline raw->normalized del proyecto.",
    )
    parser.add_argument(
        "--rag-variant-id",
        default=None,
        help="Variante que provee el perfil de procesamiento y la provenance (normalize).",
    )
    parser.add_argument(
        "--processing-profile-id",
        default=None,
        help="Perfil de procesamiento explícito cuando no se pasa --rag-variant-id.",
    )
    parser.add_argument("--corpus-version", default="platform-normalized")
    parser.add_argument("--pipeline-version", default="2.0.0")
    parser.add_argument(
        "--only-source",
        action="append",
        default=None,
        help="Limita la normalización a estos source_relpath (repetible). Para pruebas.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "Reprocesa aunque el hash de origen no haya cambiado. Necesario para"
            " re-normalizar por el path de plataforma docs cuyos manifests son legacy."
        ),
    )
    parser.add_argument(
        "--allow-cloud",
        action="store_true",
        help=(
            "Permite parsear PDFs con LlamaParse cloud (envía documentos a un servicio"
            " externo; requiere autorización registrada, SECURITY_AND_DATA §3). Por"
            " defecto la normalización es on-prem (pdfium + tesseract)."
        ),
    )
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def _connect(dsn: str) -> object:
    """Abre una conexión PostgreSQL desde un DSN (costura para pruebas).

    Aísla el único punto que toca el driver real para que las pruebas del wrapper
    puedan inyectar una conexión falsa sin infraestructura viva.
    """

    import psycopg2
    from psycopg2.extensions import parse_dsn

    return psycopg2.connect(**parse_dsn(dsn))


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


def _resolve_normalize_context(
    connection: object,
    *,
    rag_variant_id: str | None,
    processing_profile_id: str | None,
) -> tuple[str, str, str | None, str | None] | None:
    """Resuelve ``(profile_id, fingerprint, variant_id, recipe_fp)`` para normalize.

    La variante manda cuando se pasa: aporta el perfil de procesamiento y la
    provenance (variante + receta). Sin variante se acepta un perfil explícito.
    Devuelve ``None`` (fail-closed) si no hay perfil resoluble o si la variante o
    el perfil no existen; el caller lo traduce a ``processing_profile_unresolved``.
    """

    variant_id: str | None = None
    recipe_fp: str | None = None
    if rag_variant_id is not None:
        try:
            variant = PostgresRagVariantRepository(connection).get(
                PlatformId(kind=IdentityKind.RAG_VARIANT, value=rag_variant_id)
            )
        except RagVariantNotFound:
            return None
        profile_id = variant.processing_profile_id.value
        variant_id = variant.rag_variant_id.value
        recipe_fp = variant.semantic_recipe_fingerprint
    elif processing_profile_id is not None:
        profile_id = processing_profile_id
    else:
        return None

    try:
        profile = PostgresProcessingProfileRepository(connection).get(
            PlatformId(kind=IdentityKind.PROCESSING_PROFILE, value=profile_id)
        )
    except ProcessingProfileNotFound:
        return None
    return profile_id, profile.fingerprint, variant_id, recipe_fp


def _select_records(records: Sequence[object], only_source: Sequence[str] | None) -> list[object]:
    """Acota los registros a ``--only-source`` con ``source_relpath`` canónico.

    El preflight y ``run_pipeline`` deben ver la misma selección; sin
    ``--only-source`` no filtra nada.
    """

    if not only_source:
        return list(records)
    wanted = {canonical_relpath(source) for source in only_source}
    return [
        record
        for record in records
        if canonical_relpath(record.source_relpath) in wanted  # type: ignore[attr-defined]
    ]


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

    storage = ProjectStorageResolver(Path(args.data_dir))
    # Plan de normalize resuelto server-side (raíz + resolver puro); se ejecuta
    # fuera de la conexión porque run_pipeline es filesystem + LlamaSettings, no BD.
    normalize_plan: dict[str, object] | None = None

    connection = _connect(dsn)
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

        raw_root = storage.resolve_declared_root(project, "raw")
        records = scan_docs_raw(
            raw_root,
            corpus_version=_CORPUS_VERSION,
            pipeline_version=_PIPELINE_VERSION,
        )
        use_case = _build_use_case(connection)
        registered: list[str] = []
        revisions_by_relpath: dict[str, SourceDocumentRevision] = {}
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
                revisions_by_relpath[canonical_relpath(record.source_relpath)] = revision

        if args.normalize:
            # Resolver el perfil de procesamiento (autoridad de la receta física) y
            # la provenance de variante mientras la conexión sigue abierta.
            resolved = _resolve_normalize_context(
                connection,
                rag_variant_id=args.rag_variant_id,
                processing_profile_id=args.processing_profile_id,
            )
            if resolved is None:
                _emit(
                    {"status": "blocked", "reason": "processing_profile_unresolved"},
                    as_json=args.json,
                )
                return 2
            profile_id, fingerprint, variant_id, recipe_fp = resolved
            # Preflight fail-closed: resuelve la identidad de plataforma de TODOS los
            # documentos seleccionados ANTES de leer/escribir/promover ninguno. Un
            # documento seleccionado sin revisión aborta el normalize completo con
            # `platform_identity_incomplete` y cero sidecars.
            selected_records = _select_records(records, args.only_source)
            try:
                resolved_contexts = resolve_platform_contexts_or_raise(
                    records=selected_records,
                    revisions_by_relpath=revisions_by_relpath,
                    project_id=args.project_id,
                    processing_profile_id=profile_id,
                    processing_profile_fingerprint=fingerprint,
                    rag_variant_id=variant_id,
                    semantic_recipe_fingerprint=recipe_fp,
                )
            except PlatformContextResolutionError as exc:
                _emit(
                    {
                        "status": "blocked",
                        "reason": "platform_identity_incomplete",
                        "detail": str(exc),
                    },
                    as_json=args.json,
                )
                return 2
            normalize_plan = {
                "normalized_root": storage.resolve_declared_root(project, "normalized"),
                "resolver": (
                    lambda record: resolved_contexts[
                        canonical_relpath(record.source_relpath)
                    ]
                ),
                "rag_variant_id": variant_id,
            }
    finally:
        connection.close()

    summary: dict[str, object] = {
        "status": "registered",
        "project_id": args.project_id,
        "raw_root": str(raw_root),
        "documents": len(registered),
        "revision_ids": registered,
    }

    if normalize_plan is not None:
        # run_pipeline lee LlamaSettings del entorno; carga secrets como el CLI legacy.
        import shutil

        from ingestion.config.env import load_secrets_env
        from ingestion.pipeline import run_pipeline

        load_secrets_env(Path(args.env_file))
        # On-prem por defecto: los PDFs corporativos se parsean localmente (pdfium +
        # tesseract OCR), nunca se envían a LlamaParse cloud sin autorización explícita
        # (SECURITY_AND_DATA §3). `load_secrets_env` usa setdefault, así que forzamos
        # aquí para ganarle a un `LLAMA_CLOUD_ENABLED=true` heredado del entorno.
        if not args.allow_cloud:
            os.environ["LLAMA_CLOUD_ENABLED"] = "false"
        normalized_root = normalize_plan["normalized_root"]
        # promote=True exige un `staging_root` DISTINTO del root live: el pipeline
        # escribe/valida en staging y luego hace el swap atómico staging -> normalized
        # (renombra live a backup y copia). Sin staging, `output_root == normalized`
        # y `promote_candidate` mueve el candidate antes de copiarlo (FileNotFoundError).
        staging_root = normalized_root.parent / f".{normalized_root.name}.staging"
        if staging_root.exists():
            shutil.rmtree(staging_root)
        # promote=True: valida estructuralmente el árbol staged (gate de elegibilidad).
        # `--force` reprocesa aunque el hash no cambie: los manifests existentes son de
        # la lane legacy, así que hay que re-normalizar por el path de plataforma para
        # que la provenance quede sellada por este flujo, no heredada del legacy.
        try:
            pipeline_summary = run_pipeline(
                docs_raw=raw_root,
                docs_normalized=normalized_root,  # type: ignore[arg-type]
                staging_root=staging_root,
                promote=True,
                force=args.force,
                only_sources=args.only_source,
                corpus_version=args.corpus_version,
                pipeline_version=args.pipeline_version,
                platform_context_resolver=normalize_plan["resolver"],  # type: ignore[arg-type]
                request_id=f"platform_normalize_{args.project_id}",
            )
        finally:
            # El árbol staged ya se copió a normalized al promover; no dejar duplicado.
            if staging_root.exists():
                shutil.rmtree(staging_root)
        summary["status"] = "normalized"
        summary["rag_variant_id"] = normalize_plan["rag_variant_id"]
        summary["normalized_root"] = str(normalized_root)
        summary["normalize"] = pipeline_summary
        _emit(summary, as_json=args.json)
        # Fail-closed: un documento fallido no se reporta como éxito.
        return 1 if pipeline_summary.get("failed") else 0

    _emit(summary, as_json=args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
