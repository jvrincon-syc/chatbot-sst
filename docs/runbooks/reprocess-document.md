# Reprocess Document Runbook

## Trigger

A source document changed, validation failed or a reviewer requested reprocess.

## Response

1. Identify `source_relpath` and `document_id`.
2. Re-run ingestion with `--only-source <source_relpath> --force`.
3. Validate normalized artifacts.
4. Index only when `processing_status=processed` or sandbox indexing is explicit.

## Recovery

If indexing fails after docstore write, restore from the previous docstore/vector
snapshot or re-run indexing for that `ref_doc_id`.
