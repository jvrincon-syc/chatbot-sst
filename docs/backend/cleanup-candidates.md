# Candidatos de limpieza local

Este inventario no borra ni mueve archivos. Toda limpieza requiere aprobacion
explicita del usuario y revision final contra `HEAD`. `docs/` es autoridad
versionada; `memory/`, `plans/` y `.claude/` son guias locales ignoradas por
git. Los cambios sin commit no se usan para decidir que un plan esta
implementado.

## Criterio

- **Activo**: tiene trabajo o decisiones abiertas para la rama actual.
- **Historico util**: conserva contexto no reemplazado por completo.
- **Implementado y absorbido por docs**: el comportamiento esta en `HEAD` y
  el contrato o procedimiento vive en `docs/`.
- **Obsoleto/inconsistente**: contradice `HEAD`, cita rutas inexistentes o
  describe otra rama sin finalidad historica clara.

## Inventario

| Artefacto | Estado observado | Candidato | Evidencia de `HEAD` | Accion propuesta |
| --- | --- | --- | --- | --- |
| `memory/plan_trabajo.md` | Historico util; principios generales absorbidos | Archivar o eliminar tras conservar enlaces | `docs/README.md`, `AGENTS.md` y ADRs cubren el contrato general | Requiere aprobacion |
| `memory/2026-07-21-plan-llama-first-chatbot-sst.md` | Historico util; parcialmente absorbido | Archivar tras reconciliar gaps | `docs/adr/ADR-001-llama-first-experiment-boundaries.md`, `docs/llama_first/README.md` y runbooks versionados | Requiere aprobacion |
| `plans/2026-08-06-embedding-indexing-unified-adjusted.md` | Activo pero inconsistente: checkboxes abiertos y `HEAD` ya cubre gran parte del contrato | Archivar solo despues de cerrar diferencias y confirmar DoD | `HEAD` contiene modulos y pruebas de embedding, indexing y retrieval; no se cuentan cambios sin commit | Requiere decision del responsable |
| `memory/MEMORY.md` | Indice parcialmente obsoleto: tres referencias no existen | Limpiar referencias rotas, no el indice completo | `git ls-files` no contiene `fase1.md`, `auditoria-main-plan-fase-2-chatbot-sst.md` ni `plan-chunking-local-ajustado.md` | Requiere aprobacion |
| `.claude/README.md` y comandos locales | Guia local, no autoridad | Mantener; depurar cuando cambien scripts | `package.json` es fuente de scripts; `docs/rules/TESTING_AND_QUALITY.md` es fuente de gates | No borrar ahora |

## Fuera de alcance

No se proponen borrados de `docs/`, `AGENTS.md`, `docs/rules/` ni de archivos
generados o corporativos. Tampoco se clasifica como implementado el contenido
de `docs/` que aparezca como cambio sin commit en `git status`.

## Aprobacion requerida

Antes de ejecutar cualquier `Remove-Item`, mover archivos o limpiar entradas,
el usuario debe indicar los artefactos exactos y aceptar la perdida de contexto
historico. La propuesta actual es solo de archivo o borrado; no se ha realizado
ninguna eliminacion.
