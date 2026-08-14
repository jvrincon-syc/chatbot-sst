"""Adaptador PostgreSQL del read-model de motores de embedding por proyecto.

Implementa ``ProjectEmbeddingEngineReader`` con un ``JOIN`` de
``embedding_bundles`` a ``indexing_materializations`` por
``(embedding_bundle_id, project_id)`` y un ``GROUP BY`` por la config semántica
del motor. Solo cuenta materializaciones **selladas** (``realmente
materializado``); las ``writing``/``failed`` no representan un artefacto usable.
El adaptador no emite DDL y parametriza siempre por ``project_id`` (nunca
interpola).
"""

from __future__ import annotations

from collections.abc import Sequence

from rag_platform.domain.engine_selection import ProjectEmbeddingEngine
from rag_platform.domain.models import MaterializationStatus

#: Columnas del read-model, en el mismo orden que el SELECT y el mapeo de filas.
_ENGINE_COLUMNS = (
    "configuration_fingerprint",
    "provider",
    "model",
    "model_revision",
    "dimension",
    "distance_metric",
    "normalization",
    "embedding_bundle_count",
    "materialization_count",
)

#: Solo un artefacto sellado cuenta como materializado (fail-closed).
_SEALED = MaterializationStatus.SEALED.value

_LIST_ENGINES_SQL = f"""
SELECT
    eb.configuration_fingerprint,
    eb.provider,
    eb.model,
    eb.model_revision,
    eb.dimension,
    eb.distance_metric,
    eb.normalization,
    COUNT(DISTINCT eb.embedding_bundle_id) AS embedding_bundle_count,
    COUNT(DISTINCT im.materialization_id) AS materialization_count
FROM embedding_bundles AS eb
JOIN indexing_materializations AS im
    ON im.embedding_bundle_id = eb.embedding_bundle_id
   AND im.project_id = eb.project_id
WHERE eb.project_id = %s
  AND im.status = %s
GROUP BY
    eb.configuration_fingerprint,
    eb.provider,
    eb.model,
    eb.model_revision,
    eb.dimension,
    eb.distance_metric,
    eb.normalization
ORDER BY eb.provider, eb.model, eb.dimension, eb.configuration_fingerprint
"""


class PostgresProjectEmbeddingEngineReader:
    """Lee los motores de embedding materializados de un proyecto."""

    def __init__(self, connection: object) -> None:
        self._connection = connection

    def list_for_project(
        self, project_id: str
    ) -> Sequence[ProjectEmbeddingEngine]:
        """Devuelve los motores con materialización sellada del proyecto."""

        with self._connection.cursor() as cursor:
            cursor.execute(_LIST_ENGINES_SQL, (project_id, _SEALED))
            rows = cursor.fetchall()
        return [_engine_from_row(row) for row in rows]


def _engine_from_row(row: Sequence[object]) -> ProjectEmbeddingEngine:
    """Valida una fila del read-model contra el contrato de dominio."""

    return ProjectEmbeddingEngine.model_validate(dict(zip(_ENGINE_COLUMNS, row)))
