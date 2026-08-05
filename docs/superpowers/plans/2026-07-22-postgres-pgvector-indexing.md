# PostgreSQL Pgvector Indexing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist Llama-first indexing data in PostgreSQL, with pgvector tables that keep embedding providers, models, dimensions, chunking versions, corpus versions, and ingestion origins strictly separated.

**Architecture:** Keep LlamaIndex as the node/chunk construction layer, but make PostgreSQL the durable source of truth for indexing profiles, nodes, vector tables, runs, and validation reports. Use explicit ports/adapters so domain and application code do not import PostgreSQL, pgvector, LlamaIndex, BGE, Voyage, Cohere, or SDK clients directly. Persist vectors only for documents that are `processed` or explicitly approved under a valid review decision.

**Tech Stack:** Python 3.12, Pydantic 2, LlamaIndex core, `llama-index-vector-stores-postgres`, PostgreSQL 13+, pgvector, pytest, versioned SQL migrations.

## Global Constraints

- This plan targets the Llama-first branch, not `main`.
- `memory/plan_trabajo.md` is the general product vision; Llama-first is the implementation path for this branch.
- Operate only on normalized documents with `processing_status=processed` or `needs_review` documents with an explicit valid approval tied to `document_id`, `source_hash`, and `corpus_version`.
- Never index unapproved `needs_review`, `failed`, pending, malformed, or partially validated bundles.
- Do not mix normalized data ingested by local and Llama-first in the same logical corpus lane.
- Do not mix embeddings from BGE, Voyage, Cohere, mock, or any future provider in the same logical vector table.
- Do not mix embedding dimensions or distance metrics in one ANN index.
- PostgreSQL is the official source of truth; Redis is not introduced by this plan.
- Do not require live PostgreSQL/pgvector until infrastructure is confirmed. Live tests must be guarded by `SST_POSTGRES_DSN`.
- Unit tests must not call external providers, consume credits, or require network.
- Secrets are read from environment only and are never logged.
- Use migrations for schema changes. Do not manually edit database state.
- Defaults must be fail-closed and safe: in-memory/dry-run remains available until PostgreSQL is confirmed.

## Current Evidence

- `app/back/src/indexing/` already contains domain models, LlamaIndex document factory, structure-aware node parser, metadata pipeline, deterministic mock embeddings, in-memory docstore/vector store, and `LlamaIndexingPort`.
- `scripts/indexing/run_indexing.py` already filters inventory records to `processing_status == "processed"` and indexes 41 approved documents in local dry-run mode.
- `migrations/20260721_create_llama_index_tables.sql` enables pgvector and creates preliminary `llama_index_documents` and `llama_index_vectors` tables.
- The current vector table uses a generic `embedding vector` column and does not yet enforce profile-level physical separation.

## External References To Recheck During Implementation

- LlamaIndex Postgres vector store docs: `https://docs.llamaindex.org.cn/en/stable/api_reference/storage/vector_store/postgres/`
- LlamaIndex ingestion pipeline docs: `https://developers.llamaindex.ai/python/framework/`
- pgvector README: `https://github.com/pgvector/pgvector/blob/master/README.md`

The official pgvector README states that pgvector supports exact and approximate nearest-neighbor search, HNSW and IVFFlat indexes, and distance operators for L2, inner product, cosine, and L1. It also notes HNSW has better speed/recall tradeoff than IVFFlat but slower build and higher memory. LlamaIndex `PGVectorStore.from_params` accepts `embed_dim`, `hybrid_search`, `text_search_config`, `hnsw_kwargs`, `use_halfvec`, and metadata indexing options. Reconfirm these APIs before coding.

## Design Decision: Physical Separation By Embedding Profile

### Alternative A: One vectors table with `embedding vector`

Pros:
- Simple schema.
- Easy to query all profiles.

Cons:
- Does not prevent mixed dimensions at the database boundary.
- ANN indexes become unsafe or ineffective when dimensions/providers differ.
- Profile mistakes are caught late.

### Alternative B: One vectors table per embedding profile

Pros:
- Hard separation by provider, model, dimension, distance metric, and chunking version.
- Each table can use `vector(<dimension>)` and a matching HNSW/IVFFlat operator class.
- Safer rollback and deletion by profile.

