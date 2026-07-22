# Documentacion vigente

Este indice mantiene el contexto corto. Para una tarea nueva, lee solo esta
pagina y el README del area afectada.

## Areas

- `ingestion/README.md`: contrato vigente de ingesta local, comandos, gates y
  reglas de integridad.
- `llama_first/README.md`: estado del experimento Llama Cloud + LlamaIndex,
  flags, bloqueos y verificacion.
- `adr/`: decisiones de arquitectura que siguen vigentes.
- `runbooks/`: respuestas operativas cortas para incidentes o tareas manuales.

## Fuentes de verdad

- Codigo y scripts: `app/back/src`, `app/back/tests`, `scripts`, `package.json`.
- Configuracion versionada: `pyproject.toml`, `requirements*.txt`,
  `constraints/llama-first.txt`, `secrets.example.env`.
- Salidas generadas o sensibles: `data/` y `secrets.env`; no se deben usar como
  contexto largo salvo que la tarea lo pida.
- Planes historicos: `memory/`; quedan fuera del contexto normal.

## Documentos eliminados o absorbidos

Los logs largos, planes de implementacion y auditorias historicas se compactaron
en los README de area o en ADRs para evitar overflow. Si necesitas evidencia
historica exacta, revisa el historial de git en vez de cargar multiples Markdown
a la vez.
