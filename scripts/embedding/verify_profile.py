"""Explicitly verify and enable one durable embedding profile.

The backfill left every legacy profile ``compatibility_not_proven`` with both
enablement flags false. Nothing promotes them implicitly: this script is the
explicit verification process. It observes a real engine, proves every semantic
field, persists a ``readiness_checks`` row and only then flips the flags.

Usage::

    npm run embedding:verify-profile -- --profile-id local-bge-m3-v1 --dry-run
    npm run embedding:verify-profile -- --profile-id local-bge-m3-v1 --apply

``--attested-model-revision`` is only accepted for engines that cannot report a
revision themselves (for example the Voyage API). It is recorded in the
readiness report as an operator attestation, never as an engine observation.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "app" / "back" / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "indexing"))

from prepare_postgres_indexing import (  # noqa: E402
    build_dsn_from_env,
    load_env_file,
)

from embedding.application.engine_registry import (  # noqa: E402
    DefaultEmbeddingEngineRegistry,
)
from embedding.application.profile_verification import (  # noqa: E402
    ProfileVerificationRequest,
    VerifyEmbeddingProfileCompatibilityUseCase,
)
from embedding.domain.errors import EmbeddingProfileNotFound  # noqa: E402
from embedding.infrastructure.in_memory.repositories import (  # noqa: E402
    InMemoryReadinessCheckRepository,
)
from embedding.infrastructure.postgres.repositories import (  # noqa: E402
    PostgresEmbeddingProfileRepository,
    PostgresIndexingTargetRepository,
    PostgresReadinessCheckRepository,
)
from indexing.infrastructure.postgres.settings import (  # noqa: E402
    PostgresIndexingSettings,
)


class _ReadOnlyProfileRepository:
    """Wrap the durable repository so a dry-run can never promote a profile."""

    def __init__(self, delegate: PostgresEmbeddingProfileRepository) -> None:
        self._delegate = delegate

    def get(self, profile_id: str):
        """Return one profile."""

        return self._delegate.get(profile_id)

    def list_profiles(self):
        """Return every profile."""

        return self._delegate.list_profiles()

    def mark_verified(
        self,
        *,
        profile_id: str,
        configuration_fingerprint: str,
        model_revision: str,
        document_enabled: bool,
        query_enabled: bool,
    ):
        """Return the promotion a dry-run would perform, without writing it."""

        return self._delegate.get(profile_id).model_copy(
            update={
                "compatibility_status": "verified",
                "configuration_fingerprint": configuration_fingerprint,
                "model_revision": model_revision,
                "document_enabled": document_enabled,
                "query_enabled": query_enabled,
            }
        )


def parse_args() -> argparse.Namespace:
    """Parse the command line."""

    parser = argparse.ArgumentParser(
        description="Verify and enable one durable embedding profile."
    )
    parser.add_argument("--profile-id", required=True)
    parser.add_argument("--attested-model-revision", default=None)
    parser.add_argument("--enable-documents", action="store_true", default=True)
    parser.add_argument("--no-enable-documents", dest="enable_documents", action="store_false")
    parser.add_argument("--enable-queries", action="store_true", default=True)
    parser.add_argument("--no-enable-queries", dest="enable_queries", action="store_false")
    parser.add_argument("--allow-mock-engine", action="store_true")
    parser.add_argument("--env-file", default="secrets.env")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--dry-run", dest="apply", action="store_false")
    return parser.parse_args()


def main() -> int:
    """Run one verification and print a sanitized JSON report."""

    args = parse_args()
    settings = PostgresIndexingSettings.from_env(os.environ)
    if not settings.is_configured:
        # secrets.env carries POSTGRES_* / DATABASE_URL, not SST_POSTGRES_DSN, so
        # the documented npm command would otherwise always report dsn_missing.
        env_path = Path(args.env_file)
        if not env_path.is_absolute():
            env_path = ROOT / env_path
        settings = PostgresIndexingSettings(dsn=build_dsn_from_env(load_env_file(env_path)))
    if not settings.is_configured:
        print(json.dumps({"status": "blocked", "reason": "postgres_dsn_missing"}, sort_keys=True))
        return 2

    import psycopg2
    from psycopg2.extras import RealDictCursor

    connection = psycopg2.connect(str(settings.dsn), cursor_factory=RealDictCursor)
    try:
        durable_profiles = PostgresEmbeddingProfileRepository(connection)
        profiles = durable_profiles if args.apply else _ReadOnlyProfileRepository(durable_profiles)
        checks = (
            PostgresReadinessCheckRepository(connection)
            if args.apply
            else InMemoryReadinessCheckRepository()
        )
        use_case = VerifyEmbeddingProfileCompatibilityUseCase(
            profiles=profiles,
            registry=DefaultEmbeddingEngineRegistry(allow_mock=args.allow_mock_engine),
            targets=PostgresIndexingTargetRepository(connection),
            readiness_checks=checks,
        )
        try:
            result = use_case.execute(
                ProfileVerificationRequest(
                    profile_id=args.profile_id,
                    attested_model_revision=args.attested_model_revision,
                    enable_documents=args.enable_documents,
                    enable_queries=args.enable_queries,
                )
            )
        except EmbeddingProfileNotFound:
            print(
                json.dumps(
                    {"status": "failed", "reason": "EMBEDDING_PROFILE_NOT_FOUND"},
                    sort_keys=True,
                )
            )
            return 1
        if args.apply:
            connection.commit()
    finally:
        connection.close()

    print(
        json.dumps(
            {
                "mode": "apply" if args.apply else "dry_run",
                "profile_id": result.profile_id,
                "status": "verified" if result.passed else "blocked",
                "revision_source": result.revision_source,
                "checks": [check.model_dump() for check in result.checks],
                "document_enabled": result.profile.document_enabled,
                "query_enabled": result.profile.query_enabled,
            },
            sort_keys=True,
        )
    )
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
