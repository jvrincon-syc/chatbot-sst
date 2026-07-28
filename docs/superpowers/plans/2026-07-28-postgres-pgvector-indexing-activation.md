# PostgreSQL Pgvector Indexing Activation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Activate the existing indexing pipeline against configured PostgreSQL/pgvector using `bge` and `voyage` as the only productive providers, while keeping `mock` reserved for tests and dry-run.

**Architecture:** The pipeline already consumes normalized bundles, builds parent/child nodes locally, embeds child nodes at the infrastructure boundary, and persists through PostgreSQL repositories. This plan verifies readiness, locks the provider policy, and runs progressively larger smoke tests against the live database before any broader rollout. PostgreSQL remains the durable source of truth, and each embedding profile keeps its own physical vector table.

**Tech Stack:** Python 3.12, Pydantic 2, pytest, PostgreSQL 13+, pgvector, LlamaIndex OSS, npm scripts, PowerShell.

## Global Constraints

- `data/docs_raw` remains immutable.
- `data/docs_normalized` remains the auditable downstream contract.
- Productive embedding providers are only `bge` and `voyage`.
- `mock` is allowed only for tests and dry-run.
- `cohere` is out of scope for this rollout.
- Do not mix providers, models, dimensions, or corpus lanes in one vector table.
- `SST_POSTGRES_DSN` is required for live PostgreSQL runs and live tests.
- `--persist-confirmed` is required before any live PostgreSQL write.
- Secrets stay in environment or `secrets.env`; never in git or logs.
- This planning pass does not modify application code.

---

## Current Evidence

- `docs/llama_first/README.md` already documents the indexing lane, pgvector dependency, and embedding configuration.
- `memory/plan_trabajo.md` frames PostgreSQL as the source of truth and pgvector as the vector layer.
- `docs/superpowers/plans/2026-07-22-postgres-pgvector-indexing.md` already specifies profile separation and gated PostgreSQL writes.
- `scripts/indexing/run_indexing.py` already exposes `--store`, `--profile`, `--ingestion-origin`, `--dry-run`, and `--persist-confirmed`.
- `migrations/20260722_seed_indexing_profiles.sql` already creates one physical vector table per profile.
- `app/back/src/indexing` already contains PostgreSQL repositories and the embedding factory.

---

### Task 1: Lock the production provider contract

**Files:**
- Review: `docs/llama_first/README.md`
- Review: `app/back/AGENTS_back.md`
- Review: `memory/plan_trabajo.md`
- Review: `docs/superpowers/plans/2026-07-22-postgres-pgvector-indexing.md`
- Future update if needed: `docs/llama_first/README.md`

**Interfaces:**
- Consumes: current docs and the existing runtime contract.
- Produces: a single, explicit statement of the operational rule: `bge` and `voyage` are the only productive providers; `mock` is test/dry-run only.

- [ ] **Step 1: Write the contract statement**

```text
Production providers: bge and voyage
Test and dry-run only: mock
Not part of this rollout: cohere
```

- [ ] **Step 2: Compare the contract against the docs**

Run:

```powershell
Get-Content docs/llama_first/README.md
Get-Content memory/plan_trabajo.md
```

Expected:
- The new contract is explicit in the plan.
- Any broader provider list is identified as documentation drift, not as a live production policy.

- [ ] **Step 3: Decide whether documentation must be aligned before go-live**

Acceptance:
- There is no ambiguity about productive providers.
- Any config that still exposes `cohere` for live indexing is treated as a blocker, not as a supported path.

- [ ] **Step 4: Record the final policy in the execution notes**

Expected outcome:
- The rollout uses only `bge` and `voyage` for production indexing.
- `mock` remains available only for test and dry-run verification.

---

### Task 2: Verify PostgreSQL and pgvector readiness

**Files:**
- Review: `migrations/20260722_indexing_profiles_pgvector.sql`
- Review: `migrations/20260722_seed_indexing_profiles.sql`
- Review: `scripts/indexing/prepare_postgres_indexing.py`
- Test: `app/back/tests/indexing/test_prepare_postgres_indexing.py`

