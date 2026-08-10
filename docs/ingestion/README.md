# Ingestion

## Purpose and scope

This area converts immutable source documents from `data/docs_raw` into
auditable Schema 2.0 bundles in `data/docs_normalized`. It covers inventory,
reading/OCR, normalization, classification, document control, table and form
extraction, review, validation, and controlled promotion. It does not perform
embedding, retrieval, chat generation, or use PostgreSQL as its source of
truth.

## Current branch state

> Baseline de plataforma RAG: ver `docs/rag-platform/migration-baseline.md`
> (autoridad del baseline reproducible; el hash histórico de abajo se conserva
> por precisión).

`main` at `f918b51` contains the local Schema 2.0 ingestion pipeline, its CLI,
JSON schemas, GUI control path, validation, and tests. The optional Llama Cloud
lane is implemented behind configuration and feeds the same normalized
contracts; corporate live use remains subject to the approvals documented in
the Llama-first material.

## Code map

- `app/back/src/ingestion/pipeline.py`: pipeline composition and document flow.
- `app/back/src/ingestion/readers/`, `ocr/`, `layout/`, `structure/`, and
  `normalization/`: local document reading and artifact extraction.
- `classification/`, `document_control/`, and `coverage/`: evidence-led
  document interpretation.
- `schemas/`, `manifests/`, `validation/`, and `promotion.py`: Schema 2.0
  contracts, atomic output, validation, and promotion.
- `scripts/ingestion/`: inventory, OCR diagnostics, pipeline, schema export,
  and normalized-tree validation CLIs.
- `app/back/tests/ingestion/` and `docs/ingestion/`: regression coverage and
  operational evidence.

## Inputs and outputs

Input is a source file beneath `data/docs_raw`, addressed by a canonical,
relative POSIX path. The output bundle in `data/docs_normalized` has normalized
Markdown plus `.metadata.json`, `.pages.json`, `.ocr.json`, `.tables.json`, and
`.forms.json` artifacts as applicable. `_manifests/` contains inventory, run,
bundle, validation, review, and error records; all Schema 2.0 writes are
validated and atomic.

## Operational flow

1. Inventory the source corpus and establish document identity and source hash.
2. Read Markdown or PDF content; local PDF paths use digital/OCR/hybrid readers
   as appropriate, while the enabled cloud lane delegates through ports.
3. Normalize while retaining raw text and page-level provenance; derive control,
   classification, table, form, and OCR artifacts.
4. Mark warnings, unsupported critical evidence, or insufficient confidence for
   review rather than fabricating a successful result.
5. Validate the candidate tree, then promote it only after the required gate
   succeeds.

## Rules and invariants

- `data/docs_raw` is immutable; source paths are context, not documentary truth.
- Classification prioritizes visible title, control data, content, codes, and
  tables. Generic folders alone do not create conflicts.
- Document IDs, source hashes, page order, raw content, and critical values are
  traceable and must not be silently altered.
- Material warnings produce `needs_review`; `needs_review` is not eligible for
  official downstream indexing without an explicit approval decision or sandbox
  rule.
- The validator requires coherent metadata, sidecars, front matter, inventory,
  status manifests, and, in closure mode, the PDF sidecars.

## Critical variables and configuration

Use the npm scripts, which select `C:\\venvs\\chatbot-sst` on Windows when
available, otherwise `.venv`. OCR setup is checked with `doctor:ocr`; the
review threshold is configurable by `--ocr-review-threshold` and defaults to
`0.80`. The optional cloud route is controlled by `LLAMA_CLOUD_ENABLED` and
its Llama settings; credentials must remain in the environment, never in the
repository.

## Logs, manifests, and observability

Structured ingestion logs carry document and stage context. Schema 2.0
manifests under `data/docs_normalized/_manifests/` preserve inventory, run,
validation, error, bundle, and review state. Metadata keeps `document_id`,
`source_hash`, versions, status, and provenance; cloud metadata adds provider
job and configuration references when used. Do not log full sensitive document
content or secrets.

## Commands and verification

```powershell
npm run doctor:ocr
npm run test:ingestion
npm run ingestion:inventory
npm run ingestion:run
npm run ingestion:validate
npm run schemas:export
```

For an isolated candidate, use `npm run ingestion:run -- --staging-root
.tmp/candidate --force --run-id candidate`, then validate that root with
`npm run ingestion:validate -- --docs-normalized .tmp/candidate --mode closure
--run-id candidate_gate`. Promotion remains a separate, gated operation.

## Visible inconsistencies and debt

- The operational README previously described the area without the canonical
  structure; this document now aligns it with the required format.
- `LLAMA_PARSE_VERSION=latest` remains the configured exploratory default, so
  it is not a production-stable Parse pin.
- `needs_review` approval is represented in a review manifest, but downstream
  consumers must still enforce their own eligibility filtering.

## Missing pieces to reach the target model

- A production authorization, retention, regional-processing, and budget
  decision is required before corporate documents can use cloud services.
- The ingestion area alone does not provide the target PostgreSQL-backed,
  indexed retrieval system; that belongs to downstream areas.
- Production cloud routing needs accepted benchmark evidence and a dated Parse
  version pin before it can replace selective experimental use.

## References

- `AGENTS.md` and `docs/rules/`
- `docs/ingestion/phase1_checklist.md`
- `docs/ingestion/phase1_closure_report.md`
- `docs/ingestion/pdf_corpus_quality_audit.md`
- `docs/llama_first/README.md`