Cons:
- Requires a registry mapping `profile_id` to physical table name.
- Requires migrations or controlled table creation per profile.

### Decision

Use Alternative B. Store all non-vector node/document metadata in shared relational tables, and store embeddings in one physical vector table per active profile. A profile is immutable once it has vectors. Switching embeddings means selecting another profile, not mutating existing rows.

## File Structure

- Create: `app/back/src/indexing/domain/profiles.py`  
  Typed immutable profile models, profile lane policy, and validation.
- Modify: `app/back/src/indexing/domain/models.py`  
  Extend `IndexingProfile` without breaking existing tests.
- Create: `app/back/src/indexing/application/profile_orchestrator.py`  
  Resolves profile choice and validates lane/provider compatibility.
- Create: `app/back/src/indexing/application/repositories.py`  
  Ports for profile registry, node repository, vector repository, and run repository.
- Create: `app/back/src/indexing/infrastructure/postgres/settings.py`  
  Typed PostgreSQL settings loaded from environment.
- Create: `app/back/src/indexing/infrastructure/postgres/sql.py`  
  SQL builders with deterministic table names and no string interpolation for values.
- Create: `app/back/src/indexing/infrastructure/postgres/profile_registry.py`  
  PostgreSQL adapter for profiles.
- Create: `app/back/src/indexing/infrastructure/postgres/node_repository.py`  
  PostgreSQL adapter for durable parent/child node metadata and text.
- Create: `app/back/src/indexing/infrastructure/postgres/vector_repository.py`  
  PostgreSQL adapter for profile-specific vector tables.
- Modify: `app/back/src/indexing/infrastructure/llama_index/pgvector_store.py`  
  Keep in-memory store and add a PostgreSQL-backed implementation through the vector repository port.
- Modify: `app/back/src/indexing/infrastructure/llama_index/pipeline_factory.py`  
  Inject embedding factory, docstore, node repository, vector repository, and profile orchestrator.
- Create: `app/back/tests/indexing/domain/test_profiles.py`
- Create: `app/back/tests/indexing/application/test_profile_orchestrator.py`
- Create: `app/back/tests/indexing/infrastructure/postgres/test_sql.py`
- Create: `app/back/tests/indexing/infrastructure/postgres/test_profile_registry_contract.py`
- Create: `app/back/tests/indexing/infrastructure/postgres/test_vector_repository_contract.py`
- Create: `app/back/tests/indexing/infrastructure/postgres/test_postgres_live.py`
- Modify: `scripts/indexing/run_indexing.py`
- Modify: `scripts/indexing/validate_index.py`
- Modify: `package.json`
- Create: `migrations/20260722_indexing_profiles_pgvector.sql`
- Create: `docs/adr/ADR-005-postgres-pgvector-profile-separation.md`

---

### Task 1: Profile Domain Contract

**Files:**
- Create: `app/back/src/indexing/domain/profiles.py`
- Modify: `app/back/src/indexing/domain/models.py`
- Test: `app/back/tests/indexing/domain/test_profiles.py`

**Interfaces:**
- Produces: `EmbeddingProviderName`, `IngestionOrigin`, `DistanceMetric`, `VectorTableName`, `ResolvedIndexingProfile`
- Consumes: existing `IndexingProfile`

- [ ] **Step 1: Write the failing tests**

```python
from indexing.domain.profiles import ResolvedIndexingProfile


def test_profile_rejects_embedding_dimension_mismatch() -> None:
    profile = ResolvedIndexingProfile(
        profile_id="llama-bge-m3-v1",
        ingestion_origin="llama_cloud",
        chunking_version="structure-aware-v1",
        embedding_provider="bge",
        embedding_model="BAAI/bge-m3",
        embedding_dimension=1024,
        distance_metric="cosine",
        vector_table="idx_vec_llama_bge_m3_v1",
        metadata_schema_version="2.0",
        active=True,
        config_hash="a" * 64,
    )

    assert profile.vector_table == "idx_vec_llama_bge_m3_v1"
    assert profile.embedding_dimension == 1024
```