**Interfaces:**
- Consumes: `SST_POSTGRES_DSN` and the migration set.
- Produces: a prepared PostgreSQL instance with the base tables and per-profile vector tables ready for indexing.

- [ ] **Step 1: Confirm the PostgreSQL DSN is present**

Run:

```powershell
Get-ChildItem Env:SST_POSTGRES_DSN
```

Expected:
- The variable exists in the shell or is sourced from `secrets.env` before running any live step.

- [ ] **Step 2: Prepare the database**

Run:

```powershell
npm run indexing:prepare-postgres
```

Expected:
- The prepare step reports `prepared`.
- The base tables exist.
- The active profiles match the vector tables that were created.

- [ ] **Step 3: Confirm the profile registry and vector tables**

Check:
- `indexing_profiles`
- `indexing_normalized_documents`
- `indexing_runs`
- `indexing_run_documents`
- `indexing_nodes`
- `idx_vec_*` tables for each active profile

Expected:
- One active profile maps to one physical vector table.
- No mixed-provider table is used for live writes.

- [ ] **Step 4: Record the readiness result**

Acceptance:
- PostgreSQL and pgvector are confirmed ready for live indexing.
- If the database is not ready, the rollout stops here.

---

### Task 3: Establish a dry-run baseline

**Files:**
- Review: `scripts/indexing/run_indexing.py`
- Review: `app/back/src/indexing/infrastructure/embeddings/factory.py`
- Test: `app/back/tests/indexing/test_run_indexing_cli.py`

**Interfaces:**
- Consumes: approved inventory records and the selected profile.
- Produces: a deterministic dry-run summary without database writes.

- [ ] **Step 1: Run the existing dry-run path**

Run:

```powershell
npm run indexing:run -- --dry-run
```

Expected:
- The command reports candidate and approved document counts.
- No PostgreSQL write occurs.
- The output is deterministic for the same inventory snapshot.

- [ ] **Step 2: Verify the `mock` lane remains test-only**

Run a dry-run with the `mock` profile if the existing runtime still allows it.

Expected:
- The dry-run completes.
- No live indexing is attempted.
- `mock` is treated as a verification aid, not as a production lane.

- [ ] **Step 3: Verify that dry-run does not mutate PostgreSQL**

Check:
- No rows are written to `indexing_nodes`.
- No rows are written to any `idx_vec_*` table.

Acceptance:
- Dry-run remains a safe preflight check.

---

### Task 4: Run a live PostgreSQL smoke with BGE

**Files:**
- Review: `scripts/indexing/run_indexing.py`
- Review: `app/back/src/indexing/infrastructure/postgres/node_repository.py`
- Review: `app/back/src/indexing/infrastructure/postgres/vector_repository.py`
- Review: `migrations/20260722_seed_indexing_profiles.sql`
- Test: `app/back/tests/indexing/infrastructure/postgres/test_postgres_live.py`

**Interfaces:**
- Consumes: a small approved corpus slice, `bge` profile metadata, `SST_POSTGRES_DSN`, and `--persist-confirmed`.
- Produces: durable rows in the node and vector tables for the selected `bge` profile.

- [ ] **Step 1: Choose the smallest safe corpus slice**

Pick:
- one approved document, or
- the smallest approved set that exercises parent and child node writes.

Expected:
- The smoke stays cheap and reversible.

- [ ] **Step 2: Run the live BGE indexing command**

Run:

```powershell
npm run indexing:run -- --store postgres --profile local-bge-m3-v1 --ingestion-origin local --persist-confirmed
```

Expected:
- The command succeeds against PostgreSQL.
- The selected profile writes only to its own vector table.
- The summary reports indexed parent and child counts.

- [ ] **Step 3: Verify the live rows**

Check:
- `indexing_nodes`
- `indexing_normalized_documents`
- `idx_vec_local_bge_m3_v1`

Expected:
- The document appears once.
- The child vectors exist in the BGE table.
- No other profile table was touched.

- [ ] **Step 4: Record the smoke result**

Acceptance:
- BGE live indexing is confirmed end to end.

