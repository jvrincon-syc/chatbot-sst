# Checklist Audit Against Memory Plan

Date: 2026-07-21

Source checklist: `memory/2026-07-21-plan-llama-first-chatbot-sst.md`

## Result Summary

The branch now satisfies the checklist items that can be completed locally
without uploading corporate documents to Llama Cloud or connecting to a live
PostgreSQL/pgvector database.

## Completed Or Implemented Locally

| Plan area | Status | Evidence |
| --- | --- | --- |
| Fase 0 baseline, research and dependencies | Completed locally | `docs/llama_first/*`, `docs/adr/ADR-001-*`, `ADR-002-*`, `constraints/llama-first.txt`, dependency checker |
| Fase 0.5 guarded smoke | Completed with synthetic non-sensitive file | `data/evaluation/llama_first/smoke-results.json` records real Parse/Classify/Extract job IDs and sanitized result shapes |
| Fase 1 domain/config/ports | Completed locally | Domain models, ports, provider run repository, usage ledger and tests |
| Fase 2 LlamaParse | Completed locally under feature flag | Parse config/adapter/raw storage/reader routing/fallback tests |
| Fase 3 LlamaClassify | Baseline completed locally | Rules and adapter tests; live classification blocked with cloud smoke |
| Fase 4 LlamaExtract | Baseline completed locally | Extract adapter/form mapper tests; parse job reuse live verification blocked |
| Fase 5 bundles/schemas/routing | Completed locally | Schema export/validation, Llama extraction methods, fallback route |
| Fase 6 LlamaIndex indexing | Completed local baseline | Document factory, parent/child parser, metadata pipeline, embeddings, cache/upsert/rollback tests, migration, CLI |
| Fase 7 retrieval | Completed local baseline | Vector filter retriever, FTS SQL builder, RRF, reranking, parent expansion, evidence builder |
| Fase 8 evaluation | Harness completed | JSONL datasets, metrics, benchmark CLI |
| Fase 9 operations | Completed local baseline | Resume planner, credit budget, GUI status panel, runbooks |
| Fase 10 hardening | Completed local verification | Full backend tests, frontend build, schema export, validation, dependency and secret checks |

## Explicitly Blocked Checklist Items

These items are not marked complete because the plan itself requires external
approval or infrastructure:

- Live Parse/Classify/Extract smoke over an authorized corporate document.
- Confirming real cloud credits, retention/deletion and returned effective
  dated Parse version.
- Replacing `LLAMA_PARSE_VERSION=latest` with a dated version from a real job.
- Writing real vectors to PostgreSQL/pgvector and validating live CRUD.
- Full A/B production benchmark and final adoption gate.
- Runbooks tested by a person distinct from the implementer.
- Review by three senior engineers.

## Latest Verification

- `npm run python -- scripts/experiments/llama_cloud_smoke.py`: completed with synthetic source, Parse job `pjb-g05y0jzu8law2xy820haloreyu5e`, Classify job `clj-gez9e4ucpa1pdcl3c6vv06fd9pes`, Extract job `ext-zzz5se6fsmx5d2qlqs6wcm7n9dfs`.
- `npm run indexing:run`: indexed 41 approved documents into the local LlamaIndex-backed memory pipeline, producing 41 parent nodes and 95 child nodes.
- `npm run python -- -m pytest app/back/tests`: 319 passed, 3 skipped.
- `npm --prefix app/front run build`: passed.
- `npm run schemas:export`: exported 10 schemas.
- `npm run ingestion:validate`: passed with 0 errors.
- `npm run indexing:run -- --dry-run`: 55 candidates, 41 approved.
- `npm run indexing:run`: indexed 41 approved documents, 41 parent nodes and 95 child nodes.
- `npm run indexing:validate`: passed; approved artifacts present for 41 documents.
- `npm run evaluation:llama-first`: baseline_ready.
- `npm run python -- scripts/experiments/check_llama_dependencies.py`: ok.
- `npm run python -- -m pip check`: no broken requirements.
