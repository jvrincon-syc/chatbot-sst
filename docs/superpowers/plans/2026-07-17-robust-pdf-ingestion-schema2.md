# Robust PDF Ingestion Schema 2.0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Regenerate the nine audited PDFs as faithful, portable and semantically validated schema 2.0 bundles without invented confidence or negative detections.

**Architecture:** The implementation introduces strict versioned contracts, capability-aware extraction interfaces and a candidate-tree pipeline. Digital layout, regional OCR, tables, forms, boilerplate, classification and document-control evidence remain separate components joined by a hybrid reconciler. Existing 1.0 artifacts are readable through an explicit adapter; all new writes are 2.0 and promotion happens only after structural and golden validation.

**Tech Stack:** Python 3.12, Pydantic 2.10, pypdf, pdfplumber, pypdfium2, Pillow, pytesseract, NumPy, OpenCV headless, pytest.

## Global Constraints

- Canonical `source_relpath` is POSIX and relative to `raw_root`; canonical `normalized_relpath` is POSIX and relative to `normalized_root`.
- Golden source locators are repository-relative and are normalized by stripping the configured raw-root prefix before artifact comparison.
- `document_id` remains `doc_` plus the first 16 hex characters of SHA-1 over the normalized raw-root-relative POSIX path.
- Readers accept explicit schema `1.0` and `2.0`; missing or unknown schema versions fail closed; writers emit only `2.0`.
- Pydantic 2.0 models use `extra="forbid"` and require `schema_version`.
- `detected` always requires evidence; `not_detected` requires a named capable detector; unavailable capability is `not_evaluated` with `value=null`.
- OCR confidence is nullable and is `measured` only when emitted by a capable OCR backend with engine, version, unit and sample size.
- Every legacy OCR confidence is adapted as `estimated`; legacy false or missing feature booleans become `not_evaluated`.
- A legacy true feature becomes `detected` with `method="legacy_assertion"` and an `legacy_detection_unverified` warning; it is not sufficient for automatic approval.
- Rotation degrees use a typed measurement, not a boolean observation.
- Forms are written to a dedicated `.forms.json` artifact.
- The document-type taxonomy keeps existing Phase 1 types and adds `programa` and `matriz`.
- Filename timestamps are provenance signals only and never documentary dates.
- `skipped` is a run disposition; persistent document status remains the last validated `processed`, `needs_review` or `failed`.
- No PostgreSQL, chunking, embeddings, RAG or manual rewriting of normalized PDFs is included.
- Names, dates, percentages, identifiers, codes, legal articles, deadlines and table values must not be silently corrected.
- `secrets.example.env`, unrelated user changes and pre-existing `.tmp/` audit material are outside the implementation scope.

---

### Task 1: Strict Schema 2.0 Contracts and Legacy Adapter

**Files:**
- Create: `app/back/src/ingestion/schemas/common.py`
- Create: `app/back/src/ingestion/schemas/legacy_v1.py`
- Create: `app/back/src/ingestion/schemas/adapters.py`
- Create: `app/back/src/ingestion/schemas/loader.py`
- Modify: `app/back/src/ingestion/schemas/artifacts.py`
- Modify: `app/back/src/ingestion/schemas/inventory.py`
- Test: `app/back/tests/ingestion/test_schemas_v2.py`
- Test: `app/back/tests/ingestion/test_legacy_adapter.py`

**Interfaces:**
- Produces: `StrictModel`, `BBox`, `Evidence`, `Observation`, `ConfidenceMetric`, `MeasuredValue`, `PageBlock`, `RemovedSpan`, `NormalizationAction`.
- Produces: canonical `MetadataArtifact`, `PagesArtifact`, `OcrArtifact`, `TablesArtifact`, `FormsArtifact`, all schema `2.0`.
- Produces: `load_artifact(payload, artifact_type, context)` and `adapt_v1_to_v2(...)`.

