# Observability

## 1. Purpose and scope

Observability defines sanitized backend signals and their compatible operational destinations. This README is the canonical index to the committed contract and runbooks, not a replacement for their detailed field/event definitions.

## 2. Current branch state

This reflects committed `main` at `f918b512a5320b6fc434feefe1e3e9f780bc097b`. No observability README existed in that commit. [current-contracts.md](current-contracts.md) is the committed compatibility baseline, not a future design.

> Baseline de plataforma RAG: ver `docs/rag-platform/migration-baseline.md` (autoridad del baseline reproducible; este hash histórico se conserva por precisión).

## 3. Code map

- Structured logger/sinks: `app/back/src/core/logging/logger.py`.
- Typed events, redaction, duration, exception correlation: `app/back/src/core/logging/observability.py`.
- Contract: [current-contracts.md](current-contracts.md).
- Operator guide: [backend-observability.md](../runbooks/backend-observability.md).
- Related procedures: `docs/runbooks/`.

## 4. Inputs and outputs

Inputs are Python log records and typed `ObservabilityEvent` values with domain/status/context/metrics/attributes. Outputs are structured JSON on stdout or stderr according to entrypoint, warning-and-above `logs/app.log`, ingestion `_details.log` JSONL, and subsystem manifests.

## 5. Operational flow

1. Configure the logger with `configure_structured_logging`.
2. Build an event with stable context IDs and sanitized metadata.
3. Emit through the shared helper to select level, log JSON, and optionally mirror JSONL.
4. Follow request/run/document/profile IDs and inspect durable manifests for audit/recovery.

## 6. Rules and invariants

- CLI stdout retains final machine-readable JSON; operational CLI logs use stderr.
- Add fields only additively; do not rename events or destinations without migration.
- Use `event_message` in typed payloads because `message` is reserved by `LogRecord`.
- Never emit document/prompt text, provider bodies, raw uploads, vectors, URLs, headers/bodies, secrets, or tokens.
- `request_id` handoff is explicit; run/document/job/profile/provider/capability/configuration hash are stable context.

## 7. Critical variables and configuration

- `configure_structured_logging(stream=..., include_file_handler=...)` controls sinks.
- Console is `INFO`; `logs/app.log` is rotating `WARNING+`, 5 MB, three backups.
- No dedicated DEBUG environment flag is committed; the runbook shows a local handler adjustment.
- Typed events and ingestion JSONL use schema version `1.0`.

## 8. Logs, manifests, and observability

[current-contracts.md](current-contracts.md) is canonical for channels, compatibility, event families, samples, and tests. [backend-observability.md](../runbooks/backend-observability.md) covers backend startup, HTTP/ingestion/indexing/chunking tracing, CLI streams, and triage. Related procedures include [llama-cloud-outage.md](../runbooks/llama-cloud-outage.md), [llama-credit-exhaustion.md](../runbooks/llama-credit-exhaustion.md), [pin-parse-version.md](../runbooks/pin-parse-version.md), and [reprocess-document.md](../runbooks/reprocess-document.md).

## 9. Commands and verification

```powershell
npm run gui:api
npm run test:pipeline
npm run test:indexing
npm run ingestion:validate
npm run indexing:validate
```

Use the focused test list in [current-contracts.md](current-contracts.md). `npm run gui:api` is the real backend command; no `api` script exists.

## 10. Visible inconsistencies and debt

- The committed tree had no README for this area.
- The snapshot lists GUI, ingestion, Llama, and indexing events but not embedding/retrieval events emitted by newer modules.
- Manifests are a channel without one central schema/version policy.

## 11. Missing pieces to reach the target model

- No complete owned event catalog covers embedding and retrieval.
- No retention/access policy or alerting/metrics backend is specified.
- No central manifest index captures schemas, producers, consumers, and replay/rollback procedures.

## 12. References

- [Current backend observability contracts](current-contracts.md)
- [Backend observability runbook](../runbooks/backend-observability.md)
- `app/back/src/core/logging/logger.py`
- `app/back/src/core/logging/observability.py`
- `app/back/tests/core/test_logging.py`
- `app/back/tests/core/test_observability.py`