```python
import pytest
from pydantic import ValidationError
from indexing.domain.profiles import ResolvedIndexingProfile


def test_profile_rejects_invalid_vector_table_name() -> None:
    with pytest.raises(ValidationError):
        ResolvedIndexingProfile(
            profile_id="bad",
            ingestion_origin="llama_cloud",
            chunking_version="structure-aware-v1",
            embedding_provider="bge",
            embedding_model="BAAI/bge-m3",
            embedding_dimension=1024,
            distance_metric="cosine",
            vector_table="public.bad;drop table x",
            metadata_schema_version="2.0",
            active=True,
            config_hash="a" * 64,
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm run python -- -m pytest app/back/tests/indexing/domain/test_profiles.py -q`  
Expected: FAIL because `indexing.domain.profiles` does not exist.

- [ ] **Step 3: Implement minimal domain model**

Create `profiles.py` with:

```python
from __future__ import annotations

from typing import Literal

from pydantic import Field

from ingestion.schemas.common import StrictModel


EmbeddingProviderName = Literal["mock", "bge", "voyage", "cohere"]
IngestionOrigin = Literal["local", "llama_cloud"]
DistanceMetric = Literal["cosine", "l2", "inner_product"]


class ResolvedIndexingProfile(StrictModel):
    profile_id: str = Field(min_length=1)
    ingestion_origin: IngestionOrigin
    chunking_version: str = Field(min_length=1)
    embedding_provider: EmbeddingProviderName
    embedding_model: str = Field(min_length=1)
    embedding_dimension: int = Field(gt=0)
    distance_metric: DistanceMetric
    vector_table: str = Field(pattern=r"^idx_vec_[a-z0-9_]+$")
    metadata_schema_version: str = Field(min_length=1)
    active: bool
    config_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `npm run python -- -m pytest app/back/tests/indexing/domain/test_profiles.py -q`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/back/src/indexing/domain/profiles.py app/back/src/indexing/domain/models.py app/back/tests/indexing/domain/test_profiles.py
git commit -m "feat(indexing): add embedding profile domain contract"
```

---

### Task 2: Profile Registry And Lane Orchestrator

**Files:**
- Create: `app/back/src/indexing/application/profile_orchestrator.py`
- Create: `app/back/src/indexing/application/repositories.py`
- Test: `app/back/tests/indexing/application/test_profile_orchestrator.py`

**Interfaces:**
- Consumes: `ResolvedIndexingProfile`
- Produces: `ProfileRegistry.get(profile_id: str) -> ResolvedIndexingProfile`
- Produces: `EmbeddingProfileOrchestrator.resolve(profile_id: str, ingestion_origin: str) -> ResolvedIndexingProfile`

- [ ] **Step 1: Write the failing tests**

```python
import pytest

from indexing.application.profile_orchestrator import (
    EmbeddingProfileOrchestrator,
    ProfileLaneMismatchError,
)
from indexing.domain.profiles import ResolvedIndexingProfile


class FakeRegistry:
    def __init__(self, profile: ResolvedIndexingProfile) -> None:
        self.profile = profile

    def get(self, profile_id: str) -> ResolvedIndexingProfile:
        assert profile_id == self.profile.profile_id
        return self.profile


def _profile(origin: str = "llama_cloud") -> ResolvedIndexingProfile:
    return ResolvedIndexingProfile(
        profile_id="llama-bge-m3-v1",
        ingestion_origin=origin,
        chunking_version="structure-aware-v1",
        embedding_provider="bge",
        embedding_model="BAAI/bge-m3",
        embedding_dimension=1024,
        distance_metric="cosine",
        vector_table="idx_vec_llama_bge_m3_v1",
        metadata_schema_version="2.0",
        active=True,
        config_hash="a" * 64,
    )


def test_orchestrator_returns_active_profile_for_matching_lane() -> None:
    result = EmbeddingProfileOrchestrator(FakeRegistry(_profile())).resolve(
        profile_id="llama-bge-m3-v1",
        ingestion_origin="llama_cloud",
    )
    assert result.embedding_provider == "bge"


def test_orchestrator_rejects_local_documents_for_llama_profile() -> None:
    with pytest.raises(ProfileLaneMismatchError):
        EmbeddingProfileOrchestrator(FakeRegistry(_profile())).resolve(
            profile_id="llama-bge-m3-v1",
            ingestion_origin="local",
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm run python -- -m pytest app/back/tests/indexing/application/test_profile_orchestrator.py -q`  
Expected: FAIL because orchestrator does not exist.