- [ ] **Step 1: Write failing primitive-contract tests**

  Cover required schema version, rejected extras, POSIX relative paths, traversal rejection, all observation invariants, measured confidence provenance and nullable/unavailable confidence.

- [ ] **Step 2: Verify RED**

  Run:

  ```powershell
  .venv\Scripts\python.exe -m pytest app/back/tests/ingestion/test_schemas_v2.py -q
  ```

  Expected: collection/import failures because schema 2.0 primitives do not exist.

- [ ] **Step 3: Implement strict primitives**

  Use `ConfigDict(extra="forbid")`. `Observation` supports only boolean feature observations; `MeasuredValue` carries numeric rotation/deskew measurements separately. `BBox` stores page coordinates plus coordinate system.

- [ ] **Step 4: Write failing artifact relationship tests**

  Cover `hybrid`, page blocks, removed spans, normalization actions, OCR words, table cells/spans, form label/control associations, document-control fields, independent classification confidences, conflicts, review reasons and artifact hashes in manifests rather than self-referential metadata.

- [ ] **Step 5: Implement canonical artifacts**

  Preserve public artifact class names to reduce import churn. Add `FormsArtifact`; keep all historic document types plus `programa`, `matriz` and `otro`.

- [ ] **Step 6: Write failing legacy dispatch tests**

  Assert explicit 1.0/2.0 dispatch, missing/unknown rejection, all legacy confidence as `estimated`, false/missing observations as `not_evaluated`, true observations as warned legacy assertions, nullable document fields as `not_evaluated`, and absolute path handling with/without known roots.

- [ ] **Step 7: Implement exact legacy models, adapter and loader**

  Never instantiate canonical models directly from unknown-version dictionaries. Preserve non-relativizable absolute paths only in `legacy_path` with a warning.

- [ ] **Step 8: Verify GREEN and regression**

  ```powershell
  .venv\Scripts\python.exe -m pytest app/back/tests/ingestion/test_schemas_v2.py app/back/tests/ingestion/test_legacy_adapter.py app/back/tests/ingestion/test_schemas.py -q
  ```

---

### Task 2: Portable Identity, Typed Manifests and Atomic Bundles

**Files:**
- Create: `app/back/src/ingestion/paths.py`
- Create: `app/back/src/ingestion/schemas/manifests.py`
- Create: `app/back/src/ingestion/manifests/bundle_writer.py`
- Modify: `app/back/src/ingestion/inventory/scanner.py`
- Modify: `app/back/src/ingestion/manifests/writer.py`
- Modify: `scripts/ingestion/export_schemas.py`
- Test: `app/back/tests/ingestion/test_identity.py`
- Test: `app/back/tests/ingestion/test_bundle_writer.py`

**Interfaces:**
- Produces: `ArtifactPaths.for_source(source_relpath)` that removes only the final source extension and appends artifact suffixes literally.
- Produces: versioned `InventoryManifest`, `RunManifest`, `ReviewManifest`, `ErrorManifest`, `BundleManifest`.
- Produces: `write_bundle_atomic(candidate_root, bundle)` and `compute_artifact_hashes(...)`.

- [ ] **Step 1: Write failing identity/path tests**

  Assert stable IDs after moving roots, POSIX relpaths, traversal/absolute rejection, preservation of `RE.RH-04...`, `RG.RH-01...` and `.program` stems, plus preflight collision detection.

- [ ] **Step 2: Verify RED and implement path helpers**

  Replace chained `with_suffix()` behavior with one source-extension removal and literal suffix appending.

- [ ] **Step 3: Write failing manifest and atomic-write tests**

  Assert schema 2.0 envelopes, artifact hashes, temp-file replacement, cleanup after failure and refusal to serialize legacy models as new output.

- [ ] **Step 4: Implement typed manifests and candidate bundle writer**

  Write every JSON and Markdown through same-directory temporary files followed by `os.replace`. Bundle hashes live in the bundle/run manifest.

