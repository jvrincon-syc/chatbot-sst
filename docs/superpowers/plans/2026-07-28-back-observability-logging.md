# Backend Observability Logging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make backend ingestion, chunking, indexing, and API/server transitions visible in the terminal during `npm run api`, with structured info/warning/error logs, state transitions, edge-case diagnostics, and timing metrics, without changing business logic.

**Architecture:** Use a console-first structured logging contract shared by the backend entrypoint, ingestion pipeline, chunking workflow, and indexing workflow. Keep domain validation pure and emit logs at orchestration, adapter, and HTTP boundaries where we can attach context and classify recoverable vs fatal errors. File-backed runtime logs should stop being the primary operator surface.

**Tech Stack:** Python 3.12 `logging`, JSON structured events, pytest, the existing HTTP server in `app/back/src/ingestion/gui/server.py`, ingestion and indexing application services, and the `npm` script wrapper in `package.json`.

## Global Constraints

- `Usar Python \`>=3.12,<3.13\`, salvo ADR explicito.`
- `Usar type hints para todos los parametros, atributos publicos y valores de retorno.`
- `Usar logs estructurados.`
- `Incluir \`run_id\`, \`document_id\`, \`job_id\`, capability, proveedor, version y estado cuando aplique.`
- `Metricas y logs deben permitir reconstruir el recorrido del documento.`
- `No usar \`print\` en codigo de aplicacion.`
- `No registrar API keys, tokens, URLs firmadas ni contenido corporativo completo.`
- `No silenciar excepciones con pass.`

## Current Evidence

- `package.json` exposes `gui:api` and `gui:dev`, but there is no `api` alias yet.
- `app/back/src/core/logging/logger.py` already sends INFO+ to stdout and WARNING+ to `logs/app.log`.
- `app/back/src/ingestion/logging/jsonl.py` currently writes run details to `_manifests/*_details.log`.
- `app/back/src/ingestion/pipeline.py` already logs document start/finish/fail, but not run start/end, validation, promotion, or timing metrics.
- `app/back/src/ingestion/application/services/llama_orchestrator.py` already logs Llama phase start/finish/failure, but not a final lane summary or explicit duration fields.
- `app/back/src/ingestion/gui/server.py` still uses `print` for startup and HTTP access logs.
- `app/back/src/chunking/application/run_service.py` has partial lifecycle logs, while `chunking_orchestrator.py`, `structural_parser.py`, `parent_chunk_builder.py`, and `child_chunk_builder.py` only cover a subset of the chunking story.
- `app/back/src/indexing/application/use_cases/index_document.py` is currently silent, and the indexing infrastructure only logs at the CLI wrappers in `scripts/indexing/*.py`.

## Logging Decision

- Option A: keep file-backed runtime logs as the main operator surface and mirror them to stdout.
- Option B: make stdout the primary runtime surface and keep file persistence opt-in for audit/debug only.
- Choice: Option B. The operator wants live terminal visibility, and the existing manifests already preserve durable evidence.

## File Structure

- Create: `app/back/src/core/logging/observability.py`
- Modify: `app/back/src/core/logging/logger.py`
- Modify: `app/back/src/ingestion/logging/jsonl.py`
- Modify: `package.json`
- Modify: `README.md`
- Modify: `app/back/src/ingestion/pipeline.py`
- Modify: `app/back/src/ingestion/application/services/llama_orchestrator.py`
- Modify: `app/back/src/ingestion/gui/server.py`
- Modify: `app/back/src/chunking/application/run_service.py`
- Modify: `app/back/src/chunking/application/chunking_orchestrator.py`
- Modify: `app/back/src/chunking/application/structural_parser.py`
- Modify: `app/back/src/chunking/application/parent_chunk_builder.py`
- Modify: `app/back/src/chunking/application/child_chunk_builder.py`
- Modify: `app/back/src/ingestion/gui/chunking_adapter.py`
- Modify: `app/back/src/chunking/api/router.py`
- Modify: `app/back/src/indexing/application/use_cases/index_document.py`
- Modify: `app/back/src/indexing/application/profile_orchestrator.py`
- Modify: `app/back/src/indexing/infrastructure/llama_index/pipeline_factory.py`
- Modify: `app/back/src/indexing/infrastructure/embeddings/base.py`
- Modify: `app/back/src/indexing/infrastructure/postgres/node_repository.py`
- Modify: `app/back/src/indexing/infrastructure/postgres/normalized_document_repository.py`
- Modify: `app/back/src/indexing/infrastructure/postgres/vector_repository.py`

