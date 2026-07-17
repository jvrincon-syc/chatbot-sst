# Task 1 Report — Strict Schema 2.0 Contracts and Legacy Adapter

Status: **DONE_WITH_CONCERNS**

Date: 2026-07-17

## Summary

Implemented the strict schema 2.0 primitives and canonical artifacts, a
separate permissive schema 1.0 model family, explicit version dispatch, and
the schema 1.0 to 2.0 adapter.

The focused Task 1 regression is green. The full ingestion suite still has 19
failures because the scanner, readers, pipeline, and validator instantiate
canonical models with legacy 1.0 arguments. Those consumers belong to Tasks
2, 4, 5, 6, and 7 and were explicitly outside this brief.

## TDD evidence

### RED — primitive and canonical artifact contracts

Command:

```powershell
.venv\Scripts\python.exe -m pytest app/back/tests/ingestion/test_schemas_v2.py -q
```

Observed expected failure:

```text
ERROR collecting app/back/tests/ingestion/test_schemas_v2.py
ImportError: cannot import name 'Classification' from
'ingestion.schemas.artifacts'
1 error in 0.63s
```

The failure was caused by the missing schema 2.0 contract, not a test typo.
No production implementation had been added before this run.

### RED — legacy adapter and loader

Command:

```powershell
.venv\Scripts\python.exe -m pytest app/back/tests/ingestion/test_legacy_adapter.py -q
```

Observed expected failure:

```text
ERROR collecting app/back/tests/ingestion/test_legacy_adapter.py
ModuleNotFoundError: No module named 'ingestion.schemas.adapters'
1 error in 0.29s
```

The failure was caused by the missing adapter module. The legacy tests had
been written before implementing `legacy_v1.py`, `adapters.py`, or
`loader.py`.

### Intermediate GREEN

Command:

```powershell
.venv\Scripts\python.exe -m pytest app/back/tests/ingestion/test_schemas_v2.py app/back/tests/ingestion/test_legacy_adapter.py -q -p no:cacheprovider
```

Result:

```text
46 passed in 0.52s
```

### Required focused GREEN and compatibility regression

Command:

```powershell
.venv\Scripts\python.exe -m pytest app/back/tests/ingestion/test_schemas_v2.py app/back/tests/ingestion/test_legacy_adapter.py app/back/tests/ingestion/test_schemas.py -q -p no:cacheprovider
```

Final result after cleanup:

```text
49 passed in 0.32s
```

## Contract coverage

- `StrictModel` uses `ConfigDict(extra="forbid")`.
- Canonical top-level artifact and inventory models require literal
  `schema_version="2.0"`; no version defaults are present.
- Canonical paths reject absolute paths, drive paths, backslashes, empty
  components, `.` and `..`.
- `BBox` requires positive area and records its coordinate system.
- `Evidence` retains page, bbox, region, text, pattern, source, and warnings.
- Boolean observations enforce the three valid status/value/provenance
  combinations.
- Confidence metrics distinguish measured, estimated, and unavailable
  provenance and enforce the required measured fields.
- Numeric measurements such as rotation use `MeasuredValue`, not
  `Observation`.
- Pages retain raw/normalized text, blocks, removed spans, normalization
  actions, warnings, and typed OCR confidence.
- OCR retains word geometry/confidence and typed page/document confidence.
- Tables retain geometry, indexed/spanned cells, representation, extractor,
  quality, and warnings.
- Forms use a dedicated `FormsArtifact` with groups, labels, controls,
  selections, blank areas, associations, and geometry.
- Metadata retains document-control fields, independent type/topic
  confidence, signals/conflicts, feature observations, review reasons, and
  portable paths. Artifact hashes were not added to metadata.
- Inventory uses schema 2.0 source-relative identity and excludes `skipped`
  from persistent statuses.
- Legacy 1.0 models are separate and permissive; canonical 2.0 models remain
  strict.
- Loader dispatch is closed to missing or unknown versions.
- All legacy OCR confidence values, including `0.0` and `1.0`, become
  `estimated`.
- Legacy false/missing handwriting and table flags become `not_evaluated`.
- Legacy true flags become evidence-backed `legacy_assertion` detections with
  `legacy_detection_unverified`.
- Null legacy document-control fields become `not_evaluated`.
- Known-root absolute legacy paths are relativized. Unknown absolute paths
  are retained only in `legacy_path`, while canonical paths use safe relative
  placeholders and warnings.

## Full ingestion suite

First sandboxed run was not usable as a compatibility signal because pytest
could not access its Windows temporary directory:

```text
57 passed, 24 errors
PermissionError: ...\AppData\Local\Temp\pytest-of-jvrincon
```

The suite was rerun outside the filesystem sandbox so `tmp_path` fixtures
could execute.

Command:

```powershell
.venv\Scripts\python.exe -m pytest app/back/tests/ingestion -q -p no:cacheprovider
```

