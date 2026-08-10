# Chunking

## Purpose and scope

This area performs deterministic local structural parent-child chunking over
validated Schema 2.0 normalized documents. It creates inspectable chunk
bundles for downstream consumers; it does not accept uploads, normalize source
documents, generate embeddings, index vectors, retrieve evidence, or answer
chat requests.

## Current branch state

> Baseline de plataforma RAG: ver `docs/rag-platform/migration-baseline.md`
> (autoridad del baseline reproducible; el hash histórico de abajo se conserva
> por precisión).

`main` at `f918b51` contains the local `local-structural-v1` engine, filesystem
persistence, CLI, FastAPI API, run service, validation utility, golden corpus,
and unit/integration/API tests. `docs/chunking/README.md` did not exist in the
committed tree before this documentation update; this is a new operational
entry point derived from the committed implementation and existing contracts.

## Code map

- `app/back/src/chunking/domain/`: immutable models, policy, enums, and
  invariants.
- `app/back/src/chunking/application/`: structural parser, parent/child
  builders, local engine, orchestrator, run service, and ports.
- `app/back/src/chunking/infrastructure/`: Schema 2.0 loading, canonical
  tokenizer, Markdown adaptation, and filesystem repositories.
- `app/back/src/chunking/api/`: FastAPI composition, routes, schemas, and
  dependencies.
- `scripts/chunking/`: command-line execution and validation.
- `app/back/tests/chunking/` and `docs/chunking/`: executable coverage and
  versioned contracts.

## Inputs and outputs

Input is Markdown plus required Schema 2.0 metadata and pages sidecars under
`data/docs_normalized`; tables, forms, and OCR sidecars are optional but
validated when present. The source loader rejects unsafe paths and mismatched
document identity, hashes, paths, or page counts. Output beneath `data/chunks`
contains `.parent_chunks.jsonl`, `.child_chunks.jsonl`, and
`.chunking_metadata.json`, plus run and validation manifests in `_manifests/`.

## Operational flow

1. Load a constrained normalized Markdown path and validate its Schema 2.0
   sidecars and front matter.
2. Parse structural blocks and resolve their page-aware source spans.
3. Build deterministic parents, then children with canonical token counts and
   semantic overlap rules.
4. Validate the chunk bundle against the source document and profile.
5. Atomically replace the persisted bundle and write run/validation manifests;
   identical fingerprints are reusable rather than recomputed.

## Rules and invariants

- The only committed profile is `local-structural-v1`: child minimum/target/max
  are 250/350/450 tokens, with 12% overlap clamped to 30--60 tokens.
- Child maximum includes overlap. Parent/block/child text and source spans must
  be nonblank, ordered, and auditable.
- IDs and fingerprints are deterministic SHA-256 identities over content,
  profile, and stable structural position.
- Every child belongs to an existing parent in the same document/profile.
- Zero overlap is fail-closed and allowed only at `document_start` or a
  `table_or_form_boundary`; `section_boundary` is not valid for this profile.
- HTTP execution requires an `Idempotency-Key`, validates inventory document
  IDs, and uses a single worker per application instance.

## Critical variables and configuration

The CLI defaults are `--docs-normalized data/docs_normalized`, `--chunks-root
data/chunks`, and `--profile local-structural-v1`; `--document` may be repeated
to restrict scope. The profile is fixed in the current implementation. API
requests select `scope` (`documents` or `corpus`), inventory `document_ids`,
profile, and `force`; pagination accepts pages and page sizes from 1 through
100.

## Logs, manifests, and observability

Chunking logs include run/document IDs, reuse state, progress, and failures.
Per-document output metadata preserves source path/hash, corpus version,
profile and bundle fingerprints, and parent/child counts. `data/chunks/_manifests/`
holds CLI run and validation records as well as API run state and validation
summaries. API responses expose run progress, warnings, relative inspection
links, parents, children, and validation status without accepting arbitrary
filesystem paths.

## Commands and verification

```powershell
npm run python -- scripts/chunking/run_chunking.py
npm run python -- scripts/chunking/run_chunking.py --document path/to/document.md
npm run python -- scripts/chunking/validate_chunks.py
npm run python -- -m pytest app/back/tests/chunking -v
```

Run normalized ingestion validation before chunking when the source bundle has
changed: `npm run ingestion:validate`.

## Visible inconsistencies and debt

- The README was absent from `HEAD`; related policy, API, and decision-log
  documents existed but were not consolidated operationally.
- The HTTP API declares a 500 error envelope but does not install a global
  handler for uncontrolled exceptions.
- Parent listing with `run_id` checks that the run exists but reads the current
  document bundle rather than selecting artifacts scoped to that historical run.
- There is no request-contract maximum number of document IDs per API run.

## Missing pieces to reach the target model

- Define durable historical artifact selection per chunking run, rather than
  only current bundle inspection.
- Add a global uncontrolled-exception error mapper if the documented 500
  envelope is to be guaranteed.
- Establish explicit capacity/concurrency limits for API document batches and
  operational storage retention for chunk artifacts.
- Integrate approved chunk bundles with the separately owned production
  embedding/indexing persistence path.

## References

- `AGENTS.md` and `docs/rules/TESTING_AND_QUALITY.md`
- `docs/chunking/api_contract.md`
- `docs/chunking/chunking_policy.md`
- `docs/chunking/decision-log.md`
- `docs/chunking/golden_corpus_expected.json`
- `docs/ingestion/README.md`
