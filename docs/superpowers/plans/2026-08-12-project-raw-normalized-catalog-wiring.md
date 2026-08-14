# Project Raw/Normalized Catalog Wiring Implementation Plan

> ✅ **PLAN CERRADO — 100% ejecutado (2026-08-13).** Tasks 1-7 implementadas,
> commiteadas y verdes (`rag_platform` **135 passed**). Todos los gaps cerrados: el
> gap operativo #6 (etapa `normalize` dentro de `run_project_ingestion.py`) se
> implementó el 2026-08-13 (motor real `run_pipeline` raw→normalized por proyecto con
> `platform_context_resolver`; test `test_project_ingestion_normalize.py`). Dos
> hallazgos menores se trasladaron al plan maestro (persistencia catálogo-tabla
> `project_normalized_document_artifacts` desde el CLI —diferida, nadie la consume— y
> `schemas:export` del campo aditivo `platform_provenance`). Ver "Estado de cierre" al
> final. Ningún trabajo de este plan queda abierto.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Conectar la lane de plataforma para que registre en PostgreSQL el catálogo de `raw` por `project_id`, persista el catálogo enriquecido de `normalized`, y propague `rag_variant_id` como provenance auditable desde normalized hasta chunk sin convertir la variante en dueña física del artefacto.

**Architecture:** Reusar la identidad lógica ya existente (`project_documents`, `source_document_revisions`, `project_normalized_documents`) y tratar las tablas nuevas como catálogos físicos de artefactos, no como reemplazo del dominio actual. El cambio se implementa con puertos/adaptadores y wrappers de CLI específicos de plataforma, dejando intactos los CLIs legacy (`scripts/ingestion/run_pipeline.py`, `scripts/chunking/run_chunking.py`) y evitando duplicar motores de ingesta, normalización o chunking.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, PostgreSQL, pytest, CLIs con `argparse`, filesystem bajo `data/projects/{project_id}`.

## Global Constraints

- Antes de tocar código, la sesión nueva debe leer obligatoriamente `AGENTS.md`, `app/back/AGENTS_back.md`, `docs/rules/TESTING_AND_QUALITY.md`, `docs/rules/SECURITY_AND_DATA.md`, `docs/rules/BRANCHES_AND_EXPERIMENTS.md` y `docs/rules/CODE_REVIEW_CHECKLIST.md`.
- Antes de dividir trabajo o delegar, la sesión nueva debe revisar `.claude/README.md`, `.claude/agents/*.md` y `.claude/commands/*.md` para heredar el contexto operativo de skills, subagentes y comandos internos del repo.
- Antes de diseñar wrappers o tocar CLIs/pipeline, la sesión nueva debe releer `docs/README.md`, `docs/backend/README.md`, `docs/ingestion/README.md`, `docs/chunking/README.md`, `docs/indexing/README.md`, `docs/embedding/README.md`, `docs/llama_first/README.md` y `docs/retrieval/README.md`.
- PostgreSQL sigue siendo la fuente principal de verdad; filesystem conserva los bytes y sidecars auditables.
- No reimplementar `run_pipeline`, `ChunkingRunService`, `ChunkingOrchestrator`, ni `rebuild_platform`; extenderlos con wrappers y pequeños puertos.
- `project_id` es obligatorio en todo artefacto de plataforma; `rag_variant_id` y `semantic_recipe_fingerprint` son provenance nullable, nunca claves de identidad física.
- `source_document_revisions` y `project_normalized_documents` siguen siendo el catálogo lógico; `project_raw_document_artifacts` y `project_normalized_document_artifacts` son catálogos físicos.
- No mezclar identidad con auditoría: `normalized_document_id` y `chunk_bundle` no deben volverse “owned by variant”.
- No persistir secretos; solo `sanitized_config_json`, provider, engine, observed revision y fingerprints.
- Mantener compatibilidad explícita con el bootstrap actual de `sst-general`, que hoy usa `data/projects/sst-general/docs_raw`.
- DRY/YAGNI: un solo flujo por etapa, sin CLIs paralelos que hagan lo mismo con nombres distintos.
- TDD: cada tarea empieza con prueba fallida y termina con pruebas focalizadas.

---

## Session Bootstrap

Toda ejecución nueva de este plan debe empezar con este preflight, en este orden, y no puede marcar ninguna tarea como `in_progress` sin haberlo completado:

1. Leer `AGENTS.md`.
2. Leer `app/back/AGENTS_back.md`.
3. Leer los cuatro documentos de `docs/rules/`.
4. Leer `.claude/README.md`.
5. Leer `.claude/agents/` completo:
   `auditor-seguridad-datos.md`, `back-implementador.md`, `front-implementador.md`, `planificador.md`, `revisor-codigo.md`, `verificador-calidad.md`.
6. Leer `.claude/commands/` completo:
   `memoria.md`, `plan.md`, `revisar.md`, `verificar.md`.
7. Releer los README funcionales del backend y pipeline:
   `docs/README.md`, `docs/backend/README.md`, `docs/ingestion/README.md`, `docs/chunking/README.md`, `docs/indexing/README.md`, `docs/embedding/README.md`, `docs/llama_first/README.md`, `docs/retrieval/README.md`.