---

### Task 1: Shared Structured Logging Contract

**Files:**
- Create: `app/back/src/core/logging/observability.py`
- Modify: `app/back/src/core/logging/logger.py`
- Modify: `app/back/src/ingestion/logging/jsonl.py`
- Modify: `package.json`
- Modify: `README.md`
- Test: `app/back/tests/core/test_logging.py`
- Test: `app/back/tests/core/test_observability.py`
- Modify: `app/back/tests/ingestion/test_pipeline_integration.py`

**Interfaces:**
- Produces: `emit_structured_event(logger, *, level, event, stage, status, message, run_id=None, document_id=None, job_id=None, source_path=None, provider=None, capability=None, phase=None, from_state=None, to_state=None, duration_ms=None, warning_count=None, warning_code=None, error_code=None, exception=None, extra=None) -> None`
- Produces: `timed_structured_event(...)` context manager for start/end logs with `duration_ms`
- Produces: `JsonlLogger.event(...)` payloads that land in stdout instead of a mandatory text file

- [ ] **Step 1: Write the failing tests**

```python
import json

from core.logging.logger import get_logger
from ingestion.logging.jsonl import JsonlLogger


def test_backend_logger_emits_json_to_stdout_and_stays_file_free_by_default(
    tmp_path,
    capsys,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    logger = get_logger("tests.logging.stdout")
    logger.info(
        "pipeline_run_started",
        extra={"run_id": "run_1", "stage": "ingestion", "status": "started"},
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["run_id"] == "run_1"
    assert payload["stage"] == "ingestion"
    assert payload["status"] == "started"
    assert not (tmp_path / "logs" / "app.log").exists()


def test_jsonl_logger_emits_live_event_payload_to_stdout(tmp_path, capsys):
    logger = JsonlLogger(tmp_path / "unused.log", "run_2")
    logger.event(
        stage="reading",
        event="document_start",
        status="started",
        message="Processing document",
        document_id="doc_123",
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["run_id"] == "run_2"
    assert payload["document_id"] == "doc_123"
    assert payload["event"] == "document_start"
```

- [ ] **Step 2: Run the tests and confirm the current behavior fails**

Run: `npm run python -- -m pytest app/back/tests/core/test_logging.py app/back/tests/core/test_observability.py app/back/tests/ingestion/test_pipeline_integration.py::test_pipeline_writes_llama_phase_events_to_details_log -q`
Expected: FAIL because the logger still prefers file sinks and the pipeline test still reads `_details.log`.

- [ ] **Step 3: Implement the minimal logging contract**

Make `core.logging.logger.get_logger()` default to stdout-only structured output, with file persistence behind an explicit opt-in flag. Refactor `JsonlLogger` to reuse the same structured payload and stop being the mandatory file sink.

Update `package.json` so `npm run api` becomes a friendly alias for `npm run gui:api`, and document the alias plus the stdout-first logging behavior in `README.md`.

- [ ] **Step 4: Run the tests and confirm the new contract passes**

Run:

```bash
npm run python -- -m pytest app/back/tests/core/test_logging.py app/back/tests/core/test_observability.py app/back/tests/ingestion/test_pipeline_integration.py::test_pipeline_writes_llama_phase_events_to_details_log -q
```

Expected: PASS, with the pipeline test now reading live stdout JSON events.

