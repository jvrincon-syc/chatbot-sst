# Task 2 Brief — Portable Identity, Typed Manifests and Atomic Bundles

Read first:

- Global Constraints and Task 2 in `docs/superpowers/plans/2026-07-17-robust-pdf-ingestion-schema2.md`.
- Canonical schema interfaces implemented by Task 1.

## Scope

Create:

- `app/back/src/ingestion/paths.py`
- `app/back/src/ingestion/schemas/manifests.py`
- `app/back/src/ingestion/manifests/bundle_writer.py`
- `app/back/tests/ingestion/test_identity.py`
- `app/back/tests/ingestion/test_bundle_writer.py`

Modify:

- `app/back/src/ingestion/inventory/scanner.py`
- `app/back/src/ingestion/manifests/writer.py`
- `app/back/src/ingestion/schemas/inventory.py` only to add the required `identity_version` field
- `app/back/src/ingestion/schemas/__init__.py` only for exports
- `scripts/ingestion/export_schemas.py`
- `app/back/tests/ingestion/test_inventory.py`

Do not modify pipeline, readers, validation, classification, normalized corpus, dependencies, docs, memory, secrets or `.tmp/`.

## Required behavior

### Identity and artifact paths

- `canonical_relpath(value)` returns a safe POSIX raw-root-relative path and rejects absolute paths, drive paths, backslashes, empty components, `.` and `..`.
- `stable_document_id(source_relpath)` preserves the existing algorithm: `doc_` plus 16 SHA-1 hex characters over the canonical POSIX relative path.
- `ArtifactPaths.for_source(source_relpath)` removes only the final source extension.
- It appends these suffixes literally: `.md`, `.metadata.json`, `.pages.json`, `.ocr.json`, `.tables.json`, `.forms.json`.
- These stems must remain distinct and complete:
  - `1761580555950_syc_RE.RH-04SST23102025.pdf`
  - `1761609513260_syc_RG.RH-01-SST23102025.pdf`
  - `1711493199040_syc_pg-rh-10-sst.program.pdf`
- `preflight_artifact_paths(sources)` rejects any collision before a write.
- Moving `raw_root` must not change `source_relpath`, artifact relpaths or document ID.

### Scanner

- `scan_docs_raw` emits canonical schema 2.0 `InventoryRecord`.
- Persist `source_relpath`, never an absolute `source_path`.
- Use `identity_version="relpath-posix-v1"`.
- Preserve content hash, extension/signature detection, MIME, category and stable ID.
- Persistent status starts `pending`; it never stores `skipped`.
- Duplicate content remains detectable through `content_hash`.

### Manifest contracts

Create strict schema 2.0 models:

- `ArtifactHash`: `relpath`, SHA-256, byte size.
- `BundleManifest`: document ID, source relpath/hash, normalized base, required artifact set, artifact hashes, processing fingerprint, document status.
- `InventoryManifest`: schema/version metadata plus records list.
- `RunDocument`: document ID, source relpath, canonical document status and run disposition (`processed`, `reprocessed`, `reused`, `failed`, `needs_review`).
- `RunManifest`: run ID/timestamp/fingerprints/summary/documents/bundles.
- `ReviewItem`, `ReviewManifest`, `ErrorItem`, `ErrorManifest`.
- All use `extra="forbid"` and literal `schema_version="2.0"`.
- Inventory root is a versioned envelope, not a list.

### Atomic writing

- `dump_json_atomic(path, payload)` validates that top-level ingestion outputs are canonical 2.0 models/envelopes, serializes UTF-8 with deterministic indentation and replaces through a same-directory temp file using `os.replace`.
- `write_text_atomic` follows the same temp/replace discipline.
- On serialization/write/replace failure, temp files are removed and an existing target remains unchanged.
- `write_bundle_atomic(candidate_root, bundle_payload)` writes the complete candidate bundle only within `candidate_root`, computes hashes after writes and returns a `BundleManifest`.
- It rejects absolute/traversing artifact relpaths and a bundle whose artifact document IDs disagree.
- It must not write a schema 1.0 model/dict as new output.
- Artifact hashes live in bundle/run manifests, not within metadata.
- A candidate bundle contains only the required sidecars; omitted obsolete sidecars are absent from the candidate.

### Schema export

Export JSON Schemas for metadata, pages, OCR, tables, forms, inventory, run, review, errors and bundle manifests. Generated schema must declare `additionalProperties: false`.

## TDD

1. Write identity tests and verify RED.
2. Implement path helpers/scanner and verify GREEN.
3. Write manifest/atomic bundle tests and verify RED.
4. Implement models/writers and verify GREEN.
5. Run:

   ```powershell
   .venv\Scripts\python.exe -m pytest app/back/tests/ingestion/test_identity.py app/back/tests/ingestion/test_bundle_writer.py app/back/tests/ingestion/test_inventory.py -q -p no:cacheprovider
   ```

6. Run `compileall` for changed production modules.
7. Run the full ingestion suite once and report remaining planned migration failures exactly.
8. Do not commit; the user made a concurrent commit during Task 1 and the controller owns integration.

Write the detailed report to `.superpowers/sdd/task-2-report.md`, including RED/GREEN evidence, files, test counts and concerns.