Execution note:
- Confirmed through the live pytest smoke `app/back/tests/indexing/infrastructure/postgres/test_postgres_live.py`.
- Corpus slice used: `convivencia_laboral/manual/1772036012249_syc_mrh03sstmanualdeconv.md`.
- Observed result: 5 parent nodes, 5 child nodes, 5 rows in `indexing_nodes`, 5 rows in `idx_vec_local_bge_m3_v1`.

---

### Task 5: Run a live PostgreSQL smoke with Voyage (pendiente hasta recargar creditos y definir VOYAGE_API_KEY)

Estado para esta ejecucion:
- Pendiente.
- No se ejecuta hasta disponer de creditos y `VOYAGE_API_KEY`.
- El codigo queda preparado para retomarlo sin reescribir la ruta.

**Files:**
- Review: `scripts/indexing/run_indexing.py`
- Review: `app/back/src/indexing/infrastructure/embeddings/voyage.py`
- Review: `app/back/src/indexing/infrastructure/postgres/vector_repository.py`
- Review: `migrations/20260722_seed_indexing_profiles.sql`
- Test: `app/back/tests/indexing/infrastructure/postgres/test_postgres_live.py`

**Interfaces:**
- Consumes: a small approved corpus slice, `voyage` profile metadata, `SST_POSTGRES_DSN`, `VOYAGE_API_KEY`, and `--persist-confirmed`.
- Produces: durable rows in the Voyage vector table for the selected profile.

- [ ] **Step 1: Confirm Voyage credentials are available**

Run:

```powershell
Get-ChildItem Env:VOYAGE_API_KEY
```

Expected:
- The credential is present before any live Voyage smoke.

- [ ] **Step 2: Run the live Voyage indexing command**

Run:

```powershell
npm run indexing:run -- --store postgres --profile local-voyage-4-v1 --ingestion-origin local --persist-confirmed
```

Expected:
- The command succeeds against PostgreSQL.
- The selected profile writes only to its own vector table.
- The summary reports indexed parent and child counts.

- [ ] **Step 3: Verify the live rows**

Check:
- `indexing_nodes`
- `idx_vec_local_voyage_4_v1`

Expected:
- The document appears once.
- The child vectors exist in the Voyage table.
- No other profile table was touched.

- [ ] **Step 4: Record the smoke result**

Acceptance:
- Voyage live indexing is confirmed end to end.

---

### Task 6: Validate, observe, and define rollback

**Files:**
- Review: `scripts/indexing/validate_index.py`
- Review: `docs/runbooks/`
- Review: `docs/llama_first/README.md`

**Interfaces:**
- Consumes: the live PostgreSQL state produced by the smoke tests.
- Produces: a go/no-go validation result and a rollback note if needed.

- [ ] **Step 1: Run index validation**

Run:

```powershell
npm run indexing:validate
```

Expected:
- The validation passes for the live smoke rows, or it reports a precise blocker.

- [ ] **Step 2: Run the indexing test suite**

Run:

```powershell
npm run test:indexing
```

Expected:
- The focused indexing tests pass.
- Any failure is tied to a specific provider, profile, or repository contract.

- [ ] **Step 3: Summarize the live result**

Record:
- provider used
- profile used
- document count
- parent node count
- child node count
- vector table written
- any warnings or blockers

Acceptance:
- The run is reproducible from the command line.
- The rollback path is known before any broader rollout.

- [ ] **Step 4: Decide go / no-go**

Go only if:
- PostgreSQL is ready.
- BGE and Voyage both completed a smoke without cross-profile contamination.
- Validation passes.
- `mock` remains test/dry-run only.

No-go if:
- Any provider other than `bge` or `voyage` is reachable in live production.
- Any mixed-provider or mixed-dimension write appears.
- The DSN or credentials are missing.

---

## Definition Of Done

- `bge` and `voyage` are the only productive providers.
- `mock` is only used for tests and dry-run.
- PostgreSQL and pgvector are confirmed ready.
- Live BGE smoke passes.
- Live Voyage smoke passes.
- Validation passes on the live smoke rows.
- The rollout notes capture the exact command line and result.
- No code changes were made during this planning pass.
