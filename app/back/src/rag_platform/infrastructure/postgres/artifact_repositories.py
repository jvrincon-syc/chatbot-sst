"""PostgreSQL adapters for sealed chunk bundles and the build ledger (Fase 3).

This module reflects the schema frozen by migration ``20260810_04`` (additive over
legacy) and never issues DDL, mirroring the Fase 1/2 adapters. It does **not**
touch the legacy chunk-bundle writer (``embedding...PostgresChunkBundleRepository``);
platform rows are registered here with the new project-ownership columns and
``sealing_status = 'sealed'``.

Deuda conocida (Fase 4/5): ``chunk_bundles.source_document_id`` conserva su FK a
``indexing_normalized_documents`` mientras la unicidad global no se retire. Un row
de plataforma cuyo normalizado vive en ``project_normalized_documents`` requiere que
esa FK se relaje/redirija en una fase posterior; esta fase solo añade columnas y un
índice único parcial, sin alterar la FK legacy. Estos adaptadores no se ejecutan en
unit tests (se prueban con fakes in-memory); reflejan el SQL para el entorno real.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
import uuid

from embedding.domain.models import ChunkBundleRef
from rag_platform.domain.errors import (
    BuildStepNotFound,
    CrossProjectLegacyFingerprintCollision,
)
from rag_platform.domain.identity import IdentityKind, PlatformId, RagBuildContext
from rag_platform.domain.models import (
    BuildOutcome,
    BuildStage,
    RagBuildStep,
    ReuseKind,
    SealingStatus,
)


def _pid(kind: IdentityKind, value: str) -> PlatformId:
    return PlatformId(kind=kind, value=value)


def _is_unique_violation(error: Exception) -> bool:
    """Best-effort detection of a PostgreSQL unique-violation (SQLSTATE 23505).

    Mirrors ``project_repositories._is_unique_violation``: reads
    ``sqlstate``/``pgcode`` and falls back to the class name, staying driver-agnostic
    without importing the SDK here.
    """

    sqlstate = getattr(error, "sqlstate", None) or getattr(error, "pgcode", None)
    if sqlstate == "23505":
        return True
    return type(error).__name__ == "UniqueViolation"


class PostgresSealedChunkBundleRepository:
    """Registra y consulta filas de ``chunk_bundles`` propiedad de un proyecto.

    Complementa el sellado en filesystem (``SealedChunkStore``): la fila-ledger
    lleva las columnas nuevas de identidad física (§4.4) además de los campos
    legacy que la tabla exige. No modifica el writer legacy.
    """

    def __init__(self, connection: object) -> None:
        self._connection = connection

    def register_sealed_bundle(
        self,
        bundle: ChunkBundleRef,
        *,
        project_id: PlatformId,
        normalized_document_id: str,
        chunking_profile_fingerprint: str,
        bundle_schema_version: str,
    ) -> ChunkBundleRef:
        """Inserta o confirma la fila sellada por su identidad física exacta.

        Idempotente por identidad del bundle: ``ON CONFLICT (chunk_bundle_id)
        DO NOTHING`` (la PK). El índice único parcial ``uq_chunk_bundles_physical_identity``
        además protege la identidad física §4.4 para filas de plataforma.

        Deuda declarada (Fase 4): la unicidad global legacy
        ``chunk_bundles_bundle_fingerprint_key`` sigue vigente, así que dos proyectos
        que sellen bundles con **bytes idénticos** (mismo ``bundle_fingerprint``)
        chocan con una ``UniqueViolation`` cruda en esta lane Postgres —el aislamiento
        por proyecto para contenido idéntico entre proyectos solo se cumple cuando
        Fase 4 retire esa unicidad global. La lane in-memory (fakes) no expone este
        límite; la paridad fake↔Postgres para ese caso no debe darse por supuesta.
        """

        try:
            with self._connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO chunk_bundles (
                        chunk_bundle_id, bundle_fingerprint, profile_id,
                        profile_fingerprint, corpus_version, source_document_id,
                        artifact_relpath, parent_count, child_count, status,
                        project_id, normalized_document_id,
                        chunking_profile_fingerprint, bundle_schema_version,
                        sealing_status
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s)
                    ON CONFLICT (chunk_bundle_id) DO NOTHING
                    """,
                    (
                        bundle.chunk_bundle_id,
                        bundle.bundle_fingerprint,
                        bundle.profile_id,
                        bundle.profile_fingerprint,
                        bundle.corpus_version,
                        bundle.source_document_id,
                        bundle.artifact_relpath,
                        bundle.parent_count,
                        bundle.child_count,
                        bundle.status,
                        project_id.value,
                        normalized_document_id,
                        chunking_profile_fingerprint,
                        bundle_schema_version,
                        SealingStatus.SEALED.value,
                    ),
                )
        except Exception as error:  # noqa: BLE001 — borde de integración; se re-lanza
            # Fail-closed (ADR-007 §9): la unicidad global legacy sobre
            # ``bundle_fingerprint`` sigue vigente en Fase 4. Dos proyectos con bytes
            # idénticos colisionan; se traduce a un error de dominio y NUNCA se reutiliza,
            # renombra ni borra el artefacto del otro proyecto. Otras violaciones se
            # re-lanzan intactas preservando la causa.
            if _is_unique_violation(error):
                raise CrossProjectLegacyFingerprintCollision(
                    "bundle_fingerprint collides with another project's sealed bundle: "
                    f"{bundle.bundle_fingerprint}"
                ) from error
            raise
        return bundle

    def find_sealed(
        self,
        *,
        project_id: PlatformId,
        normalized_document_id: str,
        chunking_profile_fingerprint: str,
        bundle_schema_version: str,
    ) -> ChunkBundleRef | None:
        """Devuelve el bundle sellado con la identidad física exacta, o ``None``."""

        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT chunk_bundle_id, bundle_fingerprint, profile_id,
                       profile_fingerprint, corpus_version, source_document_id,
                       artifact_relpath, parent_count, child_count, status
                FROM chunk_bundles
                WHERE project_id = %s
                  AND normalized_document_id = %s
                  AND chunking_profile_fingerprint = %s
                  AND bundle_schema_version = %s
                  AND sealing_status = %s
                """,
                (
                    project_id.value,
                    normalized_document_id,
                    chunking_profile_fingerprint,
                    bundle_schema_version,
                    SealingStatus.SEALED.value,
                ),
            )
            row = cursor.fetchone()
        return None if row is None else self._row_to_ref(row)

    @staticmethod
    def _row_to_ref(row: Sequence[object]) -> ChunkBundleRef:
        return ChunkBundleRef(
            chunk_bundle_id=str(row[0]),
            bundle_fingerprint=str(row[1]),
            profile_id=str(row[2]),
            profile_fingerprint=str(row[3]),
            corpus_version=str(row[4]),
            source_document_id=str(row[5]),
            artifact_relpath=str(row[6]),
            parent_count=int(row[7]),  # type: ignore[arg-type]
            child_count=int(row[8]),  # type: ignore[arg-type]
            status=str(row[9]),  # type: ignore[arg-type]
        )


class PostgresRagBuildRunRepository:
    """Ledger durable de runs y pasos de build (``rag_build_runs``/``_steps``)."""

    def __init__(self, connection: object) -> None:
        self._connection = connection

    def start_step(
        self, *, context: RagBuildContext, stage: BuildStage
    ) -> RagBuildStep:
        """Abre un paso bajo el run de la release (get-or-create del run)."""

        run_id = f"rbr_{context.rag_release_id.value}"
        step_id = f"rbs_{uuid.uuid4().hex}"
        started_at = datetime.now(timezone.utc)
        with self._connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO rag_build_runs"
                " (rag_build_run_id, rag_release_id, project_id, created_at)"
                " VALUES (%s, %s, %s, %s)"
                " ON CONFLICT (rag_build_run_id) DO NOTHING",
                (
                    run_id,
                    context.rag_release_id.value,
                    context.project_id.value,
                    started_at,
                ),
            )
            cursor.execute(
                "INSERT INTO rag_build_steps"
                " (rag_build_step_id, rag_build_run_id, stage, started_at)"
                " VALUES (%s, %s, %s, %s)",
                (step_id, run_id, stage.value, started_at),
            )
        return RagBuildStep(
            step_id=step_id,
            rag_build_run_id=run_id,
            rag_release_id=context.rag_release_id,
            project_id=context.project_id,
            stage=stage,
            started_at=started_at,
        )

    def complete_step(
        self,
        *,
        step_id: str,
        outcome: BuildOutcome,
        reuse_kind: ReuseKind | None = None,
        source_artifact_id: str | None = None,
    ) -> RagBuildStep:
        """Cierra un paso con su resultado y clasificación de reuso opcional."""

        completed_at = datetime.now(timezone.utc)
        with self._connection.cursor() as cursor:
            cursor.execute(
                "UPDATE rag_build_steps SET outcome = %s, reuse_kind = %s,"
                " source_artifact_id = %s, completed_at = %s"
                " WHERE rag_build_step_id = %s"
                " RETURNING rag_build_run_id, stage, started_at",
                (
                    outcome.value,
                    None if reuse_kind is None else reuse_kind.value,
                    source_artifact_id,
                    completed_at,
                    step_id,
                ),
            )
            row = cursor.fetchone()
            if row is None:
                # Fail-closed: step inexistente => error de dominio, no TypeError.
                raise BuildStepNotFound(step_id)
            cursor.execute(
                "SELECT rag_release_id, project_id FROM rag_build_runs"
                " WHERE rag_build_run_id = %s",
                (str(row[0]),),
            )
            run_row = cursor.fetchone()
        return RagBuildStep(
            step_id=step_id,
            rag_build_run_id=str(row[0]),
            rag_release_id=_pid(IdentityKind.RAG_RELEASE, str(run_row[0])),
            project_id=_pid(IdentityKind.PROJECT, str(run_row[1])),
            stage=BuildStage(str(row[1])),
            outcome=outcome,
            reuse_kind=reuse_kind,
            source_artifact_id=source_artifact_id,
            started_at=row[2],  # type: ignore[arg-type]
            completed_at=completed_at,
        )
