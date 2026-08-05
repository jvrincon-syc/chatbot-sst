# Backend Observability Runbook

## Scope

This runbook explains how to watch the backend from the terminal without
changing the business logic or the durable manifests.

## Start the backend

```powershell
npm run gui:api
```

This is the real backend entrypoint. There is no separate `api` alias in
`package.json`.

Expected startup events:

- `backend_process_started`
- `backend_configuration_loaded`
- `backend_ready`

Expected shutdown events:

- `backend_shutdown_started`
- `backend_shutdown_completed`

## Follow one HTTP request

1. Capture the `request_id` from `http_request_started`.
2. Follow the same `request_id` through the rest of the stdout log stream.
3. If the request triggers chunking work, the same `request_id` is handed off
   explicitly to the chunking request object and to any worker thread logs.
4. Use `method`, `route`, `status_code`, and `duration_ms` to understand the
   lifecycle.

Do not expect to see:

- full request bodies;
- full headers;
- signed URLs;
- document contents;
- tokens or API keys.

## Follow an ingestion run

Look for these events in order:

- `pipeline_run_started`
- `pipeline_inventory_completed`
- `document_selected`
- `document_start`
- `document_fallback_activated` when the cloud path falls back locally
- `document_normalization_completed`
- `document_validation_completed`
- `document_review_required` when the document needs human review
- `review_decision_recorded`
- `document_finished`
- `document_failed`
- `pipeline_run_completed`

Useful identifiers:

- `run_id`
- `document_id`
- `request_id`
- `provider`
- `capability`

## Follow indexation

The indexing path now exposes:

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

For PostgreSQL-backed indexing:

1. Confirm `indexing_persistence_started` appears before the async indexing
   work finishes.
2. Confirm `indexing_persistence_committed` after a successful transaction.
3. Confirm `indexing_persistence_rolled_back` if the transaction is aborted.

## Follow chunking

When chunking is launched from the GUI or API, the request correlation is kept
explicit:

- `request_id` is generated at the HTTP boundary.
- `request_id` is attached to `ChunkingRunRequest`.
- `request_id` is written into the persisted chunking run state and logs.

If you call the chunking API directly, send `X-Request-Id` to preserve the
handoff.

## CLI contract

- `stdout` contains only the final machine-readable JSON payload.
- `stderr` contains structured JSON logs.
- `scripts/ingestion/doctor_ocr.py` always prints JSON to `stdout`.

Useful commands:

```powershell
npm run ingestion:run
npm run ingestion:validate
npm run indexing:run -- --dry-run
npm run indexing:validate
npm run chunking:run
```

## DEBUG mode

The current logger config does not expose a dedicated env flag. If you need
DEBUG logs in a local session, lower the console handler level after calling
`configure_structured_logging`:

```python
import logging
import sys

from core.logging.logger import configure_structured_logging

root = configure_structured_logging(stream=sys.stdout)
for handler in root.handlers:
    if handler.name == "chatbot_sst_console":
        handler.setLevel(logging.DEBUG)
```

The file sink still keeps `WARNING+` in `logs/app.log`.

## What should never appear

- full document text;
- prompt text;
- provider responses;
- raw uploads;
- vectors;
- signed URLs;
- secrets or tokens.

## Quick triage map

- `cloud_fallback_used`: the local fallback path was used.
- `needs_review`: the document still requires human review.
- `indexing_persistence_rolled_back`: the database transaction failed.
- `http_request_failed`: the request crashed unexpectedly.
- `http_request_rejected`: the request was invalid or blocked.
