# Task 1 Brief — Strict Schema 2.0 Contracts and Legacy Adapter

Read first:

- `docs/superpowers/specs/2026-07-17-robust-pdf-ingestion-quality-design.md`
- Task 1 and Global Constraints in `docs/superpowers/plans/2026-07-17-robust-pdf-ingestion-schema2.md`

## Scope

Create:

- `app/back/src/ingestion/schemas/common.py`
- `app/back/src/ingestion/schemas/legacy_v1.py`
- `app/back/src/ingestion/schemas/adapters.py`
- `app/back/src/ingestion/schemas/loader.py`
- `app/back/tests/ingestion/test_schemas_v2.py`
- `app/back/tests/ingestion/test_legacy_adapter.py`

Modify only as needed:

- `app/back/src/ingestion/schemas/artifacts.py`
- `app/back/src/ingestion/schemas/inventory.py`
- `app/back/src/ingestion/schemas/__init__.py`
- Existing schema tests only if canonical 2.0 behavior makes their old assertions obsolete.

Do not modify pipeline, readers, validation, normalized corpus, dependency files, `secrets.example.env`, `.tmp/`, docs or memory.

## Required public contract

- `StrictModel` uses Pydantic `ConfigDict(extra="forbid")`.
- Every canonical top-level artifact requires the literal `schema_version="2.0"`; it must not be silently defaulted when loading arbitrary payloads.
- `ExtractionMethod` accepts `markdown`, `pdf_digital`, `ocr`, `hybrid`.
- Canonical paths are relative POSIX strings with no drive, leading slash, `.` or `..`.
- `BBox` records `x0`, `top`, `x1`, `bottom`, `coordinate_system` and validates positive area.
- `Evidence` can identify page, optional bbox/region, text, pattern, source and warnings.
- Boolean `Observation` obeys:
  - `detected`: value true and non-empty evidence;
  - `not_detected`: value false and a named capable engine/method;
  - `not_evaluated`: value null;
  - no other combination is valid.
- `ConfidenceMetric` obeys:
  - `measured`: numeric 0..1, engine, engine_version, unit and positive sample_size;
  - `estimated`: numeric 0..1 and method/provenance;
  - `unavailable`: null value.
- `MeasuredValue` represents numeric metrics such as rotation and carries status/provenance; rotation must not reuse boolean `Observation`.
- `DocumentField` carries `value`, `value_raw`, `status`, evidence and warnings.
- Page model preserves raw/normalized text, blocks, removed spans, normalization actions, warnings and typed OCR confidence.
- OCR model preserves words with bboxes/confidence, page metrics and document metric.
- Table model preserves bbox, cells, row/column indices and spans, representation, extractor/quality and warnings.
- Form model preserves groups, labels, controls/blank areas, selections and geometry in a dedicated `FormsArtifact`.
- Metadata includes canonical title/code/version/dates under document control, independent type/topic confidences/signals/conflicts, feature observations, review reasons and portable paths.
- Inventory is schema 2.0 and uses source-relative identity. Persistent status excludes `skipped`.
- Canonical public names remain `MetadataArtifact`, `PagesArtifact`, `OcrArtifact`, `TablesArtifact`, `FormsArtifact`, `InventoryRecord`.

## Legacy behavior

- Define exact permissive 1.0 shapes separately; do not weaken canonical 2.0 models.
- `load_artifact(payload, artifact_type, context)` dispatches only on explicit `1.0` or `2.0`; missing/unknown versions raise a clear error.
- Writer concerns are outside this task, but adapter output is always canonical 2.0.
- Every legacy OCR confidence becomes `estimated`, including values other than 1.0.
- Legacy false or missing handwriting/tables becomes `not_evaluated`.
- Legacy true feature becomes `detected` with evidence describing the legacy assertion, method `legacy_assertion` and warning `legacy_detection_unverified`.
- Legacy null document-control fields without extractor provenance become `not_evaluated`.
- Absolute legacy paths are relativized only when under a supplied known root. Otherwise preserve them in `legacy_path` and add a warning; canonical relpath must remain a safe relative placeholder rather than the absolute value.

## TDD and compatibility

1. Write focused failing tests before production code.
2. Run them and record the expected RED output.
3. Implement the minimum contract.
4. Run focused tests GREEN.
5. Run all existing ingestion tests and keep compatibility through the loader/adapter where feasible.
6. Do not commit; the controller owns repository integration in this dirty checkout.

Write the detailed implementation report to `.superpowers/sdd/task-1-report.md`, including RED and GREEN commands/output, files changed, full-suite result and concerns.
