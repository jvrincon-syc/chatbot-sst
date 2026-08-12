"""CLI de rebuild pure-platform (Fase 4, Stage 3 — scaffold).

Encadena la lane de plataforma estampando ``project_id`` de raw a indexing
(ADR-008). Reusa los servicios existentes; no reimplementa pipeline.

Etapa implementada:
  1. **chunk** — ``ChunkingRunService`` (vía ``build_run_service_from_env`` con
     ``project_id``) registra cada ``chunk_bundles`` con su dueño de proyecto.

Etapas siguientes (pendientes, requieren BGE vivo + wiring de materialización en
el composition root, ver `plans/2026-08-11-fase4-embedding-nodos-vectores.md`
Stage 3):
  2. **embed** — ``CreateEmbeddingRunUseCase`` + executor (BGE); el bundle hereda
     ``project_id`` del chunk bundle (bundle_builder).
  3. **index** — ``CreateIndexingRunUseCase`` + executor (nodos físicos + vectores
     inactivos, namespaced por proyecto).
  4. **materializa** — ``RebuildPlatformArtifactsUseCase`` (materialización sellada).

Uso:
    npm run python -- scripts/rag_platform/rebuild_platform.py --project-id proj_xxx
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "app" / "back" / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "indexing"))

from core.logging.logger import configure_structured_logging  # noqa: E402
from prepare_postgres_indexing import build_dsn_from_env, load_env_file  # noqa: E402


logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--docs-normalized", default="data/docs_normalized")
    parser.add_argument("--chunks-root", default="data/chunks")
    parser.add_argument("--document", action="append", default=[])
    parser.add_argument("--profile", default="local-structural-v1")
    parser.add_argument("--scope", default="platform-rebuild")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--env-file", default="secrets.env")
    return parser.parse_args()


def main() -> int:
    configure_structured_logging(stream=sys.stderr, include_file_handler=False)
    args = parse_args()

    # Pure-platform escribe en Postgres con project_id NOT NULL: exige DSN.
    env = load_env_file(Path(args.env_file))
    dsn = build_dsn_from_env(env)
    if not dsn:
        print(json.dumps({"status": "blocked", "reason": "postgres_dsn_missing"}, sort_keys=True))
        return 2
    os.environ["SST_POSTGRES_DSN"] = dsn
    os.environ["SST_PERSISTENCE_MODE"] = "postgres"

    # Import diferido: build_run_service_from_env lee os.environ ya configurado.
    from chunking.api.dependencies import build_run_service_from_env
    from chunking.application.run_service import ChunkingRunRequest

    docs_normalized = Path(args.docs_normalized)
    documents = tuple(args.document) or _discover_documents(docs_normalized)
    if not documents:
        print(json.dumps({"status": "blocked", "reason": "no_documents"}, sort_keys=True))
        return 2

    service = build_run_service_from_env(
        docs_normalized=docs_normalized,
        chunks_root=Path(args.chunks_root),
        project_id=args.project_id,
    )
    state = service.create_run(
        request=ChunkingRunRequest(
            scope=args.scope,
            document_ids=documents,
            profile_id=args.profile,
            force=args.force,
        ),
        idempotency_key=f"platform-chunk-{args.project_id}-{args.scope}",
    )
    service.execute_run(state.run_id)
    final = service.get_run_state(state.run_id)

    summary = {
        "status": "chunked",
        "project_id": args.project_id,
        "run_id": final.run_id,
        "requested_documents": final.requested_documents,
        "completed_documents": final.completed_documents,
        "chunk_bundles": [
            {"chunk_bundle_id": document.get("bundle_fingerprint"), "document_id": document.get("document_id")}
            for document in final.documents
        ],
        "warnings": final.warnings,
        # Etapas embed/index/materializa aún no cableadas en este CLI.
        "next_stages": ["embed", "index", "materialize"],
    }
    logger.info(
        "platform_rebuild_chunk_completed",
        extra={"project_id": args.project_id, "completed": final.completed_documents},
    )
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0 if final.status != "failed" else 1


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
