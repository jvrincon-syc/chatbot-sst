"""Task 2: el seeder deriva la receta de chunking v1/v2 sin colisionar identidades.

Estas pruebas cubren la lógica pura del seeder sin tocar PostgreSQL (regla de
unit tests sin red): derivación de slug/config/fingerprint desde la estrategia,
paridad byte a byte del fingerprint v1 con el legacy, y la guarda de conflicto de
receta bajo un mismo ``chunking_profile_id``.
"""

from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path

import pytest

from rag_platform.domain.errors import ChunkingProfileSeedConflict
from rag_platform.domain.models import compute_chunking_profile_fingerprint

_ROOT = Path(__file__).resolve().parents[4]


def _load(module_name: str, relpath: str):
    spec = importlib.util.spec_from_file_location(module_name, _ROOT / relpath)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    # Registrar antes de exec: dataclasses/typing resuelven anotaciones-string vía
    # sys.modules[cls.__module__]; sin esto el @dataclass del módulo falla al cargar.
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


seed = _load("seed_project_cli", "scripts/rag_platform/seed_project.py")


def _legacy_seed_chunking_fingerprint(*, strategy: str) -> str:
    """Réplica exacta del fingerprint legacy: ``_fingerprint("chunking", strategy)``."""

    return hashlib.sha256(f"chunking\x1f{strategy}".encode("utf-8")).hexdigest()


def test_compute_chunking_profile_fingerprint_v1_matches_legacy_seed() -> None:
    legacy = _legacy_seed_chunking_fingerprint(strategy="structural")

    canonical = compute_chunking_profile_fingerprint(
        strategy="structural",
        sanitized_config={},
    )

    assert canonical == legacy


def test_deriva_slug_y_config_v1_cuando_estrategia_es_structural_sin_slug() -> None:
    recipe = seed._resolve_chunking_recipe(strategy="structural", slug=None)

    assert recipe.effective_slug == "structural"
    assert recipe.chunking_id == "cp_structural"
    assert recipe.sanitized_config == {}
    assert recipe.fingerprint == _legacy_seed_chunking_fingerprint(strategy="structural")


def test_deriva_slug_v2_cuando_estrategia_es_v2_sin_slug() -> None:
    recipe = seed._resolve_chunking_recipe(
        strategy="local-structural-v2", slug=None
    )

    assert recipe.effective_slug == "structural-v2"
    assert recipe.chunking_id == "cp_structural-v2"
    assert recipe.sanitized_config == {"include_section_context": True}
    assert recipe.fingerprint == compute_chunking_profile_fingerprint(
        strategy="local-structural-v2",
        sanitized_config={"include_section_context": True},
    )


def test_v2_no_reutiliza_el_id_de_v1() -> None:
    v1 = seed._resolve_chunking_recipe(strategy="structural", slug="structural")
    v2 = seed._resolve_chunking_recipe(
        strategy="local-structural-v2", slug="structural-v2"
    )

    assert v1.chunking_id == "cp_structural"
    assert v2.chunking_id == "cp_structural-v2"
    assert v1.chunking_id != v2.chunking_id
    assert v1.fingerprint != v2.fingerprint


def test_preserva_el_slug_explicito_cuando_se_provee() -> None:
    recipe = seed._resolve_chunking_recipe(
        strategy="local-structural-v2", slug="mi-slug"
    )

    assert recipe.effective_slug == "mi-slug"
    assert recipe.chunking_id == "cp_mi-slug"


def test_inserta_cuando_no_existe_perfil_previo() -> None:
    recipe = seed._resolve_chunking_recipe(strategy="structural", slug="structural")

    must_insert = seed._ensure_recipe_matches_existing(None, recipe)

    assert must_insert is True


def test_es_idempotente_cuando_la_receta_persistida_es_identica() -> None:
    recipe = seed._resolve_chunking_recipe(strategy="structural", slug="structural")
    existing = (recipe.strategy, dict(recipe.sanitized_config), recipe.fingerprint)

    must_insert = seed._ensure_recipe_matches_existing(existing, recipe)

    assert must_insert is False


def test_falla_cerrado_cuando_el_id_existe_con_otra_receta() -> None:
    recipe = seed._resolve_chunking_recipe(strategy="structural", slug="structural")
    existing = (
        "local-structural-v2",
        {"include_section_context": True},
        compute_chunking_profile_fingerprint(
            strategy="local-structural-v2",
            sanitized_config={"include_section_context": True},
        ),
    )

    with pytest.raises(ChunkingProfileSeedConflict):
        seed._ensure_recipe_matches_existing(existing, recipe)
