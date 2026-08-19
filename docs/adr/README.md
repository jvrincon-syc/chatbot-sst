# ADR vigentes

Mantener solo decisiones que afecten contratos, dependencias o rutas
arquitectonicas actuales.

- `ADR-001-llama-first-experiment-boundaries.md`: limites del experimento y
  separacion entre contrato local y proveedores cloud.
- `ADR-002-pydantic-and-llamaindex-pins.md`: pins de Pydantic, Llama Cloud y
  LlamaIndex.
- `ADR-003-node-parsing-strategy.md`: baseline de parent/child nodes con
  trazabilidad.
- `ADR-004-production-parser-routing.md`: routing por feature flags y adopcion
  selectiva.
- `ADR-005-postgres-pgvector-profile-separation.md`: una tabla pgvector por
  perfil de embedding inmutable; separacion de lanes en base de datos.
- `ADR-006-rag-platform-project-variant-release.md`: identidad de plataforma
  multi-proyecto (project/variant/release), aditiva sobre la lane legacy.
- `ADR-009-retrieval-per-project-tenant-isolation.md`: `project_id` de extremo a
  extremo en el runtime de retrieval (search/lexical/parent/activación/rollback);
  aislamiento por proyecto demostrable en SQL, fail-closed.

El estado operativo corto vive en `docs/README.md`,
`docs/ingestion/README.md` y `docs/llama_first/README.md`.
