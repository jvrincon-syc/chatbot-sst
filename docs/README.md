# Documentacion corta

Para evitar overflow, empieza por este indice y abre solo el README del area
afectada. No cargues `data/`, `memory/`, `.tmp/`, `.venv*` ni
`node_modules/` salvo solicitud explicita.

## Areas

- `ingestion/README.md`: ingesta local, Schema 2.0, gates y consumo downstream.
- `llama_first/README.md`: via experimental Llama Cloud/LlamaIndex, flags y
  bloqueos.
- `chunking/`: contrato del chunking local y su API HTTP.
- `adr/`: decisiones de arquitectura vigentes.
- `runbooks/`: acciones operativas breves.
- `rules/`: politicas obligatorias; leerlas cuando el cambio toque calidad,
  seguridad, ramas o revision.

## Fuentes de verdad

- Codigo y scripts: `app/back/src`, `app/back/tests`, `scripts`, `package.json`.
- Configuracion versionada: `pyproject.toml`, `requirements*.txt`,
  `constraints/llama-first.txt`, `secrets.example.env`.
- AGENTS: `AGENTS.md`, `app/back/AGENTS_back.md`,
  `app/front/AGENTS_front.md`.
- Salidas generadas o sensibles: `data/`, `secrets.env`, `manual-test-temp/`
  y cualquier `pytest-*` temporal.
- Planes historicos: `memory/`.

## Poda

Los planes temporales y reportes historicos se absorbieron en README de area o
ADRs. Si necesitas evidencia historica exacta, usa el historial de git en vez de
cargar multiples Markdown.
