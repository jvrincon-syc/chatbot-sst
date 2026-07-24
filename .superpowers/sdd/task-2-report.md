# Task 2 Report: Schema 2 Normalized Source

## Status

Completed without a commit.

## Delivered

- Added `Schema2NormalizedDocumentSource`, rooted to `docs_normalized`, to load
  Markdown and validate Schema 2 metadata, pages, tables, forms, and OCR
  sidecars through the existing `ingestion.schemas.loader.load_artifact`.
- Required Markdown, metadata, and pages sidecars are fail-closed. Tables,
  forms, and OCR are optional and may be present independently.
- Reworked `NormalizedDocumentBundle` into the pre-structural contract needed
  for Task 2/3: literal Markdown, source/page traces, validated sidecar data,
  and warnings. It no longer contains `StructuralBlock` instances.
- Added `SourceSpanResolver`, which prefers Markdown `<!-- page: N -->`
  markers, uses ordered unique `pages.json.text_normalized` alignment only as
  a fallback, and emits `PAGE_TRACE_UNRESOLVED` when neither is safe.
- Added validation for root confinement, traversal attempts, normalized path,
  sidecar `document_id`, and any identifying front-matter values that are
  present (`document_id`, `source_relpath`, `source_hash`).
- Preserved literal Markdown, page raw/normalized text, table Markdown, and
  form titles. OCR confidence is `None` when its sidecar is absent; no value
  or structural block is invented.

## TDD Evidence

1. Added the integration tests before the infrastructure adapter existed.
2. RED run: collection failed with `ModuleNotFoundError: chunking.infrastructure`,
   confirming the test exercised the absent feature.
3. Implemented the minimal source loader and resolver.
4. Added a second RED assertion for retaining validated table/form values;
   it failed because `ValidatedSidecars` lacked `table_markdown`.
5. Added the minimal domain mapping and confirmed GREEN.

## Verification

Required command:

```powershell
$env:TMP=(Resolve-Path '.').Path + '\pytest-temp'; $env:TEMP=$env:TMP; New-Item -ItemType Directory -Force -Path $env:TMP | Out-Null; .\.venv_windows_trabajo\Scripts\python.exe -m pytest app/back/tests/chunking/integration/test_schema2_source.py -q --basetemp .\pytest-basetemp-task2
```

Result: `6 passed in 0.13s`.

Additional regression:

```powershell
.\.venv_windows_trabajo\Scripts\python.exe -m compileall -q app\back\src\chunking
.\.venv_windows_trabajo\Scripts\python.exe -m pytest app/back/tests/chunking/unit/test_domain_models.py app/back/tests/chunking/integration/test_schema2_source.py -q --basetemp .\pytest-basetemp-task2-regression
```

Result: compilation passed and `22 passed in 0.14s`.

## Files Changed

- `app/back/src/chunking/application/source_span_resolver.py`
- `app/back/src/chunking/infrastructure/__init__.py`
- `app/back/src/chunking/infrastructure/schema2_source.py`
- `app/back/src/chunking/domain/models.py`
- `app/back/tests/chunking/integration/test_schema2_source.py`
- `app/back/tests/chunking/unit/test_domain_models.py`

## Concerns

- `pytest` integration execution is environment-sensitive on this Windows
  workspace because `tmp_path` and later symlink cleanup can hit permission
  errors unrelated to the loader logic.
- The working tree already contained unrelated modified and untracked files;
  they were not altered by this task.

## Review Fixes

Applied the Task 2 review findings without changing parser, indexing, or other
non-Task-2 code.

- Marker resolution is now fail-closed: duplicate marker numbers or a marker
  page number absent from `pages.json` produce `PAGE_TRACE_UNRESOLVED` and do
  not fall back to a conflicting text alignment.
- The source loader rejects bundles where `metadata.page_count` differs from
  `pages.page_count`.
- Every derived sidecar path is resolved before access and rejected when its
  resolved target escapes the configured `docs_normalized` root, including via
  a symlink.
- Removed the unused `cast` import from `schema2_source.py`.

### Review TDD Evidence

Added three regression tests first:

1. A Markdown marker for pages absent from `pages.json` must abstain rather
   than create empty page traces.
2. Mismatched metadata/pages counts must be rejected.
3. A metadata-sidecar symlink escaping the normalized root must be rejected.

The RED run produced the first two expected failures. The symlink test was
collected but skipped because symlink creation is not permitted in this
Windows test session; it remains a regression test for environments where
symlinks are available.

### Review Verification

```powershell
$env:TMP=(Resolve-Path '.').Path + '\pytest-temp'; $env:TEMP=$env:TMP; New-Item -ItemType Directory -Force -Path $env:TMP | Out-Null; .\.venv_windows_trabajo\Scripts\python.exe -m pytest app/back/tests/chunking/integration/test_schema2_source.py -q --basetemp .\pytest-basetemp-task2-fix
```

Result: `8 passed, 1 skipped in 0.15s`.

## Final Review Fix

`SourceSpanResolver` now rejects duplicate `page_number` values in
`pages.json` before it attempts marker or text-alignment resolution. This
prevents a later page record from overwriting an earlier record in the page
lookup dictionary and returns `PAGE_TRACE_UNRESOLVED` instead.

### Final Review TDD Evidence

Added a regression test with one valid Markdown page marker and two
`pages.json` entries for page `1`. The RED run showed that the resolver used
the later page record. The resolver now detects duplicate source page numbers
at the beginning of `resolve` and abstains before constructing the lookup.

### Final Review Verification

```powershell
$env:TMP=(Resolve-Path '.').Path + '\pytest-temp'; $env:TEMP=$env:TMP; New-Item -ItemType Directory -Force -Path $env:TMP | Out-Null; .\.venv_windows_trabajo\Scripts\python.exe -m pytest app/back/tests/chunking/integration/test_schema2_source.py -q --basetemp .\pytest-basetemp-task2-fix2
```

Result: `9 passed, 1 skipped in 0.17s`.

## Post-Review Closures

Applied additional review-driven hardening after the focused review rounds:

- `ChunkingRun` again fail-closes on `parent.block_ids` by requiring
  `document.structural_blocks` and rejecting missing references.
- Marker-based page resolution now abstains when Markdown markers move
  backwards, not only when they duplicate or reference unknown pages.
- `Schema2NormalizedDocumentSource` now requires front-matter parity for
  `document_id` and `source_relpath`, while keeping `source_hash` optional
  because the normalized pipeline does not currently emit it in front matter.

### Manual Integration Verification

Because `pytest` fixture temp roots are permission-constrained in this
workspace, the Schema 2 integration assertions were also executed manually
against workspace-local temp directories using the exact test functions.

Result:

- 11 integration assertions passed.
- 1 symlink-escape regression remained skipped because symlink creation is not
  permitted in this environment.