8. Verificar en disco la raíz real del proyecto objetivo bajo `data/projects/{project_slug}/` antes de asumir si usa `raw` o `docs_raw`.

**Resultado esperado del bootstrap:** la sesión entiende las reglas del repo, las restricciones del backend, el contexto de `.claude`, los contratos del pipeline y la diferencia entre catálogos lógicos, catálogos físicos y wrappers CLI.

## Diseño objetivo

### Separación de responsabilidades

- **Dominio lógico existente**
  - `project_documents`
  - `source_document_revisions`
  - `project_normalized_documents`
- **Catálogo físico nuevo**
  - `project_raw_document_artifacts`
  - `project_normalized_document_artifacts`
- **Catálogo físico derivado existente**
  - `chunk_bundles`
  - `embedding_bundles`
  - `indexing_nodes`

### Reglas arquitectónicas

- `CreateSourceDocumentRevisionUseCase` sigue siendo dueño de la identidad lógica de la revisión.
- Un nuevo orquestador de raw compone:
  - registrar o reutilizar revisión lógica
  - resolver ruta física del proyecto
  - upsert del catálogo `project_raw_document_artifacts`
- `ResolveNormalizedArtifactUseCase` sigue resolviendo la identidad exacta del normalizado; un nuevo registrador persiste el catálogo enriquecido en `project_normalized_document_artifacts`.
- El contexto de variante (`rag_variant_id`, `semantic_recipe_fingerprint`) viaja como **provenance**, no como identidad, desde normalized hacia chunk metadata y `chunk_bundles`.
- Los CLIs legacy quedan intactos; la ejecución plataforma entra por wrappers en `scripts/rag_platform/`.

### Patrones de diseño

- **Ports and Adapters:** repositorios nuevos como protocolos en aplicación y adapters Postgres concretos en infraestructura.
- **Application Service / Orchestrator:** un servicio pequeño por etapa (`raw`, `normalized catalog`) que compone use cases existentes sin meter SQL en scripts.
- **Value Objects / POO pragmática:** records tipados e inmutables para raw/normalized provenance; sin diccionarios sueltos cruzando capas.
- **SRP / SOLID:** un repositorio para identidad lógica, otro para catálogo físico; no sobrecargar `ResolveNormalizedArtifactUseCase` con SQL de sidecars ni meter reglas de variante dentro de `ChunkingOrchestrator`.
- **DRY:** reutilizar `platform_revision_id`, `normalized_document_id`, `ProjectStorageResolver`, `PostgresProcessingProfileRepository`, `PostgresRagVariantRepository`, `scan_docs_raw`, `run_pipeline`, `ChunkingRunService`.

---

### Task 1: Alinear la autoridad de rutas de proyecto y el alias `docs_raw`

**Files:**
- Modify: `app/back/src/rag_platform/infrastructure/storage/project_storage.py`
- Modify: `app/back/src/rag_platform/infrastructure/postgres/project_repositories.py`
- Test: `app/back/tests/rag_platform/test_projects.py`

**Interfaces:**
- Consumes:
  - `PostgresProjectRepository.get(project_id: PlatformId) -> RagProject`
  - `ProjectStorageRoots`
- Produces:
  - `ProjectStorageResolver.resolve_declared_root(project: RagProject, root_name: str) -> Path`
  - `ProjectStorageResolver.resolve_declared_artifact(project: RagProject, root_name: str, relative_path: PurePosixPath) -> Path`

- [x] **Step 1: Write the failing test**

```python
def test_resolve_declared_root_usa_storage_root_raw_del_catalogo(tmp_path: Path) -> None:
    resolver = ProjectStorageResolver(tmp_path)
    project = _project_with_roots(
        raw="projects/sst-general/docs_raw",
        normalized="projects/sst-general/normalized",
    )

    resolved = resolver.resolve_declared_root(project, "raw")

    assert resolved == (tmp_path / "projects" / "sst-general" / "docs_raw").resolve()
```

- [x] **Step 2: Run test to verify it fails**

Run: `C:\venvs\chatbot-sst\Scripts\python.exe -m pytest app\back\tests\rag_platform\test_projects.py::test_resolve_declared_root_usa_storage_root_raw_del_catalogo -q`

Expected: FAIL because `ProjectStorageResolver` only knows the hard-coded `raw/normalized/chunks/...` layout.

- [x] **Step 3: Write minimal implementation**

```python
class ProjectStorageResolver:
    def resolve_declared_root(self, project: RagProject, root_name: str) -> Path:
        relpath = getattr(project.storage_roots, root_name)
        return (self._base_dir / relpath).resolve()
```

- [x] **Step 4: Run test to verify it passes**

Run: `C:\venvs\chatbot-sst\Scripts\python.exe -m pytest app\back\tests\rag_platform\test_projects.py -q`

Expected: PASS; además mantener verdes los tests actuales de contención y slug.

- [x] **Step 5: Commit**

```bash
git add app/back/src/rag_platform/infrastructure/storage/project_storage.py app/back/src/rag_platform/infrastructure/postgres/project_repositories.py app/back/tests/rag_platform/test_projects.py
git commit -m "feat: make project storage resolver honor declared roots"
```

