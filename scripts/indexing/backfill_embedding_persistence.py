from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "app" / "back" / "src"))

from indexing.infrastructure.postgres.settings import PostgresIndexingSettings  # noqa: E402


VECTOR_TABLES = (
    "idx_vec_llama_first_local_v1",
    "idx_vec_local_bge_m3_v1",
    "idx_vec_llama_bge_m3_v1",
    "idx_vec_local_voyage_4_v1",
    "idx_vec_llama_voyage_4_v1",
    "idx_vec_local_cohere_embed_v4_v1",
    "idx_vec_llama_cohere_embed_v4_v1",
)

LEGACY_STATUSES = (
    "verified",
    "legacy_unverified",
    "compatibility_not_proven",
)


@dataclass(frozen=True)
class ChunkBundleLedgerRecord:
    """Filesystem chunk bundle identity safe to mirror into PostgreSQL."""

    chunk_bundle_id: str
    bundle_fingerprint: str
    profile_id: str
    profile_fingerprint: str
    corpus_version: str
    source_document_id: str
    artifact_relpath: str
    parent_count: int
    child_count: int
    status: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill bundle-first embedding/indexing persistence ledgers."
    )
    parser.add_argument("--chunks-root", default="data/chunks")
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    chunks_root = Path(args.chunks_root)
    if not args.apply:
        print(json.dumps(dry_run_summary(chunks_root=chunks_root), sort_keys=True))
        return 0

    settings = PostgresIndexingSettings.from_env(os.environ)
    if not settings.is_configured:
        print(
            json.dumps(
                {"status": "blocked", "reason": "postgres_dsn_missing"},
                sort_keys=True,
            )
        )
        return 2

    summary = apply_backfill(
        dsn=str(settings.dsn),
        chunks_root=chunks_root,
        batch_size=args.batch_size,
    )
    print(json.dumps(summary, sort_keys=True))
    return 0 if summary["status"] == "applied" else 1


def target_id_for_vector_table(vector_table: str) -> str:
    """Return the deterministic target id used by SQL migration backfills."""

    return f"target-{vector_table.replace('_', '-')}"


def collect_chunk_bundle_records(chunks_root: Path) -> list[ChunkBundleLedgerRecord]:
    """Collect persisted chunk bundle metadata without reading chunk text."""

    records: list[ChunkBundleLedgerRecord] = []
    root = chunks_root.resolve()
    for metadata_path in sorted(root.rglob("*.chunking_metadata.json")):
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        bundle_fingerprint = _required_text(payload, "bundle_fingerprint")
        records.append(
            ChunkBundleLedgerRecord(
                chunk_bundle_id=bundle_fingerprint,
                bundle_fingerprint=bundle_fingerprint,
                profile_id=_required_text(payload, "profile_id"),
                profile_fingerprint=_required_text(payload, "profile_fingerprint"),
                corpus_version=_required_text(payload, "corpus_version"),
                source_document_id=_required_text(payload, "document_id"),
                artifact_relpath=metadata_path.relative_to(root).as_posix(),
                parent_count=int(payload.get("parent_count") or 0),
                child_count=int(payload.get("child_count") or 0),
                status="legacy_unverified",
            )
        )
    return records


def dry_run_summary(*, chunks_root: Path) -> dict[str, object]:
    """Return the auditable work plan without touching PostgreSQL."""

    chunk_records = collect_chunk_bundle_records(chunks_root) if chunks_root.exists() else []
    return {
        "mode": "dry_run",
        "status": "planned",
        "chunk_bundles_found": len(chunk_records),
        "vector_tables": len(VECTOR_TABLES),
        "targets_to_backfill": [
            {
                "indexing_target_id": target_id_for_vector_table(vector_table),
                "postgres_schema": "public",
                "vector_table": vector_table,
            }
            for vector_table in VECTOR_TABLES
        ],
        "retrieval_profiles_activated": 0,
        "legacy_statuses": list(LEGACY_STATUSES),
    }


