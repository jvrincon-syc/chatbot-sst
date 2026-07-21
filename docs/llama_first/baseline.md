# Llama-first Baseline

Fecha local: 2026-07-21

## Git

- Rama activa verificada: `llamaparse_experiment`.
- Nota: el plan menciona `llamparse_experiment`; se registra como typo documental.
- HEAD inicial observado: `152aaa59af49216d34422fea40ccb0ba72343801`.
- Merge-base con `main`: `152aaa59af49216d34422fea40ccb0ba72343801`.
- Worktree inicial no estaba limpio. Cambios previos no atribuibles a esta tarea: OCR, PDF corpus golden, frontend package, manifiestos y parte de `secrets.example.env`.

## Entorno

- Python activo para verificacion: `.venv_windows_trabajo`, Python 3.12.10.
- Pip: 26.1.2.
- Pydantic instalado: 2.10.6.
- Corpus `data/docs_raw`: 46 Markdown y 9 PDF.

## Comandos

### Oficial por npm

`npm.cmd run test:ingestion`

- Resultado inicial: fallaba antes de pytest.
- Motivo inicial: el wrapper `npm run python -- -m pytest ...` pasaba `-m` a `node -e`; Node respondia `node: bad option: -m`.
- Resultado despues de correccion del wrapper: 263 passed, 3 skipped.

`npm.cmd run ingestion:validate`

- Resultado inicial: fallaba por el mismo wrapper `python` de `package.json`.
- Resultado despues de correccion del wrapper: passed: 0 error(s), manifiesto `data/docs_normalized/_manifests/validation_manual.json`.

### Equivalente directo con Python 3.12

`.\\.venv_windows_trabajo\\Scripts\\python.exe -m pytest app/back/tests/ingestion -v`

- Resultado: 260 passed, 3 skipped.

`.\\.venv_windows_trabajo\\Scripts\\python.exe scripts\\ingestion\\validate_normalized.py`

- Resultado: passed: 0 error(s), manifiesto `data/docs_normalized/_manifests/validation_manual.json`.

## Contratos preservados

- `ReadResult`, readers locales y pipeline oficial no se conectaron a Llama Cloud en esta fase.
- `BundleWriter`, schemas 2.0, inventory, validation y review policy siguen como compatibilidad interna.
- Los modelos/puertos nuevos son neutrales al proveedor y no importan SDKs externos.

## Gaps

- Fase 0.5 smoke cloud esta bloqueado hasta autorizacion de documento, region, retencion/eliminacion y presupuesto.
- Resolver por ADR el bloqueo de LlamaIndex/Postgres con `pydantic<2.11`.