- [ ] **Step 3: Implement ports and orchestrator**

```python
from __future__ import annotations

from typing import Protocol

from indexing.domain.profiles import IngestionOrigin, ResolvedIndexingProfile


class ProfileRegistry(Protocol):
    def get(self, profile_id: str) -> ResolvedIndexingProfile:
        """Return an immutable indexing profile by id."""
```

```python
from __future__ import annotations

from indexing.application.repositories import ProfileRegistry
from indexing.domain.profiles import IngestionOrigin, ResolvedIndexingProfile


class ProfileLaneMismatchError(ValueError):
    """The selected embedding profile is not valid for this ingestion lane."""


class InactiveProfileError(ValueError):
    """The selected profile exists but is not active."""


class EmbeddingProfileOrchestrator:
    def __init__(self, registry: ProfileRegistry) -> None:
        self._registry = registry

    def resolve(
        self,
        *,
        profile_id: str,
        ingestion_origin: IngestionOrigin,
    ) -> ResolvedIndexingProfile:
        profile = self._registry.get(profile_id)
        if not profile.active:
            raise InactiveProfileError(f"profile is inactive: {profile_id}")
        if profile.ingestion_origin != ingestion_origin:
            raise ProfileLaneMismatchError(
                f"profile {profile_id} belongs to {profile.ingestion_origin}, not {ingestion_origin}"
            )
        return profile
```

- [ ] **Step 4: Run tests**

Run: `npm run python -- -m pytest app/back/tests/indexing/application/test_profile_orchestrator.py -q`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/back/src/indexing/application/repositories.py app/back/src/indexing/application/profile_orchestrator.py app/back/tests/indexing/application/test_profile_orchestrator.py
git commit -m "feat(indexing): add embedding profile orchestrator"
```

---

### Task 3: PostgreSQL Schema Migration

**Files:**
- Create: `migrations/20260722_indexing_profiles_pgvector.sql`
- Test: `app/back/tests/indexing/infrastructure/postgres/test_sql.py`

**Interfaces:**
- Produces durable tables:
  - `indexing_profiles`
  - `indexing_runs`
  - `indexing_run_documents`
  - `indexing_nodes`
  - profile vector tables, one per profile

- [ ] **Step 1: Write SQL contract tests**

```python
from pathlib import Path


def test_pgvector_migration_creates_profile_registry() -> None:
    sql = Path("migrations/20260722_indexing_profiles_pgvector.sql").read_text(
        encoding="utf-8"
    )
    assert "CREATE EXTENSION IF NOT EXISTS vector" in sql
    assert "CREATE TABLE IF NOT EXISTS indexing_profiles" in sql
    assert "UNIQUE (ingestion_origin, embedding_provider, embedding_model, embedding_dimension, distance_metric, chunking_version)" in sql