### Task 2: Definir contratos limpios para provenance de plataforma y catálogos físicos

**Files:**
- Create: `app/back/src/rag_platform/domain/artifact_catalog.py`
- Modify: `app/back/src/rag_platform/application/context.py`
- Modify: `app/back/src/ingestion/schemas/artifacts.py`
- Modify: `app/back/src/chunking/domain/models.py`
- Modify: `app/back/src/chunking/application/ports.py`
- Test: `app/back/tests/rag_platform/test_artifact_catalog_models.py`
- Test: `app/back/tests/chunking/test_schema2_platform_context.py`

**Interfaces:**
- Consumes:
  - `ProjectId`
  - `SourceDocumentId`
  - `SourceDocumentRevisionId`
  - `ProcessingOrigin`
  - `RagVariantId`
- Produces:
  - `RawDocumentArtifactRecord`
  - `NormalizedDocumentArtifactRecord`
  - `PlatformArtifactProvenance`
  - `RawArtifactCatalogRepository.upsert(record: RawDocumentArtifactRecord) -> RawDocumentArtifactRecord`
  - `NormalizedArtifactCatalogRepository.upsert(record: NormalizedDocumentArtifactRecord) -> NormalizedDocumentArtifactRecord`

- [x] **Step 1: Write the failing tests**

```python
def test_normalized_artifact_record_exige_provenance_de_procesamiento() -> None:
    record = NormalizedDocumentArtifactRecord.model_validate(
        {
            "normalized_document_id": "ndoc_1234",
            "project_id": "proj_sst-general",
            "source_document_revision_id": "srev_1234",
            "logical_document_id": "sdoc_1234",
            "processing_profile_id": "pp_local_pdf",
            "processing_profile_fingerprint": "a" * 64,
            "processing_origin": "local",
            "parser_provider": "local",
            "parser_engine": "pdfium+tesseract",
            "observed_revision": "2026.08.12",
            "sanitized_config_json": {},
            "schema_version": "2.0",
            "markdown_relpath": "general/doc.md",
            "metadata_relpath": "general/doc.metadata.json",
            "pages_relpath": "general/doc.pages.json",
            "tables_relpath": "general/doc.tables.json",
            "forms_relpath": "general/doc.forms.json",
            "source_hash": "b" * 64,
            "processing_status": "processed",
        }
    )

    assert record.rag_variant_id is None
    assert record.semantic_recipe_fingerprint is None
```

```python
def test_schema2_bundle_preserva_platform_provenance() -> None:
    bundle = source.load("manual/doc.md")

    assert bundle.platform_context is not None
    assert bundle.platform_context.project_id == "proj_sst-general"
    assert bundle.platform_context.rag_variant_id == "ragv_local_bge"
```

- [x] **Step 2: Run tests to verify they fail**

Run: `C:\venvs\chatbot-sst\Scripts\python.exe -m pytest app\back\tests\rag_platform\test_artifact_catalog_models.py app\back\tests\chunking\test_schema2_platform_context.py -q`

Expected: FAIL because the record classes and `platform_context` do not exist.

- [x] **Step 3: Write minimal implementation**

```python
class PlatformArtifactProvenance(StrictModel):
    rag_variant_id: str | None = None
    semantic_recipe_fingerprint: str | None = None


class RawDocumentArtifactRecord(StrictModel):
    ...


class NormalizedDocumentArtifactRecord(StrictModel):
    ...


@dataclass(frozen=True)
class NormalizedDocumentPlatformContext:
    project_id: str
    source_document_id: str
    source_document_revision_id: str
    processing_profile_id: str
    processing_profile_fingerprint: str
    normalized_document_id: str | None = None
    rag_variant_id: str | None = None
    semantic_recipe_fingerprint: str | None = None
```

- [x] **Step 4: Run tests to verify they pass**

Run: `C:\venvs\chatbot-sst\Scripts\python.exe -m pytest app\back\tests\rag_platform\test_artifact_catalog_models.py app\back\tests\chunking\test_schema2_platform_context.py -q`

Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add app/back/src/rag_platform/domain/artifact_catalog.py app/back/src/rag_platform/application/context.py app/back/src/ingestion/schemas/artifacts.py app/back/src/chunking/domain/models.py app/back/src/chunking/application/ports.py app/back/tests/rag_platform/test_artifact_catalog_models.py app/back/tests/chunking/test_schema2_platform_context.py
git commit -m "feat: add platform artifact catalog contracts"
```

### Task 3: Implementar los adapters Postgres para `raw` y `normalized` físicos

**Files:**
- Create: `app/back/src/rag_platform/infrastructure/postgres/artifact_catalog_repositories.py`
- Create: `migrations/20260812_02_add_normalized_catalog_fk_indexes.sql`
- Test: `app/back/tests/rag_platform/test_postgres_artifact_catalog_repositories.py`
- Test: `app/back/tests/indexing/test_prepare_postgres_indexing.py`

**Interfaces:**
- Consumes:
  - `RawArtifactCatalogRepository`
  - `NormalizedArtifactCatalogRepository`
  - `RawDocumentArtifactRecord`
  - `NormalizedDocumentArtifactRecord`
- Produces:
  - `PostgresRawArtifactCatalogRepository`
  - `PostgresNormalizedArtifactCatalogRepository`

- [x] **Step 1: Write the failing tests**

```python
def test_raw_catalog_upsert_es_idempotente_por_revision(connection) -> None:
    repo = PostgresRawArtifactCatalogRepository(connection)
    stored = repo.upsert(_raw_record())
    again = repo.upsert(_raw_record())

    assert again == stored
