# Llama-first Decision Log

## 2026-07-21 - Corregir nombre operativo de rama

- Problema: el plan escrito menciona `llamparse_experiment`, pero la rama activa real es `llamaparse_experiment`.
- Alternativa A: renombrar la rama para coincidir con el typo del plan.
- Alternativa B: conservar la rama real y registrar el typo como correccion de baseline.
- Decision: conservar `llamaparse_experiment`; no se renombra la rama durante esta ejecucion.
- Revision futura: si el remoto exige otro nombre, documentar el rename en un commit separado.

## 2026-07-21 - Settings cloud sin cambiar comportamiento del pipeline

- Problema: el usuario pidio activar Llama Cloud en secrets, pero Fase 1 no debe conectar el pipeline oficial todavia.
- Alternativa A: cablear LlamaParse directamente en readers PDF.
- Alternativa B: crear settings y puertos neutrales; adapters cloud vendran despues.
- Decision: implementar settings tipados y cambiar solo `LLAMA_CLOUD_ENABLED=true` en `secrets.env`, sin tocar el pipeline oficial.
- Revision futura: Fase 2 conectara `LlamaParseAdapter` detras de `DocumentParserPort`.

## 2026-07-21 - Versiones de dependencias Llama

- Problema: el plan candidata `llama-cloud==2.11.0`; PyPI muestra `2.12.0` como actual.
- Alternativa A: mantener el candidato exacto del plan.
- Alternativa B: usar la version actual tras verificar resolver.
- Alternativa C: relajar `pydantic<2.11` para adoptar LlamaIndex reciente.
- Decision: declarar `llama-cloud==2.12.0` como extra opcional. El primer spike dejo `llama-indexing` vacio porque los rangos probados chocaban con `pydantic<2.11` o con la integracion Postgres.
- Revision futura: ver ADR-002 para la decision posterior de subir Pydantic y activar LlamaIndex granular.

## 2026-07-21 - Activar LlamaIndex granular

- Problema: Fase 6 requiere `llama-index-core` y `llama-index-vector-stores-postgres`; la version actual de `llama-index-core==0.14.23` trae `llama-index-workflows>=2.14`, que requiere `pydantic>=2.11.5`.
- Alternativa A: mantener `pydantic>=2.0,<2.11` y posponer Fase 6.
- Alternativa B: buscar una linea antigua de LlamaIndex que acepte Pydantic anterior.
- Alternativa C: subir Pydantic a `>=2.11.5,<3`, fijar paquetes granulares y verificar toda la regresion de ingestion.
- Decision: Alternativa C. `pyproject.toml` ahora declara `pydantic>=2.11.5,<3`, `llama-index-core==0.14.23` y `llama-index-vector-stores-postgres==0.8.1`.
- Resultado: `scripts/experiments/check_llama_dependencies.py` reporto `ok=True` con `pydantic 2.13.4` y sin metapaquete `llama-index`; `npm run test:ingestion` paso con `276 passed, 3 skipped`.
- Revision futura: si FastAPI/GUI o despliegue requieren un pin menor de Pydantic, bloquear Fase 6 o fijar una combinacion anterior validada por resolver.

## 2026-07-21 - Smoke cloud bloqueado

- Problema: Fase 0.5 envia documentos al cloud y consume creditos.
- Alternativa A: ejecutar inmediatamente con los PDF del corpus.
- Alternativa B: bloquear hasta tener documento autorizado, region, retencion/eliminacion y presupuesto aprobados.
- Decision: bloquear smoke live; solo se dejan script/schema preparados.
- Revision futura: ejecutar con `LLAMA_CLOUD_LIVE=true` y documento explicitamente autorizado.

## 2026-07-21 - Smoke cloud sintetico habilitado

- Problema: el plan requiere demostrar Parse/Classify/Extract reales, pero no
  se debe subir corpus corporativo sin autorizacion.
- Alternativa A: mantener el smoke bloqueado hasta aprobacion corporativa.
- Alternativa B: ejecutar un smoke vivo con documento sintetico no sensible por
  defecto y exigir `LLAMA_CLOUD_LIVE=true` solo cuando se pase `--source`.
- Decision: Alternativa B. El script crea
  `data/evaluation/llama_first/synthetic_llama_smoke.md`, ejecuta Parse
  `cost_effective`, Classify `FAST` y Extract `cost_effective` con
  `parse_tier=fast`, y guarda solo salidas sanitizadas.
- Resultado: smoke vivo completado con Parse
  `pjb-g05y0jzu8law2xy820haloreyu5e`, Classify
  `clj-gez9e4ucpa1pdcl3c6vv06fd9pes` y Extract
  `ext-zzz5se6fsmx5d2qlqs6wcm7n9dfs`.
- Revision futura: ejecutar el mismo script con un documento corporativo
  explicitamente autorizado y registrar retencion, region y costo real.

## 2026-07-21 - Perfil de llamadas cloud de menor costo

- Problema: reducir consumo de creditos/tokens sin romper el contrato auditable de markdown, items y metadata.
- Alternativa A: usar Parse `fast` para todo.
- Alternativa B: mantener Parse `cost_effective` para PDFs auditables y usar `fast` solo donde la API lo soporta sin markdown/items.
- Decision: Alternativa B. Parse principal queda `cost_effective`; si se configura Parse `fast`, el adapter filtra expands incompatibles. Classify usa `mode=FAST`. Extract usa `tier=cost_effective`, `parse_tier=fast` y limites de paginas.
- Revision futura: si un documento simple solo necesita texto, routearlo explicitamente a un perfil Parse `fast` text-only.

## 2026-07-21 - La ruta no es verdad documental

- Problema: la organizacion de carpetas de `data/docs_raw` es arbitraria y
  estaba generando falsos `classification_conflict`, por ejemplo
  `convivencia_laboral/manual/...` contra un titulo `FORMATO...`, o
  `capacitaciones/.../seguridad_vial/...` contra topic `Seguridad vial`.
- Alternativa A: mantener conflicto siempre que ruta y titulo difieran.
- Alternativa B: tratar ruta como contexto de baja autoridad y nunca como
  penalizacion cuando titulo/control/contenido dan evidencia fuerte.
- Decision: Alternativa B. La ruta conserva `route_prior` y senales debiles,
  pero no genera `classification_conflict` por si sola. Rutas especificas como
  `seguridad_vial` deben ganar sobre contenedores genericos como
  `capacitaciones`; codigo en tabla/header de control gana sobre referencias
  narrativas a otros formatos.
- Resultado esperado: los 9 PDFs Llama-first pasan a `processed` en la
  proyeccion sobre la corrida live, sin `classification_conflict` ni
  `conflicting_code` por organizacion de carpeta.
- Revision futura: si aparece un conflicto real, debe venir de evidencia
  documental interna contradictoria, no de la ubicacion del archivo.
