## Tarea 2 — Consumir bundles normalizados sin modificar Fase 1

**Archivos:**

- Crear: `app/back/src/chunking/infrastructure/schema2_source.py`
- Crear: `app/back/src/chunking/application/source_span_resolver.py`
- Crear: `app/back/tests/chunking/integration/test_schema2_source.py`

**Interfaces:**

- Consume: `.md`, `.metadata.json`, `.pages.json`, `.tables.json`, `.forms.json` y `.ocr.json`.
- Produce: `NormalizedDocumentBundle` validado y spans con procedencia.

- [ ] Escribir tests con sidecars completos, incompletos y ausentes.
- [ ] Validar consistencia de `document_id`, hashes y rutas relativas.
- [ ] No depender de `pages.json.blocks`.
- [ ] Resolver páginas mediante marcadores y alineación contra `pages.json`.
- [ ] Emitir `PAGE_TRACE_UNRESOLVED` cuando no exista resolución segura.
- [ ] No inventar páginas, confianza OCR ni bloques.
- [ ] Rechazar path traversal y documentos fuera de `docs_normalized`.
- [ ] Conservar literalmente cifras, códigos, fechas y nombres.

**Verificación:**

```bash
python -m pytest app/back/tests/chunking/integration/test_schema2_source.py -q
```

**Commit sugerido:**

```text
feat(chunking): consume normalized schema2 bundles
```

## Tarea 3 — Construir bloques estructurales por señales múltiples