- [ ] **Step 5: Update inventory scanner**

  Persist `source_relpath`, not absolute source path; include `identity_version="relpath-posix-v1"` and preserve canonical document status independently from run disposition.

- [ ] **Step 6: Export all schema 2.0 JSON Schemas**

  Include metadata, pages, OCR, tables, forms, inventory and run/review/error manifests.

- [ ] **Step 7: Verify GREEN**

  ```powershell
  .venv\Scripts\python.exe -m pytest app/back/tests/ingestion/test_identity.py app/back/tests/ingestion/test_bundle_writer.py app/back/tests/ingestion/test_inventory.py -q
  ```

---

### Task 3: Document Control and Evidence-First Classification

**Files:**
- Create: `app/back/src/ingestion/document_control/extractor.py`
- Create: `app/back/src/ingestion/document_control/__init__.py`
- Replace: `app/back/src/ingestion/classification/rules.py`
- Test: `app/back/tests/ingestion/test_document_control.py`
- Modify: `app/back/tests/ingestion/test_classification.py`

**Interfaces:**
- Produces: `extract_document_control(pages, filename) -> DocumentControl`.
- Produces: `classify_document(source_relpath, pages, document_control) -> ClassificationResult`.

- [ ] **Step 1: Write failing control-field tests**

  Cover repeated header evidence deduplication, raw/normalized code, version, visible date, `not_found`, OCR/header conflicts, history rows and filename timestamp conflicts.

- [ ] **Step 2: Verify RED and implement conservative extraction**

  Extract values only from page/block evidence. Keep conflicting candidates and do not silently repair OCR codes.

- [ ] **Step 3: Write failing classification precedence tests**

  Cover form under `manual`, program under `capacitaciones`, matrix under policy route, low-confidence route-only result, explicit route/title conflict, independent type/topic confidence and all retained historic types.

- [ ] **Step 4: Implement signal scoring and precedence**

  Authority is title/control, then structure/content, filename, then route. Route alone cannot cross the approval threshold.

- [ ] **Step 5: Verify GREEN**

  ```powershell
  .venv\Scripts\python.exe -m pytest app/back/tests/ingestion/test_document_control.py app/back/tests/ingestion/test_classification.py -q
  ```

---

### Task 4: Digital Layout, Boilerplate, Tables and Forms

**Files:**
- Create: `app/back/src/ingestion/layout/models.py`
- Create: `app/back/src/ingestion/layout/pdfplumber_extractor.py`
- Create: `app/back/src/ingestion/layout/boilerplate.py`
- Create: `app/back/src/ingestion/structure/tables.py`
- Create: `app/back/src/ingestion/structure/forms.py`
- Modify: `app/back/src/ingestion/readers/pdf_digital_reader.py`
- Modify: `app/back/src/ingestion/normalization/text.py`
- Test: `app/back/tests/ingestion/test_layout_extraction.py`
- Test: `app/back/tests/ingestion/test_boilerplate.py`
- Test: `app/back/tests/ingestion/test_tables_forms.py`

**Interfaces:**
- Produces: `PdfLayoutExtractor.extract_pages(path) -> list[LayoutPage]`.
- Produces: `detect_boilerplate(pages) -> BoilerplateResult`.
- Produces: capability-aware `TableExtractor.evaluate(page)` and `FormExtractor.evaluate(page)`.

- [ ] **Step 1: Add dependencies behind interfaces**

  Add bounded dependencies for `pdfplumber`, `pypdfium2`, `Pillow`, `pytesseract`, `numpy` and `opencv-python-headless` to `pyproject.toml` and `requirements.txt`; install through `uv` into the Python 3.12 environment.

- [ ] **Step 2: Write failing geometry tests**

  Cover page dimensions, cropbox, rotation, text/image/line/rectangle blocks, PDF point bboxes and deterministic reading order.

- [ ] **Step 3: Implement pdfplumber layout extraction**

  Preserve raw text and geometry. Backend absence returns capability unavailable; it never emits `not_detected`.

