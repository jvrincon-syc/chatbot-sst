# ADR-004: Production Parser Routing

Date: 2026-07-22

## Status

Accepted for the experiment.

## Context

The branch supports local ingestion and an optional Llama Cloud lane. Corporate
live cloud runs remain blocked until data and budget approvals are available.

## Decision

Keep routing behind feature flags and GUI controls:

- `LLAMA_CLOUD_ENABLED=true` selects LlamaParse for PDFs.
- `LLAMA_CLASSIFY_ENABLED` and `LLAMA_EXTRACT_ENABLED` control optional stops.
- `LLAMA_CALL_ORDER` controls the lane order; Parse is mandatory in cloud mode.
- `LLAMA_LOCAL_FALLBACK_ENABLED=true` preserves local fallback.
- Documents marked `needs_review` are not indexed by default.

Until A/B evidence is complete, production should prefer selective routing:
use Llama-first for complex PDFs, scanned documents, tables and forms, while
keeping simple Markdown/local paths available.

## Consequences

This branch can continue implementing the Llama-first path without forcing all
documents through cloud services or indexing unapproved bundles.