- [ ] **Step 5: Commit**

```bash
git add app/back/src/core/logging/observability.py app/back/src/core/logging/logger.py app/back/src/ingestion/logging/jsonl.py package.json README.md app/back/tests/core/test_logging.py app/back/tests/core/test_observability.py app/back/tests/ingestion/test_pipeline_integration.py
git commit -m "feat(logging): make backend events terminal-visible"
```

---

### Task 2: Ingestion Pipeline And GUI Server Observability

**Files:**
- Modify: `app/back/src/ingestion/pipeline.py`
- Modify: `app/back/src/ingestion/application/services/llama_orchestrator.py`
- Modify: `app/back/src/ingestion/gui/server.py`
- Test: `app/back/tests/ingestion/test_pipeline_integration.py`
- Test: `app/back/tests/ingestion/test_server_observability.py`

**Interfaces:**
- Produces: `run_pipeline(...)` logs for `pipeline_run_started`, `inventory_loaded`, `document_selected`, `document_skipped`, `document_read_started`, `document_read_finished`, `document_write_started`, `document_write_finished`, `validation_started`, `validation_finished`, `promotion_started`, `promotion_finished`, `pipeline_run_completed`
- Produces: `LlamaOrchestrator._log_phase_event(...)` payloads with `duration_ms`, `warning_count`, `from_state`, and `to_state` where applicable
- Produces: `Phase1GuiHandler` startup, request, and error logs instead of raw `print` calls

- [ ] **Step 1: Write the failing tests**

```python
import json

from ingestion.pipeline import run_pipeline


def test_pipeline_logs_run_boundaries_and_failures(tmp_path, capsys):
    docs_raw = tmp_path / "data" / "docs_raw"
    docs_normalized = tmp_path / "data" / "docs_normalized"
    docs_raw.mkdir(parents=True)
    (docs_raw / "manual.md").write_text("# Manual\n\nContenido", encoding="utf-8")

    run_pipeline(
        docs_raw=docs_raw,
        docs_normalized=docs_normalized,
        corpus_version="test",
        pipeline_version="1.0.0",
        run_id="run_test",
    )

    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert any(event["event"] == "pipeline_run_started" for event in events)
    assert any(event["event"] == "pipeline_run_completed" for event in events)
    assert any("duration_ms" in event for event in events)
```

Add a second server test that exercises an invalid request body and confirms the handler emits a structured `warning` or `error` log with `exception_type="ValueError"` or `exception_type="TypeError"`.

- [ ] **Step 2: Run the tests and confirm they fail today**

Run: `npm run python -- -m pytest app/back/tests/ingestion/test_pipeline_integration.py app/back/tests/ingestion/test_server_observability.py -q`
Expected: FAIL because the pipeline and GUI server still miss the boundary logs and metrics.

- [ ] **Step 3: Add phase, state, and timing logs**

In `pipeline.py`, log the run start, inventory size, skipped or reprocessed documents, fallback paths, validation summary, and final promotion result. In `llama_orchestrator.py`, keep the existing phase start/finish events but add duration fields and a final lane summary so the live terminal stream shows the full parse/classify/extract story.

In `server.py`, replace `print` with a structured logger for startup/shutdown, upload success/failure, review decisions, pipeline runs, validation requests, promotion requests, settings updates, chunking bridge failures, and request/response timing.

Keep `ValueError`, `TypeError`, `JSONDecodeError`, and other edge cases visible at the boundary where they are translated into HTTP status codes.

- [ ] **Step 4: Run the tests and confirm the new pipeline/server logs pass**

Run:

```bash
npm run python -- -m pytest app/back/tests/ingestion/test_pipeline_integration.py app/back/tests/ingestion/test_server_observability.py -q
```

Expected: PASS, and the stdout stream should show structured run/phase/state/timing logs.

- [ ] **Step 5: Commit**

