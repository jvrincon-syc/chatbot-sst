# Task 3 Report: PostgreSQL raw and normalized physical catalogs

## Implementation

- Added `PostgresRawArtifactCatalogRepository` for parameterized, idempotent
  upserts into `project_raw_document_artifacts` by
  `source_document_revision_id`.
- Added `PostgresNormalizedArtifactCatalogRepository` for parameterized upserts
  by the existing physical identity `(project_id, source_document_revision_id,
  processing_profile_fingerprint)`. The upsert refreshes nullable
  `rag_variant_id` and `semantic_recipe_fingerprint` as provenance without
  changing `normalized_document_id` identity.
- Reused `RawDocumentArtifactRecord`, `NormalizedDocumentArtifactRecord`, and
  their shared `PlatformArtifactProvenance`; no parallel provenance contract
  was introduced.

## DDL Decision

`20260812_01_create_project_raw_and_normalized_artifact_catalogs.sql` already
defines the catalog tables, their physical identity, direct FKs, checks, and
the needed lookup indexes. `20260812_02_add_normalized_catalog_fk_indexes.sql`
adds only the complementary composite uniqueness and FKs needed to keep a
normalized catalog row scoped to the same project as its processing profile and
optional RAG variant. It adds no speculative index and does not redesign `01`.

## Tests

Red evidence:

```text
C:\venvs\chatbot-sst\Scripts\python.exe -m pytest app\back\tests\rag_platform\test_postgres_artifact_catalog_repositories.py -q
ERROR: ModuleNotFoundError: ...artifact_catalog_repositories
```

Green and affected regression evidence:

```text
C:\venvs\chatbot-sst\Scripts\python.exe -m pytest app\back\tests\rag_platform\test_postgres_artifact_catalog_repositories.py app\back\tests\indexing\test_prepare_postgres_indexing.py -q
9 passed

C:\venvs\chatbot-sst\Scripts\python.exe -m pytest app\back\tests\rag_platform\test_artifact_catalog_models.py app\back\tests\rag_platform\test_postgres_artifact_catalog_repositories.py app\back\tests\indexing\test_prepare_postgres_indexing.py -q
15 passed
```

Pytest emitted only an existing cache-directory permission warning; no test
warnings or failures originated in Task 3 code.

## Self-review

- SQL is parameterized and catalogs remain physical projections, not logical
  identity replacements.
- Provenance remains nullable and is not part of either conflict target.
- Migration ordering is covered by `prepare_postgres` tests.
- The commit is limited to the Task 3 write set; unrelated Task 2/6 worktree
  changes were not staged.
