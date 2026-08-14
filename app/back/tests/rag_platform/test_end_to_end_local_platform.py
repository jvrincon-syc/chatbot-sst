"""End-to-end local de la plataforma: raw -> normalize -> chunk -> embed -> index.

Prueba que ``project_id`` y ``rag_variant_id`` se propagan por toda la cadena, todo
**on-prem** (normalización local pdfium+tesseract, embedding BGE-M3 local), sobre el
proyecto sembrado ``proj_sst-general`` y su corpus real bajo
``data/projects/sst-general/raw``.

Flujo:

1. ``run_project_ingestion --normalize --force`` normaliza el corpus completo
   (``promote=True`` valida el árbol entero, por eso normaliza todo, no solo 3).
2. ``rebuild_platform --document <3 .md>`` encadena chunk -> embed (BGE) -> index ->
   materializa **solo para los 3 documentos de referencia** (.md, PDF de texto, PDF
   escaneado).
3. Se verifica en PostgreSQL que ``chunk_bundles``/``embedding_bundles``/
   ``indexing_materializations`` quedaron **propiedad del proyecto** y que el chunk
   bundle lleva la ``rag_variant_id`` como provenance.

Requiere corpus real + runtime BGE + PostgreSQL con el proyecto/variante sembrados
(``scripts/rag_platform/seed_project.py``). Marcado ``corpus``/``bge_runtime``/
``postgres_live``; el usuario lo corre con autorización explícita.

Uso:
    npm run python -- -m pytest app/back/tests/rag_platform/test_end_to_end_local_platform.py -v
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
_RAW_ROOT = _REPO_ROOT / "data" / "projects" / "sst-general" / "raw"
sys.path.insert(0, str(_REPO_ROOT / "scripts" / "indexing"))

_PROJECT_ID = "proj_sst-general"
_VARIANT_ID = "ragv_local-bge"

#: Los 3 documentos de referencia, como ``source_relpath`` **raw** (el filtro
#: ``--document`` de rebuild_platform resuelve raw relpath -> document_id vía inventario).
_MD = "convivencia_laboral/manual/introduccion.md"
_PDF_TEXTO = "convivencia_laboral/manual/1761580555950_syc_RE.RH-04SST23102025.pdf"
_PDF_ESCANEADO = "convivencia_laboral/manual/1781045303349_syc_politicadedesconexin.pdf"
_THREE_DOCS = (_MD, _PDF_TEXTO, _PDF_ESCANEADO)

#: Perfil de embedding y su tabla física de vectores (target materializado).
_EMBEDDING_PROFILE_ID = "local-bge-m3-v1"
_VECTOR_TABLE = "idx_vec_local_bge_m3_v1"
_TOP_K = 6
#: Preguntas de retrieval sobre el corpus de convivencia laboral (6, top_k=6).
_QUESTIONS = (
    "¿Qué es el comité de convivencia laboral?",
    "¿Cuáles son las funciones del comité de convivencia?",
    "¿En qué consiste la política de desconexión laboral?",
    "¿Cómo se presentan quejas o denuncias de convivencia?",
    "¿Qué normas de convivencia deben cumplir los trabajadores?",
    "¿Cuál es el objetivo del reglamento del comité de convivencia?",
)


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


def _write_retrieval_report(path: Path, *, results: list, facts: dict) -> None:
    """Escribe el reporte markdown de persistencia + retrieval del end-to-end."""

    lines: list[str] = [
        "# Reporte end-to-end plataforma RAG (local, BGE-M3)",
        "",
        f"- Generado: {facts['generated_at']}",
        f"- Proyecto: `{facts['project_id']}`",
        f"- Variante: `{facts['variant_id']}`",
        f"- Documentos: {', '.join(facts['documents'])}",
        "",
        "## Persistencia de identidad",
        "",
        f"- **project_id** `{facts['project_id']}`: PERSISTIDO — "
        f"{facts['chunk_total']} chunk_bundles, {facts['embedding_total']} embedding_bundles, "
        f"{facts['node_total']} indexing_nodes, {facts['vector_total']} vectores, "
        f"{facts['materializations']} materializaciones (todos namespaced por proyecto).",
        f"- **rag_variant_id** `{facts['variant_id']}`: PERSISTIDO (provenance) — "
        f"en {facts['chunk_variant']}/{facts['chunk_total']} chunk_bundles; "
        f"embedding_runs.rag_variant_id = {facts['run_variants']}.",
        f"- **rag_release_id**: {facts['release_value']} — {facts['release_note']}",
        "",
        "## Motor de embedding (recipe)",
        "",
        f"- provider `{facts['embedding']['provider']}` · model `{facts['embedding']['model']}` "
        f"· dimensión {facts['embedding']['dimension']} · métrica `{facts['embedding']['metric']}` "
        f"· normalización `{facts['embedding']['normalization']}`",
        f"- **Pinned por la variante** (provenance atada a `rag_variant_id`): "
        f"`rag_variants.embedding_profile_id` = `{facts['embedding']['profile_id']}`, "
        f"`configuration_fingerprint` del motor = `{facts['embedding']['configuration_fingerprint']}`, "
        f"congelado dentro de `semantic_recipe_fingerprint` = `{facts['variant_fingerprint']}`.",
        "- provider/model/**dimensión**/métrica/normalización entran al fingerprint del perfil "
        "(`EmbeddingProfile.expected_fingerprint`) y, vía este, al `semantic_recipe_fingerprint` "
        "de la variante (`recipe_service`). Cambiar cualquiera crea otra variante RAG. La "
        "dimensión NO es fija por el motor: BGE-M3 admite truncado Matryoshka (1024/768/512), "
        "así que es parámetro semántico libre y por eso viaja en el fingerprint.",
        "",
        f"## Retrieval — {len(results)} preguntas, top_k={facts['top_k']} "
        f"(vectores materializados, cosine, embedding de query BGE-M3)",
        "",
    ]
    for question, hits in results:
        lines.append(f"### {question}")
        lines.append("")
        lines.append("| # | score | rol | sección | chunk (snippet) |")
        lines.append("|---|-------|-----|---------|-----------------|")
        for rank, row in enumerate(hits, start=1):
            _node_id, _proj, role, section, snippet, score = row
            snippet = (snippet or "").replace("\n", " ").replace("|", "\\|")[:160]
            section = (section or "").replace("|", "\\|")
            lines.append(f"| {rank} | {score:.4f} | {role} | {section} | {snippet} |")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _clear_derived_artifacts(dsn: str) -> None:
    """Borra los artefactos derivados para que el end-to-end sea repetible.

    Reusar chunk/embed/index de una corrida previa hace que la materialización agregue
    conteos 0 (``child_node_count <= 0``) y falle fail-closed. Se limpian BD (chunk/
    embed/index/vectores/materializaciones) y filesystem del proyecto; se preservan
    raw, normalized, proyecto, variante y perfiles.
    """

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
    for name in ("chunks", "embeddings"):
        path = _REPO_ROOT / "data" / "projects" / "sst-general" / name
        if path.exists():
            shutil.rmtree(path)


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


@pytest.mark.corpus
@pytest.mark.bge_runtime
@pytest.mark.postgres_live
def test_end_to_end_local_propaga_project_y_variant(capsys) -> None:
    if not _RAW_ROOT.exists():
        pytest.skip(f"corpus ausente: {_RAW_ROOT}")
    dsn = _dsn()
    if not dsn:
        pytest.skip("sin DSN de PostgreSQL")
    if not _variant_seeded(dsn):
        pytest.skip(
            f"proyecto/variante no sembrados; corre scripts/rag_platform/seed_project.py"
        )

    # Slate limpio de derivados => corrida repetible (evita conteos 0 en materialización).
    _clear_derived_artifacts(dsn)

    ingestion_cli = _load(
        "run_project_ingestion_e2e", "scripts/rag_platform/run_project_ingestion.py"
    )
    rebuild_cli = _load("rebuild_platform_e2e", "scripts/rag_platform/rebuild_platform.py")

    # --- 1) normalize (corpus completo; promote valida el árbol entero) -----------
    rc_norm = ingestion_cli.main(
        [
            "--project-id", _PROJECT_ID,
            "--rag-variant-id", _VARIANT_ID,
            "--normalize", "--force",
        ]
    )
    assert rc_norm == 0, "la normalización no debe reportar documentos fallidos"

    # --- 2) chunk -> embed (BGE) -> index -> materializa, solo los 3 --------------
    documents_args: list[str] = []
    for relpath in _THREE_DOCS:
        documents_args += ["--document", relpath]
    capsys.readouterr()  # descarta la salida de la normalización
    # --force: run de chunking fresco (payload_fingerprint distinto -> run_id nuevo), para
    # ejercitar el path completo y no reusar un manifest previo.
    rc_rebuild = rebuild_cli.main(
        ["--project-id", _PROJECT_ID, "--rag-variant-id", _VARIANT_ID, "--force", *documents_args]
    )
    rebuild_out = capsys.readouterr().out.strip().splitlines()[-1]
    summary = json.loads(rebuild_out)
    assert rc_rebuild == 0, f"rebuild no materializó: {summary}"
    assert summary["status"] == "materialized"
    assert len(summary["materializations"]) >= 3

    # --- 3) PostgreSQL: los artefactos derivados son propiedad del proyecto -------
    connection = _connect(dsn)
    try:
        with connection.cursor() as cursor:
            # chunk_bundles: dueño del proyecto + provenance de variante.
            cursor.execute(
                "SELECT project_id, rag_variant_id FROM chunk_bundles"
                " WHERE project_id = %s",
                (_PROJECT_ID,),
            )
            chunk_rows = cursor.fetchall()
            assert len(chunk_rows) >= 3
            assert all(row[0] == _PROJECT_ID for row in chunk_rows)
            assert all(row[1] == _VARIANT_ID for row in chunk_rows)

            # embedding_bundles y materializaciones: namespaced por proyecto.
            cursor.execute(
                "SELECT DISTINCT project_id FROM embedding_bundles WHERE project_id = %s",
                (_PROJECT_ID,),
            )
            assert cursor.fetchone() is not None
            cursor.execute(
                "SELECT DISTINCT project_id FROM indexing_materializations"
                " WHERE project_id = %s",
                (_PROJECT_ID,),
            )
            assert cursor.fetchone() is not None

            # Ningún artefacto derivado quedó sin dueño (aislamiento pure-platform).
            for table in ("chunk_bundles", "embedding_bundles", "indexing_materializations"):
                cursor.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE project_id IS NULL"
                )
                assert int(cursor.fetchone()[0]) == 0, f"{table} tiene filas sin project_id"

        # --- 4) retrieval: preguntas con top_k sobre los vectores materializados ------
        # Los vectores de plataforma quedan inactivos (ADR-007), así que se consulta la
        # tabla física del target con pgvector (cosine) y una query embebida con BGE-M3
        # del mismo perfil; no se usa la lane de retrieval legacy (perfil activo).
        from datetime import datetime, timezone

        from embedding.application.engine_registry import DefaultEmbeddingEngineRegistry
        from embedding.infrastructure.postgres.repositories import (
            PostgresEmbeddingProfileRepository,
        )

        profile = PostgresEmbeddingProfileRepository(connection).get(_EMBEDDING_PROFILE_ID)
        query_engine = DefaultEmbeddingEngineRegistry().resolve_query_engine(profile)

        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT COUNT(*) FROM {_VECTOR_TABLE} WHERE project_id = %s",
                (_PROJECT_ID,),
            )
            total_vectors = int(cursor.fetchone()[0])
        assert total_vectors >= 1, "no hay vectores materializados para consultar"
        expected_hits = min(_TOP_K, total_vectors)

        results: list = []
        for question in _QUESTIONS:
            query_vector = query_engine.embed_queries([question])[0]
            literal = "[" + ",".join(repr(float(component)) for component in query_vector) + "]"
            with connection.cursor() as cursor:
                # ``_VECTOR_TABLE`` es un identificador constante del código (no entrada de
                # usuario); el vector y los filtros van parametrizados.
                cursor.execute(
                    f"SELECT v.node_id, v.project_id, n.node_role, n.section_title,"
                    f" left(n.text, 200), 1 - (v.embedding <=> %s::vector) AS score"
                    f" FROM {_VECTOR_TABLE} AS v"
                    f" JOIN indexing_nodes AS n ON n.node_id = v.node_id"
                    f" WHERE v.project_id = %s"
                    f" ORDER BY v.embedding <=> %s::vector"
                    f" LIMIT %s",
                    (literal, _PROJECT_ID, literal, _TOP_K),
                )
                hits = cursor.fetchall()
            assert len(hits) == expected_hits, f"{question!r}: {len(hits)} != {expected_hits}"
            assert all(row[1] == _PROJECT_ID for row in hits), "vector de otro proyecto"
            scores = [row[5] for row in hits]
            assert scores == sorted(scores, reverse=True), "resultados no ordenados por similitud"
            results.append((question, hits))

        # --- 5) reporte markdown de persistencia + retrieval ------------------------
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT count(*), count(*) FILTER (WHERE rag_variant_id = %s)"
                " FROM chunk_bundles WHERE project_id = %s",
                (_VARIANT_ID, _PROJECT_ID),
            )
            chunk_total, chunk_variant = cursor.fetchone()
            cursor.execute(
                "SELECT count(*) FROM embedding_bundles WHERE project_id = %s", (_PROJECT_ID,)
            )
            embedding_total = int(cursor.fetchone()[0])
            cursor.execute(
                "SELECT count(*) FROM indexing_nodes WHERE project_id = %s", (_PROJECT_ID,)
            )
            node_total = int(cursor.fetchone()[0])
            cursor.execute(
                "SELECT count(*) FROM indexing_materializations WHERE project_id = %s",
                (_PROJECT_ID,),
            )
            materializations = int(cursor.fetchone()[0])
            cursor.execute(
                "SELECT array_agg(DISTINCT rag_variant_id), array_agg(DISTINCT rag_release_id)"
                " FROM embedding_runs WHERE project_id = %s",
                (_PROJECT_ID,),
            )
            run_variants, run_releases = cursor.fetchone()
            # Provenance del motor: la config vive pineada en la variante, no en un
            # perfil global suelto que pueda derivar. Se lee el pin real desde
            # rag_variants y se confirma que apunta al perfil que reporta la config.
            cursor.execute(
                "SELECT embedding_profile_id, semantic_recipe_fingerprint"
                " FROM rag_variants WHERE rag_variant_id = %s",
                (_VARIANT_ID,),
            )
            variant_row = cursor.fetchone()
        assert variant_row is not None, "la variante no está sembrada en rag_variants"
        variant_embedding_profile_id, variant_fingerprint = variant_row
        assert variant_embedding_profile_id == _EMBEDDING_PROFILE_ID, (
            "la config del motor reportada no es la que la variante tiene pineada"
        )

        release_values = [value for value in (run_releases or []) if value is not None]
        facts = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "project_id": _PROJECT_ID,
            "variant_id": _VARIANT_ID,
            "documents": list(_THREE_DOCS),
            "top_k": _TOP_K,
            "chunk_total": int(chunk_total),
            "chunk_variant": int(chunk_variant),
            "embedding_total": embedding_total,
            "node_total": node_total,
            "vector_total": total_vectors,
            "materializations": materializations,
            "run_variants": [v for v in (run_variants or []) if v is not None] or None,
            "variant_fingerprint": variant_fingerprint,
            "embedding": {
                "provider": profile.provider,
                "model": profile.model,
                "dimension": profile.dimension,
                "metric": profile.distance_metric,
                "normalization": profile.normalization,
                "profile_id": _EMBEDDING_PROFILE_ID,
                "configuration_fingerprint": profile.expected_fingerprint().value,
            },
            "release_value": release_values or "NULL",
            "release_note": (
                "PERSISTIDO"
                if release_values
                else "NO persistido — este flujo (rebuild materializa artefactos físicos) no "
                "construye una release; el rag_release_id se crea en la fase de release "
                "(corpus snapshot + CreateDraft/Validate), pendiente con los 2 documentos extra."
            ),
        }
        _write_retrieval_report(
            _REPO_ROOT / "e2e_retrieval_report.md", results=results, facts=facts
        )
    finally:
        connection.close()
