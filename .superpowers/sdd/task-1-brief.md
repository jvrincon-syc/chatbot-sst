## Tarea 1 — Definir contratos, perfil e invariantes

**Archivos:**

- Crear: `app/back/src/chunking/domain/models.py`
- Crear: `app/back/src/chunking/domain/policies.py`
- Crear: `app/back/src/chunking/domain/enums.py`
- Crear: `app/back/src/chunking/domain/invariants.py`
- Crear: `app/back/src/chunking/domain/errors.py`
- Crear: `app/back/src/chunking/application/ports.py`
- Crear: `docs/chunking/chunking_policy.md`

**Interfaces:**

- Consume: ningún SDK, filesystem o modelo de FastAPI.
- Produce: `NormalizedDocumentBundle`, `StructuralBlock`, `SourceSpan`, `ParentChunk`, `ChildChunk`, `ChunkBundle`, `ChunkingProfile`, `ChunkingRun` y puertos pequeños.

- [ ] Escribir tests de modelos e invariantes antes de la implementación.
- [ ] Implementar el perfil `local-structural-v1`.
- [ ] Configurar `child_min_tokens=250`, `child_target_tokens=350` y `child_max_tokens=450`.
- [ ] Configurar `overlap_ratio=0.12`, `overlap_min_tokens=30` y `overlap_max_tokens=60`.
- [ ] Validar que el máximo de 450 tokens incluya el overlap.
- [ ] Validar la coherencia del perfil: mínimo `<=` objetivo `<=` máximo, ratio entre `0` y `1`, y overlap mínimo `<=` overlap máximo `<` tamaño del child.
- [ ] Permitir overlap `0` únicamente para las excepciones semánticas definidas por la política.
- [ ] Rechazar child sin parent, rangos negativos, chunks vacíos y páginas invertidas.
- [ ] Definir IDs por contenido, perfil y posición estructural estable.
- [ ] Mantener Pydantic únicamente en schemas de entrada/salida.

**Pruebas mínimas:**

```text
test_rechaza_child_cuando_parent_no_existe
test_rechaza_overlap_cuando_supera_el_child
test_rechaza_perfil_cuando_minimo_objetivo_y_maximo_son_incoherentes
test_rechaza_perfil_cuando_limites_de_overlap_son_incoherentes
test_perfil_local_define_ratio_y_limites_de_overlap
test_rechaza_page_range_cuando_end_es_menor
test_genera_ids_iguales_cuando_entrada_y_perfil_no_cambian
test_cambia_fingerprint_cuando_cambia_overlap
```

**Verificación:**

```bash
python -m pytest app/back/tests/chunking/unit/test_domain_models.py -q
```

**Commit sugerido:**

```text
feat(chunking): add local chunking contracts and invariants
```

## Tarea 2 — Consumir bundles normalizados sin modificar Fase 1
