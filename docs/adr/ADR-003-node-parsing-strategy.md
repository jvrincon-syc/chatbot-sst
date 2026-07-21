# ADR-003: Node Parsing Strategy

Date: 2026-07-21

## Status

Accepted as the experimental baseline for Fase 6.

## Context

The plan requires comparing three strategies:

1. LlamaIndex `HierarchicalNodeParser`.
2. Element-aware parsing from LlamaParse items/tables.
3. A hybrid structure-aware parser preserving page and parent-child evidence.

The first production-quality need in this branch is traceability: every retrieved
child must resolve to a parent, page and `ref_doc_id`.

## Decision

Use `StructureAwareNodeParser` as the baseline strategy. It creates one parent
per normalized page and deterministic child nodes inside that parent. The
official hierarchical parser and element-aware facade are present as adapters
for benchmarking, but they are not the default yet.

## Evidence

`npm run test:indexing` passed with tests verifying deterministic IDs, parent
relationships on every child, page metadata and rollback behavior.

## Consequences

The branch favors auditability over semantic chunk sophistication until the
benchmark dataset proves that item-aware or hierarchical parsing improves
retrieval without weakening citations.