```bash
git add app/back/src/ingestion/pipeline.py app/back/src/ingestion/application/services/llama_orchestrator.py app/back/src/ingestion/gui/server.py app/back/tests/ingestion/test_pipeline_integration.py app/back/tests/ingestion/test_server_observability.py
git commit -m "feat(ingestion): expose pipeline and api lifecycle logs"
```

---

### Task 3: Chunking Workflow Observability

**Files:**
- Modify: `app/back/src/chunking/application/run_service.py`
- Modify: `app/back/src/chunking/application/chunking_orchestrator.py`
- Modify: `app/back/src/chunking/application/structural_parser.py`
- Modify: `app/back/src/chunking/application/parent_chunk_builder.py`
- Modify: `app/back/src/chunking/application/child_chunk_builder.py`
- Modify: `app/back/src/ingestion/gui/chunking_adapter.py`
- Modify: `app/back/src/chunking/api/router.py`
- Test: `app/back/tests/chunking/integration/test_run_service_persistence.py`
- Test: `app/back/tests/chunking/api/test_chunking_api.py`
- Test: `app/back/tests/chunking/unit/test_structural_parser.py`
- Test: `app/back/tests/chunking/unit/test_parent_chunk_builder.py`
- Test: `app/back/tests/chunking/unit/test_child_chunk_builder.py`

**Interfaces:**
- Produces: `chunking_run_created`, `chunking_run_submitted`, `chunking_run_started`, `chunking_document_completed`, `chunking_run_completed`, `chunking_run_failed`, `chunking_run_reused`, `chunking_idempotency_conflict`, `chunking_manifest_skipped`, and `chunking_gui_bridge_failed`
- Produces: chunking state transition logs with `from_state` and `to_state`
- Produces: structural parsing logs with `region_count`, `block_count`, `section_count`, `parent_count`, `child_count`, and table/form warnings

- [ ] **Step 1: Write the failing tests**

```python
import json

from chunking.application.run_service import ChunkingRunRequest


def test_chunking_run_logs_queue_start_finish_and_duration(tmp_path, capsys):
    service = build_chunking_service(tmp_path)
    state = service.create_run(
        request=ChunkingRunRequest(
            scope="documents",
            document_ids=("doc_1",),
            profile_id="local-structural-v1",
            force=False,
        ),
        idempotency_key="idem-1",
    )
    service.execute_run(state.run_id)

    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert any(event["event"] == "chunking_run_created" for event in events)
    assert any(event["event"] == "chunking_run_started" for event in events)
    assert any(event["event"] == "chunking_run_completed" for event in events)
    assert any(event.get("duration_ms") is not None for event in events)
```

Add one failure-path test that reuses an idempotency key with a different payload and asserts the warning log contains `chunking_idempotency_conflict` before the exception is raised.

- [ ] **Step 2: Run the tests and confirm they fail today**

Run: `npm run python -- -m pytest app/back/tests/chunking/integration/test_run_service_persistence.py app/back/tests/chunking/api/test_chunking_api.py app/back/tests/chunking/unit/test_structural_parser.py app/back/tests/chunking/unit/test_parent_chunk_builder.py app/back/tests/chunking/unit/test_child_chunk_builder.py -q`
Expected: FAIL because the chunking workflow still omits several lifecycle logs and timings.

- [ ] **Step 3: Add chunking lifecycle and boundary logs**

Instrument the service and builders so the live terminal stream shows when a run is created, queued, submitted, started, interrupted, reused, completed, or failed; when each document starts and finishes chunking; when the orchestrator reuses or persists a bundle; when the parser sees structural regions or page-trace resolution fails; and when parent and child builders emit counts, table warnings, and zero-overlap reasons.

Keep the logs structured and bounded. Do not dump full chunk bodies; only log counts, ids, selected profile, and warning codes.

- [ ] **Step 4: Run the tests and confirm the new chunking logs pass**

Run:

```bash
npm run python -- -m pytest app/back/tests/chunking/integration/test_run_service_persistence.py app/back/tests/chunking/api/test_chunking_api.py app/back/tests/chunking/unit/test_structural_parser.py app/back/tests/chunking/unit/test_parent_chunk_builder.py app/back/tests/chunking/unit/test_child_chunk_builder.py -q
```

Expected: PASS, with transition logs visible on stdout.

- [ ] **Step 5: Commit**

```bash
git add app/back/src/chunking/application/run_service.py app/back/src/chunking/application/chunking_orchestrator.py app/back/src/chunking/application/structural_parser.py app/back/src/chunking/application/parent_chunk_builder.py app/back/src/chunking/application/child_chunk_builder.py app/back/src/ingestion/gui/chunking_adapter.py app/back/src/chunking/api/router.py app/back/tests/chunking
git commit -m "feat(chunking): add structured lifecycle logging"
```

---

### Task 4: Indexing Workflow Observability

**Files:**
- Modify: `app/back/src/indexing/application/use_cases/index_document.py`
- Modify: `app/back/src/indexing/application/profile_orchestrator.py`
- Modify: `app/back/src/indexing/infrastructure/llama_index/pipeline_factory.py`
- Modify: `app/back/src/indexing/infrastructure/embeddings/base.py`
- Modify: `app/back/src/indexing/infrastructure/postgres/node_repository.py`
- Modify: `app/back/src/indexing/infrastructure/postgres/normalized_document_repository.py`
- Modify: `app/back/src/indexing/infrastructure/postgres/vector_repository.py`
- Test: `app/back/tests/indexing/test_index_document_use_case.py`
- Test: `app/back/tests/indexing/application/test_profile_orchestrator.py`
- Test: `app/back/tests/indexing/infrastructure/test_ingestion_pipeline.py`
- Test: `app/back/tests/indexing/infrastructure/postgres/test_vector_repository_contract.py`
- Test: `app/back/tests/indexing/test_run_indexing_cli.py`
- Test: `app/back/tests/indexing/test_validate_index_cli.py`

**Interfaces:**
- Produces: `indexing_run_started`, `indexing_run_completed`, `indexing_run_failed`, `index_cache_hit`, `profile_resolved`, `profile_rejected`, `embedding_provider_selected`, `embedding_batch_built`, `postgres_replace_started`, `postgres_replace_completed`, `rollback_applied`, `vector_dimension_mismatch`, and `indexing_rejected`
- Produces: indexing state and durability logs that include `profile_id`, `ingestion_origin`, `chunking_version`, `embedding_provider`, `embedding_model`, `embedding_dimension`, `vector_table`, `indexed_parent_nodes`, `indexed_child_nodes`, and `deleted_stale_nodes`

- [ ] **Step 1: Write the failing tests**

```python
import json

from indexing.application.use_cases.index_document import IndexDocumentUseCase


def test_index_document_use_case_logs_rejection_and_success(tmp_path, capsys):
    use_case = build_index_use_case(tmp_path)
    approved_document = build_indexable_document(document_status="processed")
    rejected_document = build_indexable_document(document_status="needs_review")

    with pytest.raises(IndexingRejectedError):
        await use_case.index(rejected_document)

    await use_case.index(approved_document)
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert any(event["event"] == "indexing_rejected" for event in events)
    assert any(event["event"] == "indexing_run_completed" for event in events)
```

Add a second test that forces a profile mismatch or embedding-dimension error and asserts the log includes `profile_rejected` or `vector_dimension_mismatch` instead of silently failing.

- [ ] **Step 2: Run the tests and confirm they fail today**

Run: `npm run python -- -m pytest app/back/tests/indexing/test_index_document_use_case.py app/back/tests/indexing/application/test_profile_orchestrator.py app/back/tests/indexing/infrastructure/test_ingestion_pipeline.py app/back/tests/indexing/infrastructure/postgres/test_vector_repository_contract.py app/back/tests/indexing/test_run_indexing_cli.py app/back/tests/indexing/test_validate_index_cli.py -q`
Expected: FAIL because the indexing application and infrastructure still omit several boundary logs and duration fields.