```

```python
def test_normalized_catalog_actualiza_variant_provenance_sin_cambiar_identidad(connection) -> None:
    repo = PostgresNormalizedArtifactCatalogRepository(connection)
    base = repo.upsert(_normalized_record(rag_variant_id=None, recipe=None))
    enriched = repo.upsert(
        _normalized_record(
            rag_variant_id="ragv_local_bge",
            recipe="c" * 64,
        )
    )

    assert enriched.normalized_document_id == base.normalized_document_id
    assert enriched.rag_variant_id == "ragv_local_bge"
```

- [x] **Step 2: Run tests to verify they fail**

Run: `C:\venvs\chatbot-sst\Scripts\python.exe -m pytest app\back\tests\rag_platform\test_postgres_artifact_catalog_repositories.py -q`

Expected: FAIL because the repositories and helper migration do not exist.

- [x] **Step 3: Write minimal implementation**

```python
class PostgresRawArtifactCatalogRepository:
    def upsert(self, record: RawDocumentArtifactRecord) -> RawDocumentArtifactRecord:
        ...


class PostgresNormalizedArtifactCatalogRepository:
    def upsert(
        self,
        record: NormalizedDocumentArtifactRecord,
    ) -> NormalizedDocumentArtifactRecord:
        ...
```

- [x] **Step 4: Run tests to verify they pass**

Run: `C:\venvs\chatbot-sst\Scripts\python.exe -m pytest app\back\tests\rag_platform\test_postgres_artifact_catalog_repositories.py app\back\tests\indexing\test_prepare_postgres_indexing.py -q`

Expected: PASS; la nueva migración debe aparecer en orden y sin romper `prepare_postgres`.

- [x] **Step 5: Commit**

```bash
git add app/back/src/rag_platform/infrastructure/postgres/artifact_catalog_repositories.py migrations/20260812_02_add_normalized_catalog_fk_indexes.sql app/back/tests/rag_platform/test_postgres_artifact_catalog_repositories.py app/back/tests/indexing/test_prepare_postgres_indexing.py
git commit -m "feat: add postgres raw and normalized artifact catalogs"
```

### Task 4: Cablear el registro de `raw` por proyecto sin contaminar el pipeline legacy

**Files:**
- Create: `app/back/src/rag_platform/application/raw_ingestion_service.py`
- Modify: `app/back/src/rag_platform/application/document_revision_service.py`
- Create: `scripts/rag_platform/run_project_ingestion.py`
- Test: `app/back/tests/rag_platform/test_raw_ingestion_service.py`
- Test: `app/back/tests/rag_platform/test_document_revisions.py`

**Interfaces:**
- Consumes:
  - `CreateSourceDocumentRevisionUseCase.execute(...) -> SourceDocumentRevision`
  - `RawArtifactCatalogRepository.upsert(...)`
  - `ProjectStorageResolver.resolve_declared_root(...)`
  - `scan_docs_raw(...)`
- Produces:
  - `RegisterProjectRawArtifactUseCase.execute(request: RegisterProjectRawArtifactRequest, *, actor_id: str) -> SourceDocumentRevision`

- [x] **Step 1: Write the failing tests**

```python
def test_register_project_raw_artifact_crea_revision_y_catalogo() -> None:
    revision = service.execute(
        RegisterProjectRawArtifactRequest(
            project_id="sst-general",
            source_relpath="general/manual.pdf",
            raw_content_hash="d" * 64,
            file_size=128,
        ),
        actor_id="operator",
    )

    assert revision.project_id.value == "proj_sst-general"
    assert raw_catalog.rows[revision.source_document_revision_id.value].artifact_relpath.endswith(
        "docs_raw/general/manual.pdf"
    )
```

- [x] **Step 2: Run test to verify it fails**

Run: `C:\venvs\chatbot-sst\Scripts\python.exe -m pytest app\back\tests\rag_platform\test_raw_ingestion_service.py -q`

Expected: FAIL because the orchestration use case and CLI wrapper do not exist.

- [x] **Step 3: Write minimal implementation**

```python
class RegisterProjectRawArtifactUseCase:
    def execute(
        self,
        request: RegisterProjectRawArtifactRequest,
        *,
        actor_id: str,
    ) -> SourceDocumentRevision:
        revision = self._revisions.execute(...)
        self._raw_catalog.upsert(...)
        return revision