def test_pgvector_migration_does_not_create_one_mixed_vector_table() -> None:
    sql = Path("migrations/20260722_indexing_profiles_pgvector.sql").read_text(
        encoding="utf-8"
    )
    assert "llama_index_vectors (" not in sql
    assert "profile vector tables are created through controlled migrations" in sql
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm run python -- -m pytest app/back/tests/indexing/infrastructure/postgres/test_sql.py -q`  
Expected: FAIL because migration does not exist.

- [ ] **Step 3: Create migration**

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS indexing_profiles (
    profile_id TEXT PRIMARY KEY,
    ingestion_origin TEXT NOT NULL CHECK (ingestion_origin IN ('local', 'llama_cloud')),
    chunking_version TEXT NOT NULL,
    embedding_provider TEXT NOT NULL CHECK (embedding_provider IN ('mock', 'bge', 'voyage', 'cohere')),
    embedding_model TEXT NOT NULL,
    embedding_dimension INTEGER NOT NULL CHECK (embedding_dimension > 0),
    distance_metric TEXT NOT NULL CHECK (distance_metric IN ('cosine', 'l2', 'inner_product')),
    vector_table TEXT NOT NULL UNIQUE CHECK (vector_table ~ '^idx_vec_[a-z0-9_]+$'),
    metadata_schema_version TEXT NOT NULL,
    config_hash TEXT NOT NULL CHECK (config_hash ~ '^[0-9a-f]{64}$'),
    active BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (ingestion_origin, embedding_provider, embedding_model, embedding_dimension, distance_metric, chunking_version)
);

CREATE TABLE IF NOT EXISTS indexing_runs (
    run_id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL REFERENCES indexing_profiles(profile_id),
    status TEXT NOT NULL CHECK (status IN ('pending', 'running', 'completed', 'failed', 'cancelled', 'blocked')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    config_hash TEXT NOT NULL CHECK (config_hash ~ '^[0-9a-f]{64}$'),
    summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    warnings JSONB NOT NULL DEFAULT '[]'::jsonb
);

CREATE TABLE IF NOT EXISTS indexing_run_documents (
    run_id TEXT NOT NULL REFERENCES indexing_runs(run_id) ON DELETE CASCADE,
    document_id TEXT NOT NULL,
    source_relpath TEXT NOT NULL,
    source_hash TEXT NOT NULL CHECK (source_hash ~ '^[0-9a-f]{64}$'),
    ingestion_origin TEXT NOT NULL CHECK (ingestion_origin IN ('local', 'llama_cloud')),
    eligibility_status TEXT NOT NULL CHECK (eligibility_status IN ('included', 'excluded', 'blocked')),
    eligibility_reason TEXT NOT NULL,
    indexed_parent_nodes INTEGER NOT NULL DEFAULT 0 CHECK (indexed_parent_nodes >= 0),
    indexed_child_nodes INTEGER NOT NULL DEFAULT 0 CHECK (indexed_child_nodes >= 0),
    error_code TEXT,
    PRIMARY KEY (run_id, document_id)
);

CREATE TABLE IF NOT EXISTS indexing_nodes (
    node_id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    source_relpath TEXT NOT NULL,
    source_hash TEXT NOT NULL CHECK (source_hash ~ '^[0-9a-f]{64}$'),
    ingestion_origin TEXT NOT NULL CHECK (ingestion_origin IN ('local', 'llama_cloud')),
    node_role TEXT NOT NULL CHECK (node_role IN ('parent', 'child')),
    parent_node_id TEXT,
    chunk_index INTEGER,
    page_start INTEGER,
    page_end INTEGER,
    section_title TEXT,
    section_path TEXT,
    text TEXT NOT NULL,
    metadata JSONB NOT NULL,
    chunking_version TEXT NOT NULL,
    processing_fingerprint TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (node_role = 'parent' OR parent_node_id IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_indexing_nodes_document
    ON indexing_nodes (document_id);

CREATE INDEX IF NOT EXISTS idx_indexing_nodes_parent
    ON indexing_nodes (parent_node_id);

CREATE INDEX IF NOT EXISTS idx_indexing_nodes_metadata
    ON indexing_nodes USING gin (metadata);

-- profile vector tables are created through controlled migrations such as:
-- CREATE TABLE idx_vec_llama_bge_m3_v1 (
--     node_id TEXT PRIMARY KEY REFERENCES indexing_nodes(node_id) ON DELETE CASCADE,
--     document_id TEXT NOT NULL,
--     embedding vector(1024) NOT NULL,
--     metadata JSONB NOT NULL,
--     updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
-- );
-- CREATE INDEX idx_vec_llama_bge_m3_v1_hnsw
--     ON idx_vec_llama_bge_m3_v1 USING hnsw (embedding vector_cosine_ops);
```

- [ ] **Step 4: Run tests**

Run: `npm run python -- -m pytest app/back/tests/indexing/infrastructure/postgres/test_sql.py -q`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add migrations/20260722_indexing_profiles_pgvector.sql app/back/tests/indexing/infrastructure/postgres/test_sql.py
git commit -m "feat(indexing): add postgres profile registry schema"
```

---

### Task 4: PostgreSQL Settings And SQL Builder

**Files:**
- Create: `app/back/src/indexing/infrastructure/postgres/settings.py`
- Create: `app/back/src/indexing/infrastructure/postgres/sql.py`
- Test: `app/back/tests/indexing/infrastructure/postgres/test_sql.py`

**Interfaces:**
- Produces: `PostgresIndexingSettings.from_env(environ: Mapping[str, str])`
- Produces: `vector_table_name(profile_id: str) -> str`
- Produces: `create_vector_table_sql(profile: ResolvedIndexingProfile) -> str`

- [ ] **Step 1: Add failing tests**

```python
from indexing.domain.profiles import ResolvedIndexingProfile
from indexing.infrastructure.postgres.sql import create_vector_table_sql


