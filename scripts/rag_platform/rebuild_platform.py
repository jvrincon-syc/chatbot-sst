"""CLI de rebuild pure-platform (Fase 4, Stage 3).

Encadena la lane de plataforma estampando ``project_id`` de raw a indexing
(ADR-008), reusando los servicios existentes; no reimplementa pipeline.

Etapas:
  1. **chunk** — ``ChunkingRunService`` (vía ``build_run_service_from_env`` con
     ``project_id``) registra cada ``chunk_bundles`` con su dueño de proyecto.
  2. **embed** — ``CreateEmbeddingRunUseCase`` + executor (BGE vivo); el bundle
     hereda ``project_id`` del chunk bundle (``bundle_builder``).
  3. **index + materializa** — ``RebuildPlatformArtifactsUseCase`` indexa
     bundle-first (nodos físicos + vectores inactivos, namespaced por proyecto) y
     sella la materialización. Deriva checksum/dimensión/métrica server-side.

Las etapas dejan los vectores **inactivos** (ADR-007 §8): el CLI no activa
retrieval ni toca ``is_active``/``retrieval_profiles``.

Rutas por proyecto (aislamiento, master plan §2.1): ``normalized``/``chunks``/
``embeddings`` se derivan del catálogo del proyecto vía ``ProjectStorageResolver``
(``data/projects/{slug}/...``), no de rutas legacy.

Uso:
    npm run python -- scripts/rag_platform/rebuild_platform.py \
        --project-id proj_sst-general --rag-variant-id ragv_local_bge
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "app" / "back" / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "indexing"))

from core.logging.logger import configure_structured_logging  # noqa: E402
from prepare_postgres_indexing import build_dsn_from_env, load_env_file  # noqa: E402


logger = logging.getLogger(__name__)


def parse_args(argv: "list[str] | None" = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-id", required=True)
    parser.add_argument(
        "--rag-variant-id",
        default=None,
        help="Variante opcional; su receta y perfil de embedding se derivan server-side.",
    )
    parser.add_argument(
        "--embedding-profile-id",
        default=None,
        help="Perfil de embedding explícito cuando no se pasa --rag-variant-id.",
    )
    # Overrides opcionales; por defecto las raíces se derivan del proyecto.
    parser.add_argument("--docs-normalized", default=None)
    parser.add_argument("--chunks-root", default=None)
    parser.add_argument("--embeddings-root", default=None)
    parser.add_argument("--document", action="append", default=[])
    parser.add_argument("--profile", default="local-structural-v1")
    parser.add_argument("--scope", default="platform-rebuild")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--env-file", default="secrets.env")
    return parser.parse_args(argv)


#: Centinela: el contexto no resolvió (proyecto/variante inexistente), fail-closed.
_CONTEXT_BLOCKED = object()


@dataclass(frozen=True)
class _ResolvedContext:
    """Contexto derivado server-side: proyecto, variante y perfil de embedding."""

    project: object  # RagProject
    rag_variant_id: str | None
    semantic_recipe_fingerprint: str | None
    embedding_profile_id: str | None


def _resolve_context(
    *, dsn: str, project_id: str, rag_variant_id: str | None, embedding_profile_id: str | None
):
    """Resuelve project + variante server-side; deriva receta y perfil de embedding.

    Devuelve un ``_ResolvedContext`` o ``(_CONTEXT_BLOCKED, blocked_payload)`` si el
    proyecto o la variante no existen.
    """

    import psycopg2
    from psycopg2.extensions import parse_dsn

    from rag_platform.domain.errors import ProjectNotFound, RagVariantNotFound
    from rag_platform.domain.identity import IdentityKind, PlatformId
    from rag_platform.infrastructure.postgres.project_repositories import (
        PostgresProjectRepository,
        PostgresRagVariantRepository,
    )

    connection = psycopg2.connect(**parse_dsn(dsn))
    try:
        try:
            project = PostgresProjectRepository(connection).get(
                PlatformId(kind=IdentityKind.PROJECT, value=project_id)
            )
        except ProjectNotFound:
            return _CONTEXT_BLOCKED, {
                "status": "blocked",
                "reason": "project_not_found",
                "project_id": project_id,
            }
        if rag_variant_id is None:
            return _ResolvedContext(
                project=project,
                rag_variant_id=None,
                semantic_recipe_fingerprint=None,
                embedding_profile_id=embedding_profile_id,
            )
        try:
            variant = PostgresRagVariantRepository(connection).get(
                PlatformId(kind=IdentityKind.RAG_VARIANT, value=rag_variant_id)
            )
        except RagVariantNotFound:
            return _CONTEXT_BLOCKED, {
                "status": "blocked",
                "reason": "rag_variant_not_found",
                "rag_variant_id": rag_variant_id,
            }
        # La variante manda: su perfil de embedding es autoridad (ADR-005 global).
        return _ResolvedContext(
            project=project,
            rag_variant_id=variant.rag_variant_id.value,
            semantic_recipe_fingerprint=variant.semantic_recipe_fingerprint,
            embedding_profile_id=variant.embedding_profile_id,
        )
    finally:
        connection.close()


def main(argv: "list[str] | None" = None) -> int:
    configure_structured_logging(stream=sys.stderr, include_file_handler=False)
    args = parse_args(argv)

    # Pure-platform escribe en Postgres con project_id NOT NULL: exige DSN.
    env = load_env_file(Path(args.env_file))
    dsn = build_dsn_from_env(env)
    if not dsn:
        print(json.dumps({"status": "blocked", "reason": "postgres_dsn_missing"}, sort_keys=True))
        return 2
    os.environ["SST_POSTGRES_DSN"] = dsn
    os.environ["SST_PERSISTENCE_MODE"] = "postgres"
    # La lane de plataforma (incl. rag_platform_rebuild) se cablea tras este flag.
    os.environ["SST_FEATURE_RAG_PLATFORM_V1"] = "true"

    resolved = _resolve_context(
        dsn=dsn,
        project_id=args.project_id,
        rag_variant_id=args.rag_variant_id,
        embedding_profile_id=args.embedding_profile_id,
    )
    if isinstance(resolved, tuple) and resolved[0] is _CONTEXT_BLOCKED:
        print(json.dumps(resolved[1], sort_keys=True))
        return 2

    if resolved.embedding_profile_id is None:
        # Fail-closed: sin variante ni perfil explícito no se puede embeder.
        print(
            json.dumps(
                {"status": "blocked", "reason": "embedding_profile_unresolved"},
                sort_keys=True,
            )
        )
        return 2

    # Raíces por proyecto (no legacy); overrides opcionales por bandera.
    from rag_platform.domain.identity import IdentityKind, PlatformId
    from rag_platform.infrastructure.storage.project_storage import ProjectStorageResolver

    resolver = ProjectStorageResolver(base_dir=ROOT / "data")
    project = resolved.project
    normalized_root = (
        Path(args.docs_normalized)
        if args.docs_normalized
        else resolver.resolve_declared_root(project, "normalized")
    )
    chunks_root = (
        Path(args.chunks_root)
        if args.chunks_root
        else resolver.resolve_declared_root(project, "chunks")
    )
    embeddings_root = (
        Path(args.embeddings_root)
        if args.embeddings_root
        else resolver.resolve_declared_root(project, "embeddings")
    )

    documents = tuple(args.document) or _discover_documents(normalized_root)
    if not documents:
        print(json.dumps({"status": "blocked", "reason": "no_documents"}, sort_keys=True))
        return 2

    # --- Etapa 1: chunk -----------------------------------------------------
    from chunking.api.dependencies import build_run_service_from_env
    from chunking.application.run_service import ChunkingRunRequest

    chunk_service = build_run_service_from_env(
        docs_normalized=normalized_root,
        chunks_root=chunks_root,
        project_id=args.project_id,
    )
    state = chunk_service.create_run(
        request=ChunkingRunRequest(
            scope=args.scope,
            document_ids=documents,
            profile_id=args.profile,
            force=args.force,
        ),
        idempotency_key=f"platform-chunk-{args.project_id}-{args.scope}",
    )
    chunk_service.execute_run(state.run_id)
    chunk_final = chunk_service.get_run_state(state.run_id)
    chunk_bundle_ids = [
        str(document.get("bundle_fingerprint"))
        for document in chunk_final.documents
        if document.get("bundle_fingerprint")
    ]

    summary: dict[str, object] = {
        "project_id": args.project_id,
        "rag_variant_id": resolved.rag_variant_id,
        "semantic_recipe_fingerprint": resolved.semantic_recipe_fingerprint,
        "chunk_run_id": chunk_final.run_id,
        "requested_documents": chunk_final.requested_documents,
        "completed_documents": chunk_final.completed_documents,
        "chunk_bundles": chunk_bundle_ids,
        "warnings": chunk_final.warnings,
    }
    if chunk_final.status == "failed" or not chunk_bundle_ids:
        summary["status"] = "failed" if chunk_final.status == "failed" else "chunked"
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
        return 1 if chunk_final.status == "failed" else 0

    # --- Etapas 2-3: embed -> index -> materializa --------------------------
    from api.dependencies import build_pipeline_services_from_env
    from embedding.application.run_service import CreateEmbeddingRunRequest
    from rag_platform.application.rebuild_orchestrator import PlatformBuildContext

    services = build_pipeline_services_from_env(
        chunks_root=chunks_root, embeddings_root=embeddings_root
    )
    try:
        rebuild = services.rag_platform_rebuild
        if rebuild is None:
            # La materialización sella en Postgres; sin conexión no aplica.
            summary["status"] = "blocked"
            summary["reason"] = "postgres_required_for_materialization"
            print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
            return 2

        context = PlatformBuildContext(
            project_id=PlatformId(IdentityKind.PROJECT, args.project_id),
            rag_variant_id=(
                PlatformId(IdentityKind.RAG_VARIANT, resolved.rag_variant_id)
                if resolved.rag_variant_id
                else None
            ),
        )

        embedding_bundles: list[str] = []
        materializations: list[dict[str, object]] = []
        for chunk_bundle_id in chunk_bundle_ids:
            run = services.embedding_create_run.execute(
                request=CreateEmbeddingRunRequest(
                    chunk_bundle_id=chunk_bundle_id,
                    profile_id=resolved.embedding_profile_id,
                    project_id=args.project_id,
                    rag_variant_id=resolved.rag_variant_id,
                ),
                idempotency_key=f"platform-embed-{args.project_id}-{chunk_bundle_id}",
            )
            completed = services.embedding_executor.execute(run.embedding_run_id)
            embedding_bundle_id = completed.produced_embedding_bundle_id
            if embedding_bundle_id is None:
                summary["status"] = "failed"
                summary["reason"] = "embedding_produced_no_bundle"
                summary["embedding_bundles"] = embedding_bundles
                print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
                return 1
            embedding_bundles.append(str(embedding_bundle_id))

            result = rebuild.execute(
                context=context,
                embedding_bundle_id=str(embedding_bundle_id),
                idempotency_key=f"platform-rebuild-{args.project_id}-{embedding_bundle_id}",
            )
            materializations.append(
                {
                    "materialization_id": result.materialization.materialization_id,
                    "embedding_bundle_id": result.embedding_bundle_id,
                    "indexing_target_id": result.indexing_target_id,
                    "status": result.materialization.status.value,
                }
            )
    finally:
        services.close()

    summary["status"] = "materialized"
    summary["embedding_bundles"] = embedding_bundles
    summary["materializations"] = materializations
    logger.info(
        "platform_rebuild_completed",
        extra={
            "project_id": args.project_id,
            "chunk_bundles": len(chunk_bundle_ids),
            "materializations": len(materializations),
        },
    )
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


def _discover_documents(docs_root: Path) -> tuple[str, ...]:
    if not docs_root.exists():
        return ()
    return tuple(
        sorted(
            path.relative_to(docs_root).as_posix()
            for path in docs_root.rglob("*.md")
            if "_manifests" not in path.parts
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