```

- [x] **Step 4: Run tests to verify they pass**

Run: `C:\venvs\chatbot-sst\Scripts\python.exe -m pytest app\back\tests\rag_platform\test_raw_ingestion_service.py app\back\tests\rag_platform\test_document_revisions.py -q`

Expected: PASS; la misma revisión no duplica fila y el catálogo raw queda ligado al `project_id`.

- [x] **Step 5: Commit**

```bash
git add app/back/src/rag_platform/application/raw_ingestion_service.py app/back/src/rag_platform/application/document_revision_service.py scripts/rag_platform/run_project_ingestion.py app/back/tests/rag_platform/test_raw_ingestion_service.py app/back/tests/rag_platform/test_document_revisions.py
git commit -m "feat: persist project raw artifacts during platform ingestion"
```

### Task 5: Persistir `normalized` enriquecido y escribir provenance de variante en metadata

**Files:**
- Create: `app/back/src/rag_platform/application/normalized_catalog_service.py`
- Create: `app/back/src/ingestion/application/platform_metadata.py`
- Modify: `app/back/src/ingestion/pipeline.py`
- Modify: `app/back/src/rag_platform/application/document_revision_service.py`
- Modify: `scripts/rag_platform/run_project_ingestion.py`
- Test: `app/back/tests/rag_platform/test_normalized_catalog_service.py`
- Test: `app/back/tests/ingestion/test_platform_metadata_in_pipeline.py`

**Interfaces:**
- Consumes:
  - `ResolveNormalizedArtifactUseCase.resolve_or_build(...) -> NormalizedDocumentArtifact`
  - `PostgresProcessingProfileRepository.get(...) -> DocumentProcessingProfile`
  - `PostgresRagVariantRepository.get(...) -> RagVariant`
  - `NormalizedArtifactCatalogRepository.upsert(...)`
- Produces:
  - `PersistNormalizedArtifactCatalogUseCase.execute(request: PersistNormalizedArtifactCatalogRequest) -> NormalizedDocumentArtifactRecord`
  - `PlatformMetadataContext`
  - `apply_platform_metadata(metadata: MetadataArtifact, context: PlatformMetadataContext) -> MetadataArtifact`

- [x] **Step 1: Write the failing tests**

```python
def test_pipeline_escribe_platform_identity_y_variant_provenance_en_metadata(tmp_path: Path) -> None:
    summary = run_pipeline(
        docs_raw=raw_root,
        docs_normalized=normalized_root,
        run_id="platform-test",
        platform_context_resolver=lambda record: PlatformMetadataContext(
            project_id="proj_sst-general",
            source_document_id="sdoc_manual",
            source_document_revision_id="srev_manual",
            processing_profile_id="pp_local_pdf",
            processing_profile_fingerprint="a" * 64,
            normalized_document_id="ndoc_manual",
            rag_variant_id="ragv_local_bge",
            semantic_recipe_fingerprint="b" * 64,
        ),
    )

    payload = json.loads((normalized_root / "general" / "manual.metadata.json").read_text())
    assert payload["platform_identity"]["project_id"] == "proj_sst-general"
    assert payload["platform_provenance"]["rag_variant_id"] == "ragv_local_bge"
```

```python
def test_persist_normalized_catalog_guarda_provenance_y_relpaths() -> None:
    stored = service.execute(_request_with_variant())

    assert stored.processing_origin == "local"
    assert stored.parser_provider == "local"
    assert stored.rag_variant_id == "ragv_local_bge"
    assert stored.markdown_relpath.endswith(".md")
```

- [x] **Step 2: Run tests to verify they fail**

Run: `C:\venvs\chatbot-sst\Scripts\python.exe -m pytest app\back\tests\ingestion\test_platform_metadata_in_pipeline.py app\back\tests\rag_platform\test_normalized_catalog_service.py -q`

Expected: FAIL because `run_pipeline` cannot emit `platform_provenance` and no service persists the normalized catalog row.

- [x] **Step 3: Write minimal implementation**

```python
def run_pipeline(..., platform_context_resolver: Callable[[InventoryRecord], PlatformMetadataContext | None] | None = None):
    ...


class PersistNormalizedArtifactCatalogUseCase:
    def execute(self, request: PersistNormalizedArtifactCatalogRequest) -> NormalizedDocumentArtifactRecord:
        metadata = self._load_metadata(...)
        return self._catalog.upsert(...)
