# Chunking Policy

## Canonical Profile

`local-structural-v1` is the local structural chunking profile. It uses a
canonical tokenizer selected by the chunking implementation; this policy only
defines observable behavior and does not own the tokenizer internals.

| Setting | Value |
| --- | ---: |
| Child minimum tokens | 250 |
| Child target tokens | 350 |
| Child maximum tokens | 450 |
| Overlap ratio | 0.12 |
| Overlap minimum tokens | 30 |
| Overlap maximum tokens | 60 |

The target overlap is `round(350 * 0.12)`, or 42 tokens. It is clamped to the
configured overlap range. The child maximum includes overlap tokens; a child
whose complete canonical-token count exceeds 450 is invalid.

## Invariants

- `child_min_tokens <= child_target_tokens <= child_max_tokens`.
- `0 <= overlap_ratio <= 1`.
- `overlap_min_tokens <= overlap_max_tokens < child_max_tokens`.
- Each child references an existing parent in the same document and profile.
- Each parent block ID must reference a block in the normalized document before
  a chunking run is created.
- Source pages and character offsets are non-negative, ordered, and auditable.
- Structural blocks, parents, and children cannot have blank text.
- Structural block kinds and zero-overlap reasons are validated as runtime enum
  members; strings that merely resemble enum values are rejected.
- IDs are deterministic SHA-256 identities over content, profile, and stable
  structural position. Bundle and run fingerprints include canonical parent and
  child payloads, including child token count, overlap token count, and the
  zero-overlap reason.

## Zero Overlap

Zero overlap is fail-closed. It is permitted only when the child carries one of
the profile's explicit semantic exceptions:

- `document_start`
- `table_or_form_boundary`

`section_boundary` exists as an enum for a future profile, but is not allowed
by `local-structural-v1`. A nonzero overlap must stay within the configured
minimum and maximum range.

## Boundaries

These contracts contain no filesystem, FastAPI, parser, SDK, or tokenizer
implementation. Pydantic remains at external schema boundaries; the chunking
domain and application ports use immutable dataclasses and Python protocols.