- [ ] **Step 4: Write failing boilerplate tests**

  Repeated top/bottom blocks must leave raw untouched, appear in removed spans and be excluded only from normalized/indexable body.

- [ ] **Step 5: Implement consensus boilerplate**

  Require repeated normalized text and positional agreement across multiple pages; retain watermarks as auditable layout observations.

- [ ] **Step 6: Write failing table/form tests**

  Cover bboxes, cells, row/column spans, AUMENTAN/DISMINUYEN, three-column matrix associations, complaint-form groups, labels and blank response regions.

- [ ] **Step 7: Implement digital structure extractors**

  Use pdfplumber table geometry and vector rectangles/lines. A capable run with no result emits `not_detected`; an unavailable extractor emits `not_evaluated`.

- [ ] **Step 8: Verify GREEN**

  ```powershell
  .venv\Scripts\python.exe -m pytest app/back/tests/ingestion/test_layout_extraction.py app/back/tests/ingestion/test_boilerplate.py app/back/tests/ingestion/test_tables_forms.py app/back/tests/ingestion/test_readers.py app/back/tests/ingestion/test_normalization.py -q
  ```

---

### Task 5: Real OCR Metrics, Coverage Analysis and Hybrid Reconciliation

**Files:**
- Create: `app/back/src/ingestion/ocr/tesseract_engine.py`
- Create: `app/back/src/ingestion/ocr/rasterizer.py`
- Create: `app/back/src/ingestion/coverage/analyzer.py`
- Create: `app/back/src/ingestion/readers/hybrid_reader.py`
- Modify: `app/back/src/ingestion/ocr/ocrmypdf_engine.py`
- Modify: `app/back/src/ingestion/readers/pdf_scanned_reader.py`
- Modify: `app/back/src/ingestion/ocr/doctor.py`
- Test: `app/back/tests/ingestion/test_tesseract_engine.py`
- Test: `app/back/tests/ingestion/test_coverage.py`
- Test: `app/back/tests/ingestion/test_hybrid_reader.py`
- Modify: `app/back/tests/ingestion/test_ocrmypdf_engine.py`

**Interfaces:**
- Produces: `PageRasterizer.render(path, page_number, clip, dpi) -> RasterRegion`.
- Produces: `RegionOcrEngine.recognize(region) -> OcrRegionResult`.
- Produces: `CoverageAnalyzer.assess(page) -> CoverageAssessment`.
- Produces: `HybridReader.read(path) -> ReadResult`.

- [ ] **Step 1: Write failing fabricated-confidence regressions**

  Sidecar text must create `kind="unavailable"`, `value=null`; no handwriting/table detector means `not_evaluated`; deskew/rotation are not filled without evidence; trailing form-feed does not create a phantom page.

- [ ] **Step 2: Remove fabricated defaults**

  Keep OCRmyPDF optional for preprocessing. It may return derived text, never confidence or feature negatives unless provided by a capable backend.

- [ ] **Step 3: Write failing Tesseract TSV tests**

  Parse real word rows (`conf >= 0`), normalize confidence 0–100 to 0–1, retain word bboxes, compute sample size and low-confidence counts, and aggregate document confidence weighted by words.

- [ ] **Step 4: Implement Tesseract and PDFium adapters**

  Configure executable paths explicitly, UTF-8 replacement handling, page/region DPI transforms and cleanup. Missing binary/language is a capability error, not a fake result.

- [ ] **Step 5: Write failing page-coverage tests**

  High document word count cannot hide sparse pages; logos do not trigger OCR; image-heavy instruction regions do; pages 13–15 fixture signals become incomplete coverage.

- [ ] **Step 6: Implement coverage analyzer**

  Combine per-page words, block coverage, image regions, suspicious gaps and abnormal characters. Return candidate regions with reasons.

- [ ] **Step 7: Write failing hybrid reconciliation tests**

  Preserve digital and OCR blocks as evidence, deduplicate overlapping text, mark page/document `hybrid`, propagate material warnings and require review when OCR is unavailable for an uncovered substantive region.