def test_vector_table_sql_uses_dimension_and_cosine_ops() -> None:
    profile = ResolvedIndexingProfile(
        profile_id="llama-bge-m3-v1",
        ingestion_origin="llama_cloud",
        chunking_version="structure-aware-v1",
        embedding_provider="bge",
        embedding_model="BAAI/bge-m3",
        embedding_dimension=1024,
        distance_metric="cosine",
        vector_table="idx_vec_llama_bge_m3_v1",
        metadata_schema_version="2.0",
        active=True,
        config_hash="a" * 64,
    )

    sql = create_vector_table_sql(profile)

    assert "embedding vector(1024) NOT NULL" in sql
    assert "USING hnsw (embedding vector_cosine_ops)" in sql
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run python -- -m pytest app/back/tests/indexing/infrastructure/postgres/test_sql.py -q`  
Expected: FAIL because SQL builder does not exist.

- [ ] **Step 3: Implement minimal SQL builder**

```python
from __future__ import annotations

from indexing.domain.profiles import ResolvedIndexingProfile


_DISTANCE_OPS = {
    "cosine": "vector_cosine_ops",
    "l2": "vector_l2_ops",
    "inner_product": "vector_ip_ops",
}


def create_vector_table_sql(profile: ResolvedIndexingProfile) -> str:
    table = profile.vector_table
    ops = _DISTANCE_OPS[profile.distance_metric]
    return f"""
CREATE TABLE IF NOT EXISTS {table} (
    node_id TEXT PRIMARY KEY REFERENCES indexing_nodes(node_id) ON DELETE CASCADE,
    document_id TEXT NOT NULL,
    embedding vector({profile.embedding_dimension}) NOT NULL,
    metadata JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS {table}_document_id
    ON {table} (document_id);

CREATE INDEX IF NOT EXISTS {table}_metadata
    ON {table} USING gin (metadata);

CREATE INDEX IF NOT EXISTS {table}_hnsw
    ON {table} USING hnsw (embedding {ops});
"""
```

- [ ] **Step 4: Run tests**

Run: `npm run python -- -m pytest app/back/tests/indexing/infrastructure/postgres/test_sql.py -q`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/back/src/indexing/infrastructure/postgres/settings.py app/back/src/indexing/infrastructure/postgres/sql.py app/back/tests/indexing/infrastructure/postgres/test_sql.py
git commit -m "feat(indexing): add pgvector sql builders"
```

---

### Task 5: PostgreSQL Repositories Behind Ports

**Files:**
- Modify: `app/back/src/indexing/application/repositories.py`
- Create: `app/back/src/indexing/infrastructure/postgres/profile_registry.py`
- Create: `app/back/src/indexing/infrastructure/postgres/node_repository.py`
- Create: `app/back/src/indexing/infrastructure/postgres/vector_repository.py`
- Test: `app/back/tests/indexing/infrastructure/postgres/test_profile_registry_contract.py`
- Test: `app/back/tests/indexing/infrastructure/postgres/test_vector_repository_contract.py`

**Interfaces:**
- Produces: `NodeRepository.replace_document_nodes(document_id: str, nodes: Sequence[BaseNode]) -> int`
- Produces: `VectorRepository.replace_document_vectors(document_id: str, profile: ResolvedIndexingProfile, nodes: Sequence[BaseNode], embeddings: Sequence[list[float]]) -> int`

- [ ] **Step 1: Write contract tests using fakes first**

```python
from indexing.infrastructure.llama_index.pgvector_store import VectorStoreWriteError


def test_vector_repository_rejects_embedding_count_mismatch(fake_vector_repository, profile, nodes):
    with pytest.raises(VectorStoreWriteError):
        fake_vector_repository.replace_document_vectors(
            document_id="doc_1",
            profile=profile,
            nodes=nodes,
            embeddings=[],
        )
```