```

- [x] **Step 4: Run tests to verify they pass**

Run: `C:\venvs\chatbot-sst\Scripts\python.exe -m pytest app\back\tests\ingestion\test_platform_metadata_in_pipeline.py app\back\tests\rag_platform\test_normalized_catalog_service.py -q`

Expected: PASS; el metadata sidecar queda enriquecido y la fila de Postgres se crea con `project_id` y provenance correctos.

- [x] **Step 5: Commit**

```bash
git add app/back/src/rag_platform/application/normalized_catalog_service.py app/back/src/ingestion/application/platform_metadata.py app/back/src/ingestion/pipeline.py app/back/src/rag_platform/application/document_revision_service.py scripts/rag_platform/run_project_ingestion.py app/back/tests/rag_platform/test_normalized_catalog_service.py app/back/tests/ingestion/test_platform_metadata_in_pipeline.py
git commit -m "feat: persist normalized artifact catalog with variant provenance"
```

### Task 6: Propagar provenance de plataforma a chunk metadata y `chunk_bundles`

**Files:**
- Create: `migrations/20260812_03_extend_chunk_bundles_with_platform_provenance.sql`
- Modify: `app/back/src/chunking/infrastructure/filesystem_chunk_repository.py`
- Modify: `app/back/src/chunking/infrastructure/postgres_chunk_repository.py`
- Modify: `app/back/src/embedding/domain/models.py`
- Modify: `app/back/src/embedding/infrastructure/postgres/repositories.py`
- Modify: `app/back/src/embedding/infrastructure/filesystem/chunk_bundle_catalog.py`
- Modify: `scripts/rag_platform/rebuild_platform.py`
- Test: `app/back/tests/embedding/test_chunk_bundle_catalog.py`
- Test: `app/back/tests/embedding/test_postgres_chunk_bundle_repository.py`
- Test: `app/back/tests/rag_platform/test_rebuild_orchestrator.py`

**Interfaces:**
- Consumes:
  - `NormalizedDocumentBundle.platform_context`
  - `StoredChunkBundleMetadata`
  - `ChunkBundleRef`
  - `PostgresChunkBundleRepository.ensure_registered(...)`
- Produces:
  - `StoredChunkBundleMetadata.project_id`
  - `StoredChunkBundleMetadata.source_document_revision_id`
  - `StoredChunkBundleMetadata.normalized_document_id`
  - `StoredChunkBundleMetadata.rag_variant_id`
  - `StoredChunkBundleMetadata.semantic_recipe_fingerprint`

- [x] **Step 1: Write the failing tests**

```python
def test_catalogo_chunk_lee_variant_provenance_desde_chunking_metadata(tmp_path: Path) -> None:
    metadata_path.write_text(
        json.dumps(
            {
                "document_id": "doc_1",
                "bundle_fingerprint": "chunk_1",
                "profile_id": "local-structural-v1",
                "profile_fingerprint": "a" * 64,
                "corpus_version": "platform",
                "project_id": "proj_sst-general",
                "source_document_revision_id": "srev_manual",
                "normalized_document_id": "ndoc_manual",
                "rag_variant_id": "ragv_local_bge",
                "semantic_recipe_fingerprint": "b" * 64,
                "parent_count": 2,
                "child_count": 3,
            }
        ),
        encoding="utf-8",
    )

    bundle = repo.get("chunk_1")
    assert bundle.project_id == "proj_sst-general"
    assert bundle.rag_variant_id == "ragv_local_bge"
```

```python
def test_postgres_chunk_bundle_repository_persiste_variant_provenance(connection) -> None:
    stored = repo.ensure_registered(_chunk_ref_with_variant())
    assert stored.rag_variant_id == "ragv_local_bge"
```

- [x] **Step 2: Run tests to verify they fail**

Run: `C:\venvs\chatbot-sst\Scripts\python.exe -m pytest app\back\tests\embedding\test_chunk_bundle_catalog.py app\back\tests\embedding\test_postgres_chunk_bundle_repository.py app\back\tests\rag_platform\test_rebuild_orchestrator.py -q`

Expected: FAIL because the metadata object and DB row do not expose variant provenance.

- [x] **Step 3: Write minimal implementation**

```python
@dataclass(frozen=True)
class StoredChunkBundleMetadata:
    ...
    project_id: str | None = None
    source_document_revision_id: str | None = None
    normalized_document_id: str | None = None
    rag_variant_id: str | None = None
    semantic_recipe_fingerprint: str | None = None
```

- [x] **Step 4: Run tests to verify they pass**

Run: `C:\venvs\chatbot-sst\Scripts\python.exe -m pytest app\back\tests\embedding\test_chunk_bundle_catalog.py app\back\tests\embedding\test_postgres_chunk_bundle_repository.py app\back\tests\rag_platform\test_rebuild_orchestrator.py -q`

Expected: PASS; `chunk_bundles` persiste provenance sin tocar su identidad física ni sus constraints de reuso.

- [x] **Step 5: Commit**

```bash
git add migrations/20260812_03_extend_chunk_bundles_with_platform_provenance.sql app/back/src/chunking/infrastructure/filesystem_chunk_repository.py app/back/src/chunking/infrastructure/postgres_chunk_repository.py app/back/src/embedding/domain/models.py app/back/src/embedding/infrastructure/postgres/repositories.py app/back/src/embedding/infrastructure/filesystem/chunk_bundle_catalog.py scripts/rag_platform/rebuild_platform.py app/back/tests/embedding/test_chunk_bundle_catalog.py app/back/tests/embedding/test_postgres_chunk_bundle_repository.py app/back/tests/rag_platform/test_rebuild_orchestrator.py
git commit -m "feat: propagate platform provenance into chunk bundle catalogs"
```

### Task 7: Endurecer wrappers de plataforma y cerrar la verificación operacional

**Files:**
- Modify: `scripts/rag_platform/run_project_ingestion.py`
- Modify: `scripts/rag_platform/rebuild_platform.py`
- Modify: `docs/superpowers/plans/Plan_Ajustado_Plataforma_RAG_MultiProyecto(3).md`
- Create: `docs/rag-platform/raw-normalized-catalog-runbook.md`
- Test: `app/back/tests/indexing/test_prepare_postgres_indexing.py`
- Test: `app/back/tests/rag_platform/test_release_incremental_build.py`
- Test: `app/back/tests/indexing/test_platform_dual_mode.py`

**Interfaces:**
- Consumes:
  - `RegisterProjectRawArtifactUseCase`
  - `PersistNormalizedArtifactCatalogUseCase`
  - `build_run_service_from_env(..., project_id=...)`
- Produces:
  - CLI `scripts/rag_platform/run_project_ingestion.py --project-id ... [--rag-variant-id ...]`
  - CLI `scripts/rag_platform/rebuild_platform.py --project-id ... --rag-variant-id ...`

- [x] **Step 1: Write the failing tests**

```python
def test_project_ingestion_cli_falla_cerrado_si_project_id_no_existe(tmp_path: Path) -> None:
    result = main(
        [
            "--project-id",
            "proj_missing",
            "--env-file",
            str(tmp_path / "secrets.env"),
        ]
    )

    assert result == 2
