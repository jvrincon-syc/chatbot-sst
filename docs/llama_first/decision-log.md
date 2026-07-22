# Llama-first Decision Log

Este log conserva solo decisiones vigentes. Detalles historicos de exploracion
quedaron absorbidos por `README.md`, ADRs o historial de git.

## 2026-07-21 - Limites del experimento

- Rama real: `llamaparse_experiment`.
- `docs_raw` permanece inmutable y `docs_normalized` sigue siendo el contrato
  auditable interno.
- Dominio y aplicacion no importan SDKs externos; Llama Cloud y LlamaIndex viven
  detras de puertos/adapters.
- No hay smoke live con documentos corporativos sin autorizacion, region,
  retencion/eliminacion y presupuesto.
- `LLAMA_PARSE_VERSION=latest` es exploratorio; produccion requiere pin fechado.

Ver: `docs/adr/ADR-001-llama-first-experiment-boundaries.md`.

## 2026-07-21 - Dependencias Llama

- Se usa `llama-cloud==2.12.0`.
- Se sube Pydantic a `>=2.11.5,<3`.
- Se usan paquetes granulares `llama-index-core==0.14.23` y
  `llama-index-vector-stores-postgres==0.8.1`.
- Se sigue rechazando el metapaquete global `llama-index`.

Ver: `docs/adr/ADR-002-pydantic-and-llamaindex-pins.md`.

## 2026-07-21 - Smoke cloud sintetico

Para probar Parse/Classify/Extract sin filtrar corpus corporativo, el smoke vivo
por defecto usa documento sintetico no sensible y guarda salidas sanitizadas.
Con `--source` real se exige `LLAMA_CLOUD_LIVE=true`.

Resultado registrado:

```text
Parse: pjb-g05y0jzu8law2xy820haloreyu5e
Classify: clj-gez9e4ucpa1pdcl3c6vv06fd9pes
Extract: ext-zzz5se6fsmx5d2qlqs6wcm7n9dfs
```

## 2026-07-21 - Perfil cloud de menor costo

- Parse auditable queda `cost_effective` para conservar `markdown` e `items`.
- Parse `fast` solo se usa para probes text-only; el adapter filtra expands
  incompatibles.
- Classify usa `FAST`.
- Extract usa `cost_effective` con `parse_tier=fast` y limites de paginas.

## 2026-07-21 - La ruta no es verdad documental

Las carpetas de `data/docs_raw` son contexto operativo de baja autoridad. No
generan `classification_conflict` si titulo, control documental, contenido,
codigo o tablas internas resuelven tipo/topic. Segmentos especificos como
`seguridad_vial` pueden ayudar a elegir topic sobre contenedores genericos como
`capacitaciones`.

## 2026-07-22 - Via Llama configurable por paradas

`LlamaOrchestrator` ejecuta paradas configurables `classify`, `parse` y
`extract`. Parse es obligatorio en modo cloud. Classify y Extract son opcionales.
Si ambos estan activos, Classify debe correr antes de Extract para elegir el
schema correcto.

Ordenes comunes validos:

- `classify,parse,extract`.
- `parse,classify,extract`.
- `classify,parse`.
- `parse,classify`.
- `parse`.

La GUI puede elegir `local` o `llama_cloud`, prender/apagar Classify/Extract y
seleccionar orden sin editar `secrets.env`.