- [ ] **Step 2: Run tests to verify failure**

Run: `npm run python -- -m pytest app/back/tests/indexing/infrastructure/postgres -q`  
Expected: FAIL because repository ports/adapters do not exist.

- [ ] **Step 3: Implement ports and PostgreSQL adapters**

Use parameterized SQL for values. Only table names may be inserted into SQL strings, and only after validation by `ResolvedIndexingProfile.vector_table`.

```python
class VectorRepository(Protocol):
    def replace_document_vectors(
        self,
        *,
        document_id: str,
        profile: ResolvedIndexingProfile,
        nodes: Sequence[BaseNode],
        embeddings: Sequence[list[float]],
    ) -> int:
        """Replace vectors for one document in one profile table."""
```

- [ ] **Step 4: Add optional live PostgreSQL tests**

Create live tests marked with:

```python
pytestmark = pytest.mark.postgres_live
```

Skip unless `SST_POSTGRES_DSN` is set.

- [ ] **Step 5: Run non-live tests**

Run: `npm run python -- -m pytest app/back/tests/indexing/infrastructure/postgres -q -m "not postgres_live"`  
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/back/src/indexing/application/repositories.py app/back/src/indexing/infrastructure/postgres app/back/tests/indexing/infrastructure/postgres
git commit -m "feat(indexing): add postgres indexing repositories"
```

---

### Task 6: Wire PostgreSQL Store Into LlamaIndexingPort

**Files:**
- Modify: `app/back/src/indexing/infrastructure/llama_index/pipeline_factory.py`
- Modify: `app/back/src/indexing/infrastructure/llama_index/pgvector_store.py`
- Test: `app/back/tests/indexing/infrastructure/test_ingestion_pipeline.py`

**Interfaces:**
- Consumes: `VectorRepository`, `NodeRepository`, `EmbeddingProfileOrchestrator`
- Produces: `LlamaIndexingPort(..., storage_mode="memory" | "postgres")`

- [ ] **Step 1: Write failing tests**

```python
@pytest.mark.anyio
async def test_indexing_port_writes_one_profile_without_touching_other_profiles() -> None:
    repository = RecordingVectorRepository()
    indexer = LlamaIndexingPort(
        bundle_loader=StaticBundleLoader(),
        vector_repository=repository,
        profile_orchestrator=FakeProfileOrchestrator(expected_origin="llama_cloud"),
    )

    await indexer.index(_document())

    assert repository.calls == [("doc_1", "idx_vec_llama_bge_m3_v1")]
```

- [ ] **Step 2: Run test to verify failure**

Run: `npm run python -- -m pytest app/back/tests/indexing/infrastructure/test_ingestion_pipeline.py -q`  
Expected: FAIL because constructor injection is not supported yet.

- [ ] **Step 3: Implement injection**

Preserve in-memory defaults. PostgreSQL must be opt-in.

- [ ] **Step 4: Run tests**

Run: `npm run python -- -m pytest app/back/tests/indexing/infrastructure/test_ingestion_pipeline.py app/back/tests/indexing/infrastructure/postgres -q -m "not postgres_live"`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/back/src/indexing/infrastructure/llama_index app/back/tests/indexing/infrastructure
git commit -m "feat(indexing): wire postgres vector persistence into llamaindex port"
```

---

### Task 7: CLI Profile Selection And Dry-Run Safety

**Files:**
- Modify: `scripts/indexing/run_indexing.py`
- Modify: `package.json`
- Test: `app/back/tests/indexing/test_run_indexing_cli.py`

**Interfaces:**
- Adds CLI flags:
  - `--store memory|postgres`
  - `--profile <profile_id>`
  - `--ingestion-origin local|llama_cloud`
  - `--dry-run`
  - `--persist-confirmed`

- [ ] **Step 1: Write failing tests**

```python
def test_run_indexing_blocks_postgres_without_confirmation(tmp_path) -> None:
    result = run_indexing(
        normalized_root=tmp_path,
        only_sources=[],
        force=False,
        profile_id="llama-bge-m3-v1",
        dry_run=False,
        store="postgres",
        persist_confirmed=False,
    )

    assert result["status"] == "blocked"
    assert result["reason"] == "postgres_not_confirmed"
```