- [ ] **Step 8: Implement hybrid reader and propagation**

  OCR only uncovered pages/regions. Never force whole-document OCR merely because one region is incomplete.

- [ ] **Step 9: Expand capability doctor**

  Report pdfplumber, PDFium, Tesseract executable/version/languages, OCRmyPDF, Ghostscript and OpenCV separately.

- [ ] **Step 10: Verify GREEN**

  ```powershell
  .venv\Scripts\python.exe -m pytest app/back/tests/ingestion/test_tesseract_engine.py app/back/tests/ingestion/test_coverage.py app/back/tests/ingestion/test_hybrid_reader.py app/back/tests/ingestion/test_ocrmypdf_engine.py app/back/tests/ingestion/test_ocr_doctor.py -q
  ```

---

### Task 6: Strict Structural and Golden Validation

**Files:**
- Replace: `app/back/src/ingestion/validation/normalized.py`
- Create: `app/back/src/ingestion/validation/front_matter.py`
- Create: `app/back/src/ingestion/validation/golden.py`
- Modify: `docs/ingestion/pdf_corpus_expected.json`
- Replace: `app/back/tests/ingestion/test_validation.py`
- Create: `app/back/tests/ingestion/test_golden_validation.py`

**Interfaces:**
- Produces: `validate_normalized_tree(normalized_root, raw_root, mode, golden_path)`.
- Produces: `validate_pdf_corpus(candidate_root, raw_root, golden)`.

- [ ] **Step 1: Write one failing test per strict invariant**

  Cover schema version, extras, required pages, required OCR/forms/tables, page ordering/contiguity, method compatibility, measured confidence provenance, table/form page ranges, observations, canonical paths, source existence/hash, bundle hashes, inventory/metadata bijection, front matter parity and processed-with-review-reasons.

- [ ] **Step 2: Implement normal and closure modes**

  Normal mode reads legacy with explicit warnings. Closure mode requires schema 2.0 for every PDF bundle and fails on any semantic invariant.

- [ ] **Step 3: Convert golden prose into typed assertions**

  Retain audit notes separately. Add exact metadata assertions, normalized content/regex operators by page range, table row/cell associations, form group/label/control assertions, observation/evidence requirements, required artifacts and expected review reasons.

- [ ] **Step 4: Write failing golden-validator tests**

  Cover missing/extra document, ID/path mismatch, total page mismatch, metadata mismatch, missing evidence/content, broken table/form association and localized error details.

- [ ] **Step 5: Implement golden loader and comparator**

  Normalize repository-relative golden locators to raw-root-relative artifact paths. Require exact nine-PDF bijection and 77 ordered pages.

- [ ] **Step 6: Verify GREEN**

  ```powershell
  .venv\Scripts\python.exe -m pytest app/back/tests/ingestion/test_validation.py app/back/tests/ingestion/test_golden_validation.py -q
  ```

---

### Task 7: Fingerprinted Candidate Pipeline and Promotion Gate

**Files:**
- Create: `app/back/src/ingestion/fingerprint.py`
- Create: `app/back/src/ingestion/promotion.py`
- Replace: `app/back/src/ingestion/pipeline.py`
- Modify: `scripts/ingestion/run_pipeline.py`
- Create: `app/back/tests/ingestion/test_incremental.py`
- Create: `app/back/tests/ingestion/test_promotion.py`
- Replace: `app/back/tests/ingestion/test_pipeline_integration.py`

**Interfaces:**
- Produces: `processing_fingerprint(config, capability_versions)` and `validation_fingerprint(validator_version, golden_hash)`.
- Produces: `run_pipeline(..., staging_root, promote=False, only_sources=None, force=False)`.
- Produces: `promote_candidate(candidate_root, live_root, manifest)` with rollback.

- [ ] **Step 1: Write failing fingerprint/incremental tests**

  Root movement does not change processing fingerprint; threshold/pipeline/schema/OCR configuration does; missing or altered required sidecars force extraction; golden-only changes force validation but may reuse verified extraction.