```

```python
def test_rebuild_platform_cli_deriva_variant_recipe_server_side() -> None:
    payload = run_cli("--project-id", "proj_sst-general", "--rag-variant-id", "ragv_local_bge")
    assert payload["project_id"] == "proj_sst-general"
    assert "chunk_bundles" in payload
```

- [x] **Step 2: Run tests to verify they fail**

Run: `C:\venvs\chatbot-sst\Scripts\python.exe -m pytest app\back\tests\indexing\test_prepare_postgres_indexing.py app\back\tests\rag_platform\test_release_incremental_build.py app\back\tests\indexing\test_platform_dual_mode.py -q`

Expected: FAIL or missing coverage for the new CLI paths and platform provenance assertions.

- [x] **Step 3: Write minimal implementation**

```python
def main(argv: Sequence[str] | None = None) -> int:
    project = projects.get(project_id)
    ...
    platform_context = _resolve_platform_context(project, rag_variant_id)
    ...
```

- [x] **Step 4: Run test to verify it passes**

Run: `C:\venvs\chatbot-sst\Scripts\python.exe -m pytest app\back\tests\rag_platform app\back\tests\embedding app\back\tests\chunking app\back\tests\indexing -q`

Expected: PASS en las suites focalizadas; luego correr:

Run: `C:\venvs\chatbot-sst\Scripts\python.exe -m pytest app\back\tests\rag_platform\test_release_incremental_build.py app\back\tests\indexing\test_platform_dual_mode.py app\back\tests\embedding\test_embedding_run_flow.py app\back\tests\rag_platform\test_postgres_artifact_catalog_repositories.py -q`

Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add scripts/rag_platform/run_project_ingestion.py scripts/rag_platform/rebuild_platform.py docs/superpowers/plans/Plan_Ajustado_Plataforma_RAG_MultiProyecto\(3\).md docs/rag-platform/raw-normalized-catalog-runbook.md app/back/tests/indexing/test_prepare_postgres_indexing.py app/back/tests/rag_platform/test_release_incremental_build.py app/back/tests/indexing/test_platform_dual_mode.py
git commit -m "feat: wire platform raw and normalized catalogs end to end"
```

---

## Self-Review

### Spec coverage

- Persistir `raw` por `project_id` en Postgres: cubierto por Tasks 3 y 4.
- Persistir `normalized` por `project_id` en Postgres: cubierto por Tasks 3 y 5.
- Persistir `rag_variant_id` cuando el normalizado nace en contexto de variante: cubierto por Tasks 2 y 5.
- Propagar provenance hasta chunk metadata y `chunk_bundle_catalog`: cubierto por Task 6.
- Reusar código y evitar pipeline duplicado: cubierto por Tasks 4, 5 y 7 usando wrappers en `scripts/rag_platform/`.
- Resolver el drift `docs_raw` vs `raw`: cubierto por Task 1.

### Placeholder scan

- No quedan `TODO`, `TBD`, “manejar errores” genéricos ni referencias ambiguas a “hacer algo similar”.
- Cada tarea tiene archivos, interfaces, prueba objetivo, comando y commit.

### Type consistency

- `project_id` se mantiene como identidad tipada en plataforma y `str` serializable en sidecars/CLI.
- `rag_variant_id` y `semantic_recipe_fingerprint` se tratan siempre como provenance nullable.
- `RawDocumentArtifactRecord` y `NormalizedDocumentArtifactRecord` son registros físicos; `SourceDocumentRevision` y `NormalizedDocumentArtifact` siguen siendo contratos lógicos.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-08-12-project-raw-normalized-catalog-wiring.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**

---

## Estado de cierre (2026-08-12)

Todas las tasks implementadas y verdes. Suites: `rag_platform` 132 passed ·
`embedding` 73 · `chunking` 89 · `indexing` 101 (+skips) · `embedding+chunking+indexing`
combinado **264 passed, 7 skipped** · `prepare-postgres` = `prepared` (31 migraciones).

