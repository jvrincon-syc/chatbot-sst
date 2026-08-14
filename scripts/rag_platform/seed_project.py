"""Seeder de proyecto + variante RAG para desbloquear el end-to-end (dev).

Crea, de forma **idempotente**, la cadena mínima que exige una corrida
`raw -> normalize -> chunk -> embed -> index -> materializa`:

1. proyecto (`CreateProjectUseCase`) con la allowlist de embedding + target binding;
2. perfil de procesamiento y de chunking del proyecto (INSERT directo: no hay caso
   de uso de creación; son filas de catálogo/receta);
3. variante RAG (`CreateRagVariantUseCase`) que fija la receta semántica.

Reusa los perfiles de embedding **globales** ya seedeados por las migraciones
(`indexing_profiles`); no crea tablas ni motores. Los ids se derivan de
``IdentityKind`` para no hardcodear prefijos.

Fail-closed: sin DSN aborta. Re-ejecutable: si el proyecto/variante ya existen, los
respeta y reporta ``exists`` en vez de duplicar.

Uso:
    npm run python -- scripts/rag_platform/seed_project.py \
        --project-slug sst-general --variant-slug local_bge \
        --embedding-profile-id local-bge-m3-v1
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Sequence

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "app" / "back" / "src"))
sys.path.insert(0, str(_REPO_ROOT / "scripts" / "indexing"))

from prepare_postgres_indexing import build_dsn_from_env, load_env_file  # noqa: E402

from rag_platform.application.project_service import (  # noqa: E402
    CreateProjectRequest,
    CreateProjectUseCase,
)
from rag_platform.application.recipe_service import (  # noqa: E402
    CreateRagVariantRequest,
    CreateRagVariantUseCase,
)
from rag_platform.domain.errors import (  # noqa: E402
    DuplicateVariantRecipe,
    ProjectAlreadyExists,
)
from rag_platform.domain.identity import IdentityKind  # noqa: E402
from rag_platform.domain.models import (  # noqa: E402
    ProjectEmbeddingProfile,
    ProjectIndexingTargetBinding,
)
from rag_platform.infrastructure.in_memory.repositories import (  # noqa: E402
    AllowAllAccessPolicy,
)
from rag_platform.infrastructure.postgres.project_repositories import (  # noqa: E402
    PostgresChunkingProfileRepository,
    PostgresProcessingProfileRepository,
    PostgresProjectRepository,
    PostgresRagVariantRepository,
    PostgresTargetBindingResolver,
)
from rag_platform.infrastructure.storage.project_storage import (  # noqa: E402
    ProjectStorageResolver,
)

_ACTOR = "seed-operator"
#: Clave lógica del binding (allowlist) que la variante referencia; nunca un
#: ``indexing_target_id`` directo (invariante §1/§7 del plan).
_BINDING_KEY = "primary"


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-slug", default="sst-general")
    parser.add_argument("--display-name", default="SST General")
    parser.add_argument(
        "--variant-slug",
        default="local-bge",
        help="Slug de la variante; solo [a-z0-9-] (sin guion bajo).",
    )
    parser.add_argument(
        "--embedding-profile-id",
        default="local-bge-m3-v1",
        help="Perfil de embedding global seedeado (indexing_profiles.profile_id).",
    )
    parser.add_argument(
        "--indexing-target-id",
        default="target-idx-vec-local-bge-m3-v1",
        help="Target global compatible con el perfil de embedding.",
    )
    parser.add_argument("--processing-slug", default="local")
    parser.add_argument("--processing-provider", default="local")
    parser.add_argument("--processing-engine", default="pdfium-tesseract")
    parser.add_argument("--processing-revision", default="2026.08")
    parser.add_argument("--chunking-slug", default="structural")
    parser.add_argument("--chunking-strategy", default="structural")
    parser.add_argument("--env-file", default="secrets.env")
    parser.add_argument("--data-dir", default=str(_REPO_ROOT / "data"))
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def _fingerprint(*parts: str) -> str:
    """Digest determinista de 64 hex para la identidad de un perfil de receta."""

    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


def _upsert_profile_rows(
    cursor: object,
    *,
    project_id_value: str,
    processing_id: str,
    chunking_id: str,
    args: argparse.Namespace,
) -> tuple[str, str]:
    """Inserta (idempotente) el perfil de procesamiento y de chunking del proyecto.

    No hay caso de uso de creación para estas recetas; son filas de catálogo con
    fingerprint inmutable. ``ON CONFLICT DO NOTHING`` hace el seeder re-ejecutable.
    Devuelve ``(processing_fingerprint, chunking_fingerprint)``.
    """

    processing_fp = _fingerprint(
        "processing",
        args.processing_provider,
        args.processing_engine,
        args.processing_revision,
    )
    chunking_fp = _fingerprint("chunking", args.chunking_strategy)
    cursor.execute(
        "INSERT INTO document_processing_profiles (processing_profile_id, project_id,"
        " provider, engine, observed_revision, origin, sanitized_config_json,"
        " fingerprint, status)"
        " VALUES (%s, %s, %s, %s, %s, 'local', '{}'::jsonb, %s, 'verified')"
        " ON CONFLICT (processing_profile_id) DO NOTHING",
        (
            processing_id,
            project_id_value,
            args.processing_provider,
            args.processing_engine,
            args.processing_revision,
            processing_fp,
        ),
    )
    cursor.execute(
        "INSERT INTO chunking_profiles (chunking_profile_id, project_id, strategy,"
        " sanitized_config_json, fingerprint, status)"
        " VALUES (%s, %s, %s, '{}'::jsonb, %s, 'verified')"
        " ON CONFLICT (chunking_profile_id) DO NOTHING",
        (chunking_id, project_id_value, args.chunking_strategy, chunking_fp),
    )
    return processing_fp, chunking_fp


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)

    dsn = build_dsn_from_env(dict(load_env_file(Path(args.env_file))))
    if not dsn:
        print(json.dumps({"status": "blocked", "reason": "postgres_dsn_missing"}))
        return 2

    project_id_value = f"{IdentityKind.PROJECT.value}_{args.project_slug}"
    processing_id = f"{IdentityKind.PROCESSING_PROFILE.value}_{args.processing_slug}"
    chunking_id = f"{IdentityKind.CHUNKING_PROFILE.value}_{args.chunking_slug}"
    variant_id_value = f"{IdentityKind.RAG_VARIANT.value}_{args.variant_slug}"

    import psycopg2
    from psycopg2.extensions import parse_dsn

    storage = ProjectStorageResolver(Path(args.data_dir))
    access = AllowAllAccessPolicy()

    connection = psycopg2.connect(**parse_dsn(dsn))
    summary: dict[str, object] = {
        "project_id": project_id_value,
        "rag_variant_id": variant_id_value,
        "embedding_profile_id": args.embedding_profile_id,
        "indexing_target_id": args.indexing_target_id,
        "binding_key": _BINDING_KEY,
    }
    try:
        with connection:  # una sola transacción atómica para toda la cadena
            with connection.cursor() as cursor:
                # 1) Proyecto con allowlist de embedding + target binding.
                project_use_case = CreateProjectUseCase(
                    projects=PostgresProjectRepository(connection),
                    storage_roots=storage,
                    access_policy=access,
                )
                try:
                    project_use_case.execute(
                        CreateProjectRequest(
                            project_slug=args.project_slug,
                            display_name=args.display_name,
                            embedding_profiles=(
                                ProjectEmbeddingProfile(
                                    embedding_profile_id=args.embedding_profile_id,
                                    enabled=True,
                                ),
                            ),
                            target_bindings=(
                                ProjectIndexingTargetBinding(
                                    binding_key=_BINDING_KEY,
                                    indexing_target_id=args.indexing_target_id,
                                    embedding_profile_id=args.embedding_profile_id,
                                ),
                            ),
                        ),
                        actor_id=_ACTOR,
                    )
                    summary["project"] = "created"
                except ProjectAlreadyExists:
                    # exists() chequea antes de insertar: la transacción sigue sana.
                    summary["project"] = "exists"

                # 2) Perfiles de receta (INSERT idempotente).
                _upsert_profile_rows(
                    cursor,
                    project_id_value=project_id_value,
                    processing_id=processing_id,
                    chunking_id=chunking_id,
                    args=args,
                )
                summary["processing_profile_id"] = processing_id
                summary["chunking_profile_id"] = chunking_id

                # 3) Variante RAG (receta semántica inmutable).
                variant_use_case = CreateRagVariantUseCase(
                    variants=PostgresRagVariantRepository(connection),
                    processing_profiles=PostgresProcessingProfileRepository(connection),
                    chunking_profiles=PostgresChunkingProfileRepository(connection),
                    target_bindings=PostgresTargetBindingResolver(connection),
                    access_policy=access,
                )
                try:
                    variant = variant_use_case.execute(
                        CreateRagVariantRequest(
                            variant_slug=args.variant_slug,
                            project_id=args.project_slug,
                            processing_profile_id=args.processing_slug,
                            chunking_profile_id=args.chunking_slug,
                            embedding_profile_id=args.embedding_profile_id,
                            target_binding_key=_BINDING_KEY,
                        ),
                        actor_id=_ACTOR,
                    )
                    summary["variant"] = "created"
                    summary["semantic_recipe_fingerprint"] = (
                        variant.semantic_recipe_fingerprint
                    )
                except DuplicateVariantRecipe:
                    # find_active_by_fingerprint chequea antes de insertar.
                    summary["variant"] = "exists"
    finally:
        connection.close()

    summary["status"] = "seeded"
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
