# Llama Cloud Outage Runbook

## Trigger

Parsing, classification or extraction fails because Llama Cloud is unavailable,
timed out or rate limited.

## Response

1. Set `LLAMA_CLOUD_ENABLED=false` or keep `LLAMA_LOCAL_FALLBACK_ENABLED=true`.
2. Re-run ingestion for affected documents with `--force` only when local
   artifacts must be refreshed.
3. Keep documents with `cloud_fallback_used` in review until evidence is checked.
4. Do not re-run live cloud jobs until service and budget status are confirmed.

## Recovery

Resume from the last successful state. Do not repeat Parse when only Extract
failed and a valid parse job/result exists.