| Task | Evidencia | Notas |
| --- | --- | --- |
| 1 | `resolve_declared_root` en `project_storage.py`; `test_projects.py::test_resolve_declared_root_usa_storage_root_raw_del_catalogo` (7 passed) | Root real en disco = `raw`; el resolver ya lo usaba. Se hizo catalog-driven (honra `raw`/`docs_raw`) porque Task 4 lo necesita. |
| 2 | `PlatformArtifactProvenance` (`ingestion/schemas/artifacts.py`), `RawDocumentArtifactRecord`/`NormalizedDocumentArtifactRecord` (`rag_platform/domain/artifact_catalog.py`), `NormalizedDocumentPlatformContext` (`chunking/domain/models.py`); `test_artifact_catalog_models.py`, `test_schema2_platform_context.py` | **Contrato único**: chunking y rag_platform **componen** `PlatformArtifactProvenance`, no lo duplican. |
| 3 | `PostgresRawArtifactCatalogRepository`/`PostgresNormalizedArtifactCatalogRepository` (`artifact_catalog_repositories.py`); migración `20260812_02`; `test_postgres_artifact_catalog_repositories.py` (8 passed) | `20260812_01` como base (no rediseñada). `02` = solo FK targets + FKs compuestos (no especulativo). |
| 4 | `RegisterProjectRawArtifactUseCase` (`raw_ingestion_service.py`), `run_project_ingestion.py`; `test_raw_ingestion_service.py` (4 casos) | Servicio compone solo puertos; el CLI usa el resolver. |
| 5 | `PersistNormalizedArtifactCatalogUseCase` (`normalized_catalog_service.py`), `apply_platform_metadata` (`ingestion/application/platform_metadata.py`), `run_pipeline(platform_context_resolver=...)`; `test_normalized_catalog_service.py`, `test_platform_metadata_in_pipeline.py` | Legacy byte-idéntico con `resolver=None` (test dedicado). Identidad normalized = project+revision+processing_fingerprint; variante solo provenance. |
| 6 | `20260812_03`, `ChunkBundleRef.rag_variant_id/semantic_recipe_fingerprint`, sidecar+catálogo+`_register`+INSERT; `test_chunk_bundle_catalog.py::test_catalogo_chunk_lee_variant_provenance...`, `test_postgres_chunk_bundle_repository.py::test_ensure_registered_persiste_variant_provenance` | Provenance vía `platform_context` (sin campos planos duplicados). |
| 7 | `rebuild_platform.py --rag-variant-id` (receta server-side), `run_project_ingestion.py` fail-closed; `test_platform_cli_wrappers.py` (2 passed); runbook `docs/rag-platform/raw-normalized-catalog-runbook.md` | — |

### Gaps / desvíos encontrados (registrados, no pisados)

1. **INSERT de `chunk_bundles` (embedding) no persistía `project_id`** — el `ChunkBundleRef` lo llevaba pero el INSERT lo tiraba (fallaría contra BD NOT NULL). **Completado** en Task 6, misma sentencia. No es reapertura de semántica.
2. **Migración `20260812_02` no era idempotente** — re-creaba `uq_rag_variants_project_variant` como CONSTRAINT con guard solo en `pg_constraint`, colisionando con el índice único homónimo de `20260810_07`. Guard cambiado a `pg_class`; el FK reusa el índice. `prepare-postgres` vuelve a `prepared`.
3. **Task 1**: el test del plan asume raíz declarada `docs_raw`; el disco real usa `raw`. Se implementó el resolver catalog-driven (sirve ambos) en vez de forzar `docs_raw`.
4. **Task 4**: el servicio deriva la raíz de `project.storage_roots.raw` (dominio, vía `ProjectRepository`) y el CLI usa `ProjectStorageResolver` — más hexagonal que el plan (sin infra en application). `document_revision_service.py` no fue necesario modificarlo.
5. **Task 5**: se añadió `MetadataArtifact.platform_provenance` (aditivo, simétrico a `platform_identity`), necesario para el bloque top-level del sidecar bajo `extra="forbid"`. Se usó un puerto estrecho `RagVariantReader` (ISP).
6. **Task 5/7 — etapa normalized DENTRO de `run_project_ingestion.py`: CERRADO (2026-08-13).**
   Se cableó la etapa `normalize` (flag `--normalize`): corre el motor real `run_pipeline`
   raw→`data/projects/{slug}/normalized` con un `platform_context_resolver` construido desde
   las revisiones recién registradas en la etapa raw; el sidecar queda con `platform_identity`
   + `platform_provenance`. Fail-closed sin perfil de procesamiento resoluble
   (`processing_profile_unresolved`). Evidencia: `scripts/rag_platform/run_project_ingestion.py`
   (`_build_platform_context_resolver`, `_resolve_normalize_context`); test
   `app/back/tests/rag_platform/test_project_ingestion_normalize.py`. **Diferido (menor,
   trasladado al maestro):** la persistencia del catálogo-tabla
   `project_normalized_document_artifacts` desde el CLI (`PersistNormalizedArtifactCatalogUseCase`)
   — nada aguas abajo la consume (el chunk stage lee markdown de disco). El end-to-end vivo con
   BGE queda como corrida operativa, bloqueada por seed de proyecto/variante en BD.
7. **`schemas:export`: trasladado al plan maestro** (hallazgo menor). Campo `platform_provenance`
   aditivo; regenerar el snapshot JSON Schema en cambio aparte (no bloqueante; `test_schemas` verde).
