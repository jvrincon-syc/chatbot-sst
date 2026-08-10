# Llama-first

## Purpose and scope

Llama-first is the experimental ingestion lane that evaluates LlamaParse,
LlamaClassify, and LlamaExtract behind neutral ports while preserving the local
Schema 2.0 traceability contract. It is not an authorization to submit
corporate documents to Llama Cloud, nor a replacement for the local pipeline,
downstream indexing, or PostgreSQL operations.

## Current branch state

> Baseline de plataforma RAG: ver `docs/rag-platform/migration-baseline.md`
> (autoridad del baseline reproducible; el hash histórico de abajo se conserva
> por precisión).

`main` at `f918b51` implements adapters, settings, provider-run persistence,
usage tracking, raw-result redaction, and `LlamaOrchestrator`. The lane can be
selected through feature flags and the ingestion GUI; local fallback is also
implemented. Live corporate-cloud operation and adoption benchmarks are not
accepted branch state.

## Code map

- `app/back/src/ingestion/application/services/llama_orchestrator.py`: ordered
  Parse/Classify/Extract orchestration and phase logging.
- `app/back/src/ingestion/application/ports/`: provider-neutral capability,
  run-repository, and usage-ledger contracts.
- `app/back/src/ingestion/infrastructure/llama_cloud/`: Llama Cloud adapters,
  request configuration, result mapping, error handling, and redacted storage.
- `app/back/src/ingestion/config/llama_settings.py`: environment settings and
  lane-order validation.
- `docs/adr/ADR-001-llama-first-experiment-boundaries.md` through ADR-004 and
  `docs/runbooks/`: decisions and operational responses.

## Inputs and outputs

The lane receives a document identity, controlled source path, and enabled
capability configuration. Parse produces internal page Markdown and provider
job references; optional classification and extraction are mapped to internal
models with evidence. Results join the standard normalized bundle and preserve
job IDs, configuration hashes, page metadata, warnings, and provider usage
without exposing secrets.

## Operational flow

1. Load and validate Llama settings; cloud mode requires an API key.
2. Run the configured, non-repeating call order. Parse occurs exactly once;
   Extract cannot precede Parse, and Classify precedes Extract when both run.
3. Map cloud responses through infrastructure adapters into internal contracts,
   saving provider-run and usage records where configured.
4. Check critical extraction values against parsed evidence and turn unsupported
   claims or failures into observable warnings/errors.
5. Continue with the same normalized-artifact and review rules as local
   ingestion, or use the configured local fallback.

## Rules and invariants

- Domain and application code depend on ports, not Llama SDK imports.
- Cloud mode needs `LLAMA_CLOUD_API_KEY`; configuration dumps redact it.
- Parse is mandatory and appears exactly once in `LLAMA_CALL_ORDER`.
- Critical extracted fields require textual evidence or receive a warning; the
  system must not promote unsupported claims as verified facts.
- Raw provider snapshots redact API keys, tokens, authorization values, signed
  URLs, and URL-shaped strings. Corporate cloud runs remain fail-closed until
  data, region, retention/deletion, and budget approvals exist.

## Critical variables and configuration

`LLAMA_CLOUD_ENABLED`, `LLAMA_CLOUD_API_KEY`, `LLAMA_PARSE_TIER`,
`LLAMA_PARSE_VERSION`, `LLAMA_PARSE_OCR_LANGUAGES`, `LLAMA_PARSE_EXPAND`,
`LLAMA_PARSE_MAX_CONCURRENCY`, `LLAMA_PARSE_TIMEOUT_SECONDS`,
`LLAMA_PARSE_MAX_CREDITS_PER_RUN`, `LLAMA_PARSE_STORE_RAW_RESULTS`,
`LLAMA_CLASSIFY_ENABLED`, `LLAMA_CLASSIFY_MAX_PAGES`,
`LLAMA_EXTRACT_ENABLED`, `LLAMA_EXTRACT_TIER`, `LLAMA_EXTRACT_PARSE_TIER`,
`LLAMA_EXTRACT_MAX_PAGES`, `LLAMA_CALL_ORDER`, and
`LLAMA_LOCAL_FALLBACK_ENABLED` configure the lane. Defaults include
`cost_effective` Parse and `latest` Parse version; `latest` is exploratory.

## Logs, manifests, and observability

Each phase emits structured events with document ID, source path, provider,
capability, job IDs, configuration hash, duration, result/warning counts, and
failure context. Provider jobs can be recorded in JSONL, while redacted raw
results are stored by document, configuration hash, and capability. Normalized
metadata records Llama job and page metadata; logs and snapshots must not
contain secrets or unrestricted sensitive payloads.

## Commands and verification

```powershell
npm run python -- -m pytest app/back/tests/ingestion/application/test_ports_contract.py -v
npm run python -- -m pytest app/back/tests/experiments/test_llama_dependency_compatibility.py -v
npm run python -- -m pytest app/back/tests/experiments/test_llama_cloud_smoke.py -v
npm run ingestion:validate
npm run test:indexing
npm run indexing:run -- --dry-run
```

For guarded live validation, use `scripts/experiments/llama_cloud_smoke.py`
with `LLAMA_CLOUD_LIVE=true`, authorized synthetic or approved data, a bounded
budget, and the applicable runbook.

## Visible inconsistencies and debt

- `LLAMA_PARSE_VERSION` defaults to `latest`, which conflicts with the
  production requirement for a validated dated pin.
- The README previously mixed implementation state, configuration, and blockers
  without the canonical operational structure.
- Raw-result persistence is redacted but still needs an explicit retention and
  authorization policy before it can hold corporate-provider results.

## Missing pieces to reach the target model

- Complete and record cloud data authorization, region, retention/deletion,
  training-use, subprocessors, and budget decisions.
- Run reproducible A/B benchmarks with authorized fixtures, then pin Parse to a
  dated validated version and document the routing decision.
- Complete production PostgreSQL/pgvector connectivity and the operational
  recovery evidence required for a production cloud lane.

## References

- `AGENTS.md` and `docs/rules/SECURITY_AND_DATA.md`
- `docs/adr/ADR-001-llama-first-experiment-boundaries.md`
- `docs/adr/ADR-002-pydantic-and-llamaindex-pins.md`
- `docs/adr/ADR-003-node-parsing-strategy.md`
- `docs/adr/ADR-004-production-parser-routing.md`
- `docs/runbooks/llama-cloud-outage.md`, `llama-credit-exhaustion.md`, and
  `pin-parse-version.md`
