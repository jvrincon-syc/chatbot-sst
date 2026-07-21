# Manual Corpus Audit

Fecha: 2026-07-21

Esta auditoria inicial identifica una muestra pequena y diversa para evaluacion. No autoriza por si sola envio a Llama Cloud.

## Muestra propuesta

| Archivo | Tipo esperado | Rasgo a evaluar | Cloud autorizado |
|---|---|---|---|
| `general_sst/manuales/politica/1778000305710_syc_politicadeseguridady.pdf` | politica | PDF corporativo, control documental | pendiente |
| `general_sst/manuales/organizacion/reglamento_interno_trabajo/1780069704133_syc_REGLAMENTOACTUALIZADO29052026.pdf` | reglamento | PDF largo, tablas/control documental | pendiente |
| `convivencia_laboral/reglamento_comite/1761609513260_syc_RG.RH-01-SST23102025.pdf` | reglamento/formulario relacionado | caso historico de clasificacion sensible | pendiente |
| `convivencia_laboral/manual/1761580555950_syc_RE.RH-04SST23102025.pdf` | formulario/reglamento segun contenido | quejas/denuncias y campos de formulario | pendiente |
| `general_sst/capacitaciones/pausas_activas/1711493199040_syc_pg-rh-10-sst.program.pdf` | programa | tablas y programa SST | pendiente |
| `general_sst/capacitaciones/politica_seguridad_trabajo/seguridad_vial/1768504433896_syc_1723156961461_syc_vial.pdf` | capacitacion/politica | PDF de seguridad vial | pendiente |
| `copasst/miembros_copasst_2025_2027.md` | informacion_general | Markdown con lista/estructura simple | no requiere cloud |
| `general_sst/manuales/introduccion.md` | manual | Markdown baseline local | no requiere cloud |

## Ground truth inicial

- PDF total auditado en corpus: 9.
- Paginas esperadas en golden existente: 77.
- Los documentos con formularios/quejas deben priorizar evidencia por pagina y no aceptar clasificacion solo por ruta.

## Presupuesto inicial

- `LLAMA_PARSE_MAX_CREDITS_PER_RUN=500`.
- `LLAMA_PARSE_MAX_CONCURRENCY=2`.
- Stop condition: detener cualquier live run si no hay autorizacion de datos o si el estimado supera presupuesto.
