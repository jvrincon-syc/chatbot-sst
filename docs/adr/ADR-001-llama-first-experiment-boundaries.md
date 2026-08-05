# ADR-001: Llama-first Experiment Boundaries

Fecha: 2026-07-21

## Estado

Aceptada para la rama experimental `llamaparse_experiment`.

## Contexto

El repositorio ya tiene contratos auditables para `docs_raw`, `docs_normalized`, bundles, validacion, inventory, review policy y promocion. El experimento Llama-first debe evaluar LlamaParse, LlamaClassify, LlamaExtract y LlamaIndex OSS sin perder trazabilidad ni mezclar SDKs externos en el dominio.

El plan escrito contiene un typo de rama: `llamparse_experiment`. La rama real verificada es `llamaparse_experiment`.

## Decision

- Mantener `docs_raw` inmutable.
- Preservar `docs_normalized` como contrato auditable interno.
- Introducir puertos por capacidad (`parse`, `classify`, `extract`) antes de SDKs.
- Mantener dominio y aplicacion sin imports de `llama_cloud` ni LlamaIndex concreto.
- Leer API keys solo desde entorno/secrets locales.
- No ejecutar smoke live cloud con documentos corporativos hasta documentar
  autorizacion de datos, region, retencion/eliminacion y presupuesto.
- Usar `latest` solo en exploracion; exigir version fechada antes de benchmark/promocion.

## Consecuencias

- El camino cloud queda detras de feature flags y adapters.
- Los tests unitarios nuevos no consumen creditos ni requieren API key.
- Los adapters cloud mapean resultados externos a modelos internos con
  evidencia por documento/pagina.

## Criterios de revision

- El smoke con documentos corporativos sigue bloqueado sin autorizacion
  explicita; se permite smoke sintetico no sensible.
- No se aceptan campos criticos extraidos sin evidencia.
- No se mezclan perfiles de embedding/vector store sin version y dimension declaradas.
