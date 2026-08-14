"""Read-model de selección de motor de embedding materializado por proyecto.

Cubre el caso de uso (orden determinista, delegación scoped, validación y
autorización fail-closed) con un fake in-memory del puerto, y el adaptador
Postgres con un cursor de grabación al estilo de
``test_postgres_artifact_catalog_repositories``.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from rag_platform.application.engine_selection_service import (
    ListProjectEmbeddingEnginesUseCase,
)
from rag_platform.domain.engine_selection import ProjectEmbeddingEngine
from rag_platform.domain.errors import PlatformAccessDenied
from rag_platform.domain.identity import InvalidIdentity
from rag_platform.infrastructure.in_memory.repositories import AllowAllAccessPolicy
from rag_platform.infrastructure.postgres.engine_selection_repositories import (
    PostgresProjectEmbeddingEngineReader,
)


def _engine(
    *,
    fingerprint: str,
    provider: str = "local",
    model: str = "bge-m3",
    dimension: int = 1024,
    distance_metric: str = "cosine",
    bundles: int = 1,
    materializations: int = 1,
) -> ProjectEmbeddingEngine:
    return ProjectEmbeddingEngine(
        configuration_fingerprint=fingerprint,
        provider=provider,
        model=model,
        model_revision="2024.10",
        dimension=dimension,
        distance_metric=distance_metric,
        normalization="l2",
        embedding_bundle_count=bundles,
        materialization_count=materializations,
    )


class _FakeEngineReader:
    """Puerto in-memory: devuelve filas sin ordenar y registra el scope pedido."""

    def __init__(self, rows: Sequence[ProjectEmbeddingEngine]) -> None:
        self._rows = list(rows)
        self.requested_project_id: str | None = None

    def list_for_project(
        self, project_id: str
    ) -> Sequence[ProjectEmbeddingEngine]:
        self.requested_project_id = project_id
        return list(self._rows)


def _use_case(reader: _FakeEngineReader) -> ListProjectEmbeddingEnginesUseCase:
    return ListProjectEmbeddingEnginesUseCase(
        engines=reader, access_policy=AllowAllAccessPolicy()
    )


def test_devuelve_orden_determinista_cuando_puerto_entrega_filas_desordenadas() -> None:
    # Orden esperado: (provider, model, dimension, configuration_fingerprint).
    unsorted_rows = [
        _engine(fingerprint="c" * 64, provider="openai", model="text-embedding-3"),
        _engine(fingerprint="b" * 64, provider="local", model="bge-m3", dimension=1024),
        _engine(fingerprint="a" * 64, provider="local", model="bge-m3", dimension=512),
        _engine(fingerprint="a" * 63 + "d", provider="local", model="bge-m3", dimension=512),
    ]
    reader = _FakeEngineReader(unsorted_rows)

    result = _use_case(reader).execute(project_id="sst-general", actor_id="op")

    keys = [
        (e.provider, e.model, e.dimension, e.configuration_fingerprint) for e in result
    ]
    assert keys == sorted(keys)
    # El primer elemento es local/bge-m3/512 con el fingerprint menor
    # ("a"*64 < "a"*63+"d", desempate por configuration_fingerprint).
    assert result[0].provider == "local"
    assert result[0].dimension == 512
    assert result[0].configuration_fingerprint == "a" * 64


def test_delegra_project_id_canonico_cuando_recibe_slug() -> None:
    reader = _FakeEngineReader([])

    result = _use_case(reader).execute(project_id="sst-general", actor_id="op")

    assert result == ()
    # El caso de uso pasa el valor canónico ``proj_<slug>`` al puerto.
    assert reader.requested_project_id == "proj_sst-general"


def test_rechaza_cuando_project_id_vacio() -> None:
    reader = _FakeEngineReader([])

    with pytest.raises(InvalidIdentity):
        _use_case(reader).execute(project_id="   ", actor_id="op")

    # Fail-closed: ni siquiera se consultó el puerto.
    assert reader.requested_project_id is None


def test_rechaza_cuando_actor_no_autorizado() -> None:
    reader = _FakeEngineReader([_engine(fingerprint="a" * 64)])

    with pytest.raises(PlatformAccessDenied):
        _use_case(reader).execute(project_id="sst-general", actor_id="")

    assert reader.requested_project_id is None


# --------------------------------------------------------------------------- #
# Adaptador Postgres                                                           #
# --------------------------------------------------------------------------- #


def test_adaptador_arma_join_group_by_y_solo_selladas() -> None:
    row = (
        "a" * 64,
        "local",
        "bge-m3",
        "2024.10",
        1024,
        "cosine",
        "l2",
        3,
        5,
    )
    connection = RecordingConnection([row])
    reader = PostgresProjectEmbeddingEngineReader(connection)

    engines = reader.list_for_project("proj_sst-general")

    statement = connection.cursor_obj.statements[0]
    params = connection.cursor_obj.params[0]
    assert "JOIN indexing_materializations" in statement
    assert "im.embedding_bundle_id = eb.embedding_bundle_id" in statement
    assert "im.project_id = eb.project_id" in statement
    assert "GROUP BY" in statement
    assert "eb.configuration_fingerprint" in statement
    assert "WHERE eb.project_id = %s" in statement
    assert "im.status = %s" in statement
    assert "ORDER BY" in statement
    # Parametrizado: proyecto + estado sellado, nunca interpolado.
    assert params == ("proj_sst-general", "sealed")
    # La fila se valida contra el contrato de dominio.
    assert len(engines) == 1
    assert engines[0].configuration_fingerprint == "a" * 64
    assert engines[0].embedding_bundle_count == 3
    assert engines[0].materialization_count == 5


class RecordingConnection:
    def __init__(self, rows: Sequence[tuple[object, ...]]) -> None:
        self.cursor_obj = RecordingCursor(rows)

    def cursor(self) -> "RecordingCursor":
        return self.cursor_obj


class RecordingCursor:
    def __init__(self, rows: Sequence[tuple[object, ...]]) -> None:
        self._rows = list(rows)
        self.statements: list[str] = []
        self.params: list[tuple[object, ...]] = []

    def __enter__(self) -> "RecordingCursor":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> bool:
        return False

    def execute(self, statement: str, params: tuple[object, ...]) -> None:
        self.statements.append(statement)
        self.params.append(params)

    def fetchall(self) -> list[tuple[object, ...]]:
        return list(self._rows)