- [ ] **Step 2: Implement deterministic fingerprints and bundle reuse**

  Exclude absolute roots and secrets. Verify source hash, processing fingerprint, required artifact set and artifact hashes before reuse.

- [ ] **Step 3: Write failing candidate-pipeline tests**

  Assert 2.0-only output, portable paths, inventory updates, page/control propagation, exact multipoint names, warning propagation, stale sidecar removal and live tree unchanged after candidate failure.

- [ ] **Step 4: Implement candidate composition**

  Scan, extract, classify, build control data, write complete bundles and manifests, then validate. Do not write directly into the live normalized tree.

- [ ] **Step 5: Write failing promotion tests**

  Golden failure leaves live unchanged; valid candidate swaps on same volume; swap failure restores backup; removed sources/artifacts do not survive.

- [ ] **Step 6: Implement lock, promotion and rollback**

  Promotion is explicit and only accepts a candidate whose structural and golden reports passed.

- [ ] **Step 7: Verify GREEN and full unit suite**

  ```powershell
  .venv\Scripts\python.exe -m pytest app/back/tests/ingestion -q
  ```

---

### Task 8: Nine-PDF Staging Run, Audit and Controlled Promotion

**Files:**
- Create: `app/back/tests/ingestion/test_pdf_corpus_golden.py`
- Modify: `docs/ingestion/pdf_corpus_quality_audit.md`
- Modify: `memory/plan_trabajo.md`
- Regenerate after gate: `data/docs_normalized/**` bundles for the nine PDFs only

**Interfaces:**
- Consumes the approved pipeline and `docs/ingestion/pdf_corpus_expected.json`.
- Produces a staging validation report, golden report and promotion manifest.

- [ ] **Step 1: Run the expanded capability doctor**

  If Tesseract 64-bit with `spa`/`osd` is unavailable, record the exact missing capability. Continue digital/schema work, but do not claim the scanned or hybrid corpus complete.

- [ ] **Step 2: Install/configure allowed user-space dependencies**

  Use project-local Python packages. If the external Tesseract/OCRmyPDF prerequisites cannot be installed without corporate support, stop corpus promotion and provide the exact IT request.

- [ ] **Step 3: Write and run the real-corpus regression test**

  The initial run against current artifacts must fail for the audited reasons. The test is marked `corpus` and reads all nine raw PDFs.

- [ ] **Step 4: Generate a candidate tree for only the nine PDFs**

  Keep the current live normalized tree untouched. Preserve all 77 pages, artifacts and warnings.

- [ ] **Step 5: Run structural closure and golden validation**

  Require 9/9 document bijection, 77/77 pages, no invented measurements, expected classification/control fields and executable content/structure assertions.

- [ ] **Step 6: Inspect every candidate bundle**

  Review `.md`, `.metadata.json`, `.pages.json`, `.ocr.json`, `.tables.json` and `.forms.json` where applicable. Compare diffs and all `needs_review` reasons against the visual audit.

- [ ] **Step 7: Promote only after both gates pass**

  Promote the nine PDF bundles without changing the 46 Markdown bundles except schema-compatible manifests required by the candidate tree.

- [ ] **Step 8: Run final verification**

  ```powershell
  .venv\Scripts\python.exe -m pip check
  .venv\Scripts\python.exe -m pytest app/back/tests/ingestion -q
  .venv\Scripts\python.exe -m pytest app/back/tests/ingestion/test_pdf_corpus_golden.py -m corpus -q
  .venv\Scripts\python.exe scripts/ingestion/validate_normalized.py --mode closure
  ```

- [ ] **Step 9: Complete audit trail**

  Check every task in this plan and `memory/plan_trabajo.md`. Record commands, counts, exceptions, unresolved review reasons and whether promotion occurred. Do not declare Phase 1 closed unless every closure criterion passes or the user explicitly accepts documented exceptions.

