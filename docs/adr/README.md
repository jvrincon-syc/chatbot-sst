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

El estado operativo corto vive en `docs/README.md`,
`docs/ingestion/README.md` y `docs/llama_first/README.md`.
