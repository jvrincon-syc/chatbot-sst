# ADR-005: PostgreSQL pgvector profile separation

Date: 2026-07-22

## Status

Accepted for the `llamaparse_experiment` branch.

## Context

The Llama-first indexing path needs durable PostgreSQL storage for normalized
documents, parent/child nodes and embeddings. Embedding providers can change
between BGE, Voyage, Cohere and the deterministic mock profile used in tests.
Those profiles have different operational runtimes, possible dimensions and
distance metrics, so mixing them in one generic vector table would make ANN
indexes unsafe and hard to audit.

Normalized documents can originate from either the local pipeline or the
Llama-first lane. The database must preserve that origin and prevent vectors
from being written with a profile that belongs to the other lane.

## Decision

Use a shared relational schema for profile registry, indexing runs, normalized
document provenance and durable nodes. Store embeddings in one physical pgvector
table per immutable embedding profile. A profile includes:

- ingestion origin;
- provider and model;
- embedding dimension;
- distance metric;
- chunking version;
- metadata schema version;
- vector table name;
- config hash.

PostgreSQL mode is opt-in. The CLI blocks writes unless both
`--persist-confirmed` and `SST_POSTGRES_DSN` are present. Dry-run and memory
mode remain the safe defaults.

## Alternatives Considered

1. Keep one generic vector table with an unbounded `embedding vector` column.
2. Use one vector table per profile and keep metadata in shared relational
   tables.

Alternative 2 was selected because it enforces separation at the database and
index level instead of relying on late application validation.

## Consequences

Switching embedding providers means selecting or creating another immutable
profile. Reindexing one document replaces nodes and vectors only for the
selected profile lane. Validation must fail closed on orphan vectors,
unapproved documents, lane mismatches and dimension mismatches.