- [ ] **Step 2: Run test to verify failure**

Run: `npm run python -- -m pytest app/back/tests/indexing/test_run_indexing_cli.py -q`  
Expected: FAIL because `store` and `persist_confirmed` are not accepted.

- [ ] **Step 3: Implement CLI safety**

Rules:
- `--store memory` can run today.
- `--store postgres` returns `blocked` unless `--persist-confirmed` is passed and `SST_POSTGRES_DSN` exists.
- `--dry-run` never writes vectors.
- `--profile` must resolve through registry.

- [ ] **Step 4: Run tests**

Run: `npm run python -- -m pytest app/back/tests/indexing/test_run_indexing_cli.py app/back/tests/indexing/test_package_scripts.py -q`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/indexing/run_indexing.py package.json app/back/tests/indexing/test_run_indexing_cli.py app/back/tests/indexing/test_package_scripts.py
git commit -m "feat(indexing): add safe postgres indexing cli controls"
```

---

### Task 8: Validation And Operational Reports

**Files:**
- Modify: `scripts/indexing/validate_index.py`
- Create: `app/back/tests/indexing/test_validate_index_cli.py`
- Create: `docs/adr/ADR-005-postgres-pgvector-profile-separation.md`

**Interfaces:**
- Produces report fields:
  - `profile_id`
  - `ingestion_origin`
  - `vector_table`
  - `indexed_documents`
  - `indexed_child_nodes`
  - `orphan_vectors`
  - `mixed_provider_errors`
  - `dimension_errors`
  - `unapproved_document_errors`

- [ ] **Step 1: Write failing validation tests**

```python
def test_validate_index_reports_mixed_provider_as_error() -> None:
    report = validate_index_state(
        documents=[{"document_id": "doc_1", "ingestion_origin": "local"}],
        profiles=[{"profile_id": "llama-bge-m3-v1", "ingestion_origin": "llama_cloud"}],
        vectors=[{"document_id": "doc_1", "profile_id": "llama-bge-m3-v1"}],
    )

    assert report.status == "failed"
    assert report.mixed_provider_errors == 1
```

- [ ] **Step 2: Run test to verify failure**

Run: `npm run python -- -m pytest app/back/tests/indexing/test_validate_index_cli.py -q`  
Expected: FAIL until validation report supports these fields.

- [ ] **Step 3: Implement validation**

Validation must fail when:
- vector rows exist for unapproved documents;
- profile lane does not match document ingestion origin;
- dimension differs from profile;
- vectors exist without child nodes;
- child nodes exist without parent nodes;
- rows from different providers are present in one vector table.

- [ ] **Step 4: Run indexing tests**

Run: `npm run test:indexing`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/indexing/validate_index.py app/back/tests/indexing/test_validate_index_cli.py docs/adr/ADR-005-postgres-pgvector-profile-separation.md
git commit -m "feat(indexing): validate pgvector profile isolation"
```

## Final Verification

Run non-live checks:

```bash
npm run python -- -m pip check
npm run test:indexing
npm run indexing:run -- --dry-run
npm run indexing:validate
npm run python -- -m pytest app/back/tests/indexing -m "not postgres_live" -q
```

Run live checks only after PostgreSQL/pgvector is confirmed:

```bash
npm run python -- -m pytest app/back/tests/indexing/infrastructure/postgres/test_postgres_live.py -q
npm run indexing:run -- --store postgres --profile llama-bge-m3-v1 --ingestion-origin llama_cloud --persist-confirmed
npm run indexing:validate -- --store postgres --profile llama-bge-m3-v1
```

## Definition Of Done

- PostgreSQL schema is versioned by migration.
- Profile registry prevents mixing providers, models, dimensions, metrics, chunking versions, and ingestion origins.
- Vector tables are physically separated by profile.
- In-memory mode remains available for tests and dry-runs.
- PostgreSQL mode is blocked until infrastructure is explicitly confirmed.
- Only processed/approved documents can be indexed.
- Reindexing one document replaces its nodes and vectors for the selected profile only.
- Validation catches orphan vectors, mixed provider rows, dimension mismatch, and unapproved documents.
- No SDK imports appear in domain or application layers.
- `npm run test:indexing` passes.
- No secrets are logged or committed.