def apply_backfill(*, dsn: str, chunks_root: Path, batch_size: int) -> dict[str, object]:
    """Apply idempotent ledger backfills in bounded transactions."""

    import psycopg2
    from psycopg2.extras import execute_batch

    records = collect_chunk_bundle_records(chunks_root) if chunks_root.exists() else []
    connection = psycopg2.connect(dsn)
    chunks_registered = 0
    try:
        with connection:
            with connection.cursor() as cursor:
                _backfill_targets(cursor)
                _mark_legacy_profiles(cursor)

        for batch in _batches(records, batch_size):
            with connection:
                with connection.cursor() as cursor:
                    execute_batch(
                        cursor,
                        """
                        INSERT INTO chunk_bundles (
                            chunk_bundle_id, bundle_fingerprint, profile_id,
                            profile_fingerprint, corpus_version, source_document_id,
                            artifact_relpath, parent_count, child_count, status
                        )
                        VALUES (
                            %(chunk_bundle_id)s, %(bundle_fingerprint)s, %(profile_id)s,
                            %(profile_fingerprint)s, %(corpus_version)s, %(source_document_id)s,
                            %(artifact_relpath)s, %(parent_count)s, %(child_count)s, %(status)s
                        )
                        ON CONFLICT (chunk_bundle_id) DO UPDATE SET
                            bundle_fingerprint = EXCLUDED.bundle_fingerprint,
                            profile_id = EXCLUDED.profile_id,
                            profile_fingerprint = EXCLUDED.profile_fingerprint,
                            corpus_version = EXCLUDED.corpus_version,
                            source_document_id = EXCLUDED.source_document_id,
                            artifact_relpath = EXCLUDED.artifact_relpath,
                            parent_count = EXCLUDED.parent_count,
                            child_count = EXCLUDED.child_count,
                            status = EXCLUDED.status,
                            registered_at = now()
                        """,
                        [asdict(record) for record in batch],
                    )
                    chunks_registered += len(batch)
    finally:
        connection.close()

    return {
        "status": "applied",
        "chunk_bundles_registered": chunks_registered,
        "vector_tables": len(VECTOR_TABLES),
        "retrieval_profiles_activated": 0,
        "legacy_statuses": list(LEGACY_STATUSES),
    }


def _backfill_targets(cursor: object) -> None:
    cursor.execute(
        """
        INSERT INTO indexing_targets (
            indexing_target_id, postgres_schema, vector_table,
            distance_ops, storage_schema_version, active
        )
        SELECT
            'target-' || replace(profile.vector_table, '_', '-'),
            'public',
            profile.vector_table,
            CASE profile.distance_metric
                WHEN 'cosine' THEN 'vector_cosine_ops'
                WHEN 'l2' THEN 'vector_l2_ops'
                WHEN 'inner_product' THEN 'vector_ip_ops'
            END,
            'idx-vec-v1',
            profile.active
        FROM indexing_profiles AS profile
        ON CONFLICT (postgres_schema, vector_table) DO UPDATE SET
            distance_ops = EXCLUDED.distance_ops,
            storage_schema_version = EXCLUDED.storage_schema_version,
            active = EXCLUDED.active
        """
    )
    cursor.execute(
        """
        UPDATE indexing_profiles AS profile
           SET default_indexing_target_id = target.indexing_target_id
          FROM indexing_targets AS target
         WHERE target.postgres_schema = 'public'
           AND target.vector_table = profile.vector_table
           AND profile.default_indexing_target_id IS NULL
        """
    )


def _mark_legacy_profiles(cursor: object) -> None:
    cursor.execute(
        """
        UPDATE indexing_profiles
           SET compatibility_status = 'compatibility_not_proven',
               document_enabled = false,
               query_enabled = false
         WHERE compatibility_status <> 'verified'
        """
    )


def _required_text(payload: Mapping[str, object], key: str) -> str:
    value = str(payload.get(key) or "")
    if not value:
        raise ValueError(f"chunk bundle metadata is missing {key}")
    return value


def _batches(
    records: Sequence[ChunkBundleLedgerRecord],
    batch_size: int,
) -> Iterable[Sequence[ChunkBundleLedgerRecord]]:
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    for index in range(0, len(records), batch_size):
        yield records[index : index + batch_size]


if __name__ == "__main__":
    raise SystemExit(main())
