# Llama-first Execution Status

Date: 2026-07-21

## Completed Locally

- Fase 0: baseline docs, research log, decision log, corpus sample, guarded smoke script, synthetic live Llama Cloud smoke, dependency spike.
- Fase 1: domain models, ports, provider run repository, usage ledger, usage manifest summarizer, settings.
- Fase 2: LlamaParse adapter, config, raw result storage and reader routing with fallback.
- Fase 3: LlamaClassify adapter and rule mapping baseline.
- Fase 4: LlamaExtract adapter and form mapper baseline.
- Fase 5: compatible schema extension and Llama PDF routing into the pipeline.
- Fase 6: indexing bounded context, LlamaIndex document factory, structure-aware nodes, metadata pipeline, embedding factory, in-memory docstore/vector pipeline, migration and CLI with approved-artifact validation.
- Fase 7: vector retrieval, PostgreSQL FTS query builder, fusion, reranking baseline, parent expansion and evidence builder.
- Fase 8: evaluation dataset, metrics and local benchmark harness.
- Fase 9: resume planner, credit budget, GUI status payload, frontend Llama-first status panel and runbooks.
- Fase 10: dependency pins, README update, hardening checks and verification commands.

## Blocked By Policy Or External State

- Corporate-document live cloud smoke: blocked until a specific document is
  approved for upload and region, retention/deletion policy and credit budget
  are documented. A synthetic non-sensitive smoke completed Parse, Classify and
  Extract on 2026-07-21.
- Parse version pin: blocked until a live or recorded LlamaParse job returns the
  effective dated version to replace `latest`.
- Real pgvector write: migration and adapters are present, but unit tests use
  memory because no PostgreSQL/pgvector connection was configured for this run.
- Production A/B decision: benchmark harness is ready, but live/recorded
  Llama-first outputs are needed for final quality gates.

## Verification Evidence

- `npm run python -- scripts/experiments/check_llama_dependencies.py`: ok.
- `npm run python -- scripts/experiments/llama_cloud_smoke.py`: completed with
  synthetic source; Parse `pjb-g05y0jzu8law2xy820haloreyu5e`, Classify
  `clj-gez9e4ucpa1pdcl3c6vv06fd9pes`, Extract
  `ext-zzz5se6fsmx5d2qlqs6wcm7n9dfs`.
- `npm run python -- -m pip check`: no broken requirements.
- `npm run python -- -m pytest app/back/tests`: 319 passed, 3 skipped.
- `npm --prefix app/front run build`: passed.
- `npm run schemas:export`: exported 10 schemas.
- `npm run ingestion:validate`: passed with 0 errors.
- `npm run indexing:run -- --dry-run`: 55 candidates, 41 approved.
- `npm run indexing:run`: 41 approved documents indexed, 41 parent nodes and
  95 child nodes in the local LlamaIndex-backed memory pipeline.
- `npm run indexing:validate`: passed; approved artifacts present for 41 documents.
- `npm run evaluation:llama-first`: baseline_ready with 2 documents, 2 questions.

## Low-cost API Policy

- LlamaParse keeps `tier=cost_effective` for the auditable PDF path because the
  `fast` tier does not support `markdown` or `items`.
- If `LLAMA_PARSE_TIER=fast` is selected for text-only probes, the adapter drops
  `markdown` and `items` from `expand` and requests text/metadata only.
- LlamaClassify sends `configuration.mode=FAST` and limits parsing to
  `LLAMA_CLASSIFY_MAX_PAGES` (default 5).
- LlamaExtract sends `tier=cost_effective`, `parse_tier=fast` and
  `LLAMA_EXTRACT_MAX_PAGES` (default 5).

## Classification Policy Update

- Folder names in `data/docs_raw` are operational organization only. They are
  not documentary truth and must not send a document to `needs_review` when
  title/control/content evidence resolves type or topic.
- Route-derived signals are low-authority context. Containers such as `manual`,
  `capacitaciones`, `politica` and `convivencia_laboral` must not create
  `classification_conflict` against stronger title/control evidence.
- Specific route segments can still help disambiguate topic; `seguridad_vial`
  is more specific than the generic `capacitaciones` container.
- Codes extracted from control tables or headers are authoritative over
  narrative references to other formats.
- Projection after this policy over the latest 9-PDF LlamaParse run:
  `processed=9`, `needs_review=0`, `classification_conflict=0`,
  `conflicting_code=0`, with 77/77 pages preserved.
