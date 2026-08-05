# Current Backend Observability Contracts

This file captures the current backend observability baseline for `chatbot-sst`.
It is a compatibility snapshot, not a future design target.

## Verified channels

- `stdout`: structured JSON from the core logger and from `npm run gui:api`.
- `stderr`: structured JSON from CLI entrypoints after
  `configure_structured_logging(..., stream=sys.stderr, include_file_handler=False)`.
- `_details.log`: durable JSONL for ingestion runs.
- `logs/app.log`: warning-and-above file sink from the core logger.
- manifests: run, review, error, and indexing artifacts.

## Compatibility table

| Contract | Producer | Consumer | Add fields | Rename event | Change destination |
|---|---|---|---|---|---|
| stdout logger | `app/back/src/core/logging/logger.py` | Terminal operators, tests | Yes, if JSON-safe and sanitized | No without migration | No |
| `logs/app.log` | `app/back/src/core/logging/logger.py` | Operators investigating warnings and errors | Yes, if sanitized | No without migration | No |
| `_details.log` | `app/back/src/ingestion/logging/jsonl.py` | Audit tooling and ingestion regressions | Yes, aditively | No without migration | No |
| manifests | ingestion, chunking, and indexing writers | Validators, resume logic, audit | Yes, aditively | No without migration | No |
| CLI stdout | scripts under `scripts/` | Shell automation and tests | Yes only if the final JSON contract stays valid | No, because parsers expect stable keys | No |
| CLI stderr | scripts under `scripts/` | Operators and CI logs | Yes, if structured JSON remains valid | No without coordination | No |

## Current event families

### GUI and HTTP

- `backend_process_started`
- `backend_configuration_loaded`
- `backend_ready`
- `backend_shutdown_started`
- `backend_shutdown_completed`
- `http_request_started`
- `http_request_completed`
- `http_request_rejected`
- `http_request_failed`
- `review_decision_recorded`

### Ingestion pipeline

- `pipeline_run_started`
- `pipeline_inventory_completed`
- `document_selected`
- `document_skipped`
- `document_start`
- `document_fallback_activated`
- `document_normalization_completed`
- `document_validation_completed`
- `document_review_required`
- `document_finished`
- `document_failed`
- `pipeline_validation_completed`
- `document_promotion_started`
- `document_promotion_completed`
- `pipeline_run_completed`
- `pipeline_run_failed`

### Llama orchestrator

- `llama_classify_start`
- `llama_classify_finished`
- `llama_classify_failed`
- `llama_classify_skipped`
- `llama_parse_start`
- `llama_parse_finished`
- `llama_parse_failed`
- `llama_extract_start`
- `llama_extract_finished`
- `llama_extract_failed`
- `llama_extract_skipped`

### Indexing

- `indexing_document_started`
- `indexing_document_rejected`
- `indexing_profile_resolved`
- `indexing_profile_rejected`
- `indexing_bundle_validated`
- `indexing_nodes_built`
- `embedding_provider_selected`
- `embedding_batch_started`
- `embedding_batch_completed`
- `indexing_persistence_started`
- `indexing_persistence_committed`
- `indexing_persistence_rolled_back`
- `indexing_document_completed`
- `indexing_document_failed`

### CLI contract

- CLI commands keep the final machine-readable JSON on `stdout`.
- Operational logs go to `stderr` as structured JSON.
- `scripts/ingestion/doctor_ocr.py` always prints a JSON payload to `stdout`.
- `npm run gui:api` is the real backend entrypoint. There is no `api` alias in
  `package.json`.

## Reserved and sensitive data

Never emit:

- document body text;
- prompt text;
- response bodies;
- tokens or API keys;
- signed URLs;
- vectors;
- raw uploads;
- full headers;
- full request bodies.

The logging helper uses `event_message` inside structured payloads because
`message` is reserved by `logging.LogRecord`.

## Traceability notes

- `request_id` is handoff-only and must be propagated explicitly.
- `run_id`, `document_id`, `job_id`, `profile_id`, `provider`, `capability`,
  and `configuration_hash` are the stable identifiers used today.
- `JsonlLogger` continues to persist `_details.log` with `schema_version=1.0`.

## Sanitized samples

### Core logger stdout

```json
{"level":"INFO","message":"Backend process started","event":"backend_process_started","event_message":"Backend process started","context":{"run_id":"run_123"}}
```

### CLI stderr

```json
{"level":"INFO","message":"indexing command started: profile=llama-first-local-v1 store=memory dry_run=false ingestion_origin=local"}
```

### `_details.log`

```json
{"schema_version":"1.0","stage":"pipeline","event":"pipeline_run_started","status":"started","message":"Pipeline run started","request_id":"req_123","context":{"run_id":"run_123","request_id":"req_123"},"metrics":{"document_count":2},"attributes":{"promote":false}}
```

## Verification evidence

- `app/back/tests/core/test_logging.py`
- `app/back/tests/core/test_observability.py`
- `app/back/tests/ingestion/test_gui_server.py`
- `app/back/tests/ingestion/test_gui_chunking_routes.py`
- `app/back/tests/ingestion/test_pipeline_integration.py`
- `app/back/tests/chunking/integration/test_run_service_persistence.py`
- `app/back/tests/chunking/integration/test_chunking_orchestrator.py`
- `app/back/tests/chunking/api/test_chunking_api.py`
- `app/back/tests/chunking/corpus/test_chunking_corpus_golden.py`
- `app/back/tests/indexing/infrastructure/test_ingestion_pipeline.py`
- `app/back/tests/indexing/test_run_indexing_cli.py`
- `app/back/tests/indexing/test_validate_index_cli.py`
- `app/back/tests/indexing/test_prepare_postgres_indexing.py`
- `app/back/tests/indexing/test_package_scripts.py`
- `app/back/tests/experiments/test_llama_cloud_smoke.py`
- `app/back/tests/experiments/test_llama_dependency_compatibility.py`