Result:

```text
19 failed, 62 passed in 0.94s
```

Failures by planned downstream coupling:

- Inventory/scanner/pipeline (8): scanner and old fixtures still pass
  `source_path` and omit required `schema_version`/`source_relpath`.
  Affected tests:
  - `test_pipeline_marks_ambiguous_classification_as_needs_review`
  - all 3 tests in `test_inventory.py`
  - `test_pipeline_falls_back_to_ocr_when_pdf_text_extractor_is_missing`
  - all 3 tests in `test_pipeline_integration.py`
- Readers (5): legacy readers still omit typed OCR confidence or pass a
  float and the removed boolean handwriting field directly.
  Affected tests:
  - both Markdown reader tests
  - both digital PDF reader tests
  - scanned PDF reader test
- Validation (6): the current validator directly instantiates strict
  canonical models from 1.0 payloads instead of dispatching through
  `load_artifact`.
  Affected tests:
  - processed Markdown acceptance
  - auxiliary document ID mismatch
  - page count mismatch
  - inventory source hash mismatch
  - status manifest coverage
  - pending inventory status

No out-of-scope scanner, reader, pipeline, or validation code was changed.

## Additional verification

Commands:

```powershell
.venv\Scripts\python.exe -m compileall -q app/back/src/ingestion/schemas
.venv\Scripts\python.exe -c "<generate JSON Schema for all six public top-level models>"
```

Results:

```text
compileall: passed
generated 6 schemas
```

Ruff was not available in the environment:

```text
No module named ruff
```

No dependency was installed or changed.

## Files changed

Created:

- `app/back/src/ingestion/schemas/common.py`
- `app/back/src/ingestion/schemas/legacy_v1.py`
- `app/back/src/ingestion/schemas/adapters.py`
- `app/back/src/ingestion/schemas/loader.py`
- `app/back/tests/ingestion/test_schemas_v2.py`
- `app/back/tests/ingestion/test_legacy_adapter.py`
- `.superpowers/sdd/task-1-report.md`

Modified:

- `app/back/src/ingestion/schemas/artifacts.py`
- `app/back/src/ingestion/schemas/inventory.py`
- `app/back/src/ingestion/schemas/__init__.py`
- `app/back/tests/ingestion/test_schemas.py` because its implicit schema 1.0
  defaults and float confidence assertions were obsolete under the canonical
  2.0 contract.

No commit was created by this worker.

## Concerns and handoff

1. The full suite cannot become green until the planned downstream tasks
   migrate constructors and validators to schema 2.0 or use the explicit
   loader for 1.0 input.
2. `TableRecord.bbox` is nullable specifically so a legacy table with no
   stored geometry can be adapted without inventing coordinates. New
   extractors should always populate it and validators may require it in
   closure mode.
3. A schema 1.0 forms artifact is rejected because that artifact did not
   exist in the 1.0 contract.
4. Ruff could not be run because it is not installed; compile and JSON Schema
   generation succeeded.

## Fix review findings

The Task 1 reviewer identified two important and two minor findings. They
were addressed with a new RED→GREEN cycle without changing files outside the
Task 1 brief.

### Review RED

Command:

```powershell
.venv\Scripts\python.exe -m pytest app/back/tests/ingestion/test_schemas_v2.py app/back/tests/ingestion/test_legacy_adapter.py -q -p no:cacheprovider
```

Observed result:

```text
10 failed, 46 passed in 0.57s
```

The ten expected failures proved:

- Pydantic coerced boolean confidence and measurement values to floats before
  the old after-validator could reject them.
- Legacy metadata/OCR boolean confidence inputs were accepted.
- `MetadataArtifact` could retain only one of two non-relativizable absolute
  legacy paths.
- Metadata OCR engine provenance was not copied to its estimated confidence.
- Unsafe relative traversal emitted the absolute-path warning.

### Review GREEN

Changes:

- Added a reusable `BeforeValidator` numeric type that rejects booleans before
  Pydantic float coercion.
- Applied it to `ConfidenceMetric`, `MeasuredValue`, OCR word confidence, all
  legacy confidence fields, legacy table quality, and legacy rotation.
- Added `legacy_source_path` and `legacy_normalized_path` while retaining
  `legacy_path` as the compatibility source-first alias.
- Preserved `ocr_engine` on adapted metadata confidence and OCR
  engine/version on adapted OCR document/page confidence.
- Split unsafe-relative traversal diagnosis into
  `legacy_relative_path_unsafe`; absolute paths retain
  `legacy_absolute_path_not_relativized`.

Command:

```powershell
.venv\Scripts\python.exe -m pytest app/back/tests/ingestion/test_schemas_v2.py app/back/tests/ingestion/test_legacy_adapter.py app/back/tests/ingestion/test_schemas.py -q -p no:cacheprovider
```

Observed result:

```text
59 passed in 0.38s
```