- [ ] **Step 3: Add indexing lifecycle, profile, embedding, and repository logs**

Instrument the indexing path so the terminal shows when a document is accepted, rejected, skipped, or cache-hit; when a profile is resolved, rejected, inactive, or lane-mismatched; when embeddings are requested; when the LlamaIndex pipeline creates documents/nodes; and when postgres repositories replace normalized documents, nodes, or vectors.

Keep `ValueError` and `TypeError` visible at the boundary that makes the decision, but do not pollute pure domain code with logging.

- [ ] **Step 4: Run the tests and confirm the new indexing logs pass**

Run:

```bash
npm run python -- -m pytest app/back/tests/indexing/test_index_document_use_case.py app/back/tests/indexing/application/test_profile_orchestrator.py app/back/tests/indexing/infrastructure/test_ingestion_pipeline.py app/back/tests/indexing/infrastructure/postgres/test_vector_repository_contract.py app/back/tests/indexing/test_run_indexing_cli.py app/back/tests/indexing/test_validate_index_cli.py -q
```

Expected: PASS, with blocked paths and successful indexing visible in structured stdout logs.

- [ ] **Step 5: Commit**

```bash
git add app/back/src/indexing/application/use_cases/index_document.py app/back/src/indexing/application/profile_orchestrator.py app/back/src/indexing/infrastructure/llama_index/pipeline_factory.py app/back/src/indexing/infrastructure/embeddings/base.py app/back/src/indexing/infrastructure/postgres/node_repository.py app/back/src/indexing/infrastructure/postgres/normalized_document_repository.py app/back/src/indexing/infrastructure/postgres/vector_repository.py app/back/tests/indexing
git commit -m "feat(indexing): expose structured lifecycle logs"
```

---

## Final Verification

Run the focused regression set after the tasks above:

```bash
npm run python -- -m pytest app/back/tests/core/test_logging.py app/back/tests/core/test_observability.py app/back/tests/ingestion/test_pipeline_integration.py app/back/tests/ingestion/test_server_observability.py app/back/tests/chunking/integration/test_run_service_persistence.py app/back/tests/chunking/api/test_chunking_api.py app/back/tests/chunking/unit/test_structural_parser.py app/back/tests/chunking/unit/test_parent_chunk_builder.py app/back/tests/chunking/unit/test_child_chunk_builder.py app/back/tests/indexing/test_index_document_use_case.py app/back/tests/indexing/application/test_profile_orchestrator.py app/back/tests/indexing/infrastructure/test_ingestion_pipeline.py app/back/tests/indexing/infrastructure/postgres/test_vector_repository_contract.py app/back/tests/indexing/test_run_indexing_cli.py app/back/tests/indexing/test_validate_index_cli.py -q
```

Then start the API entrypoint and confirm the first stdout lines are structured JSON events:

```bash
npm run api
```

The operator should see:
- startup logs for the backend server
- run start and completion logs for ingestion
- phase/state transitions for Llama, chunking, and indexing
- warnings for fallback, low confidence, idempotency conflicts, and blocked states
- error logs for invalid requests, `ValueError`, `TypeError`, and other controlled failures
- duration fields for the major phases

## Definition Of Done

- `npm run api` / `npm run gui:api` shows structured logs in the terminal by default.
- The backend emits info, warning, and error logs for run, phase, state, and request transitions.
- The logging payload includes the contextual ids and timing metrics needed to reconstruct the document path.
- Runtime logs are not dependent on a text file to be observable.
- Existing ingestion, chunking, indexing, and validation behavior stays unchanged.
- The focused pytest suites pass.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-28-back-observability-logging.md`.

Two execution options:

1. Subagent-Driven (recommended) - I dispatch a fresh subagent per task, review between tasks, fast iteration
2. Inline Execution - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
