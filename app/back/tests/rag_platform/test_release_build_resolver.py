"""Task 2: el resolver de chunking runtime mapea v1/v2 sin degradar en silencio.

Una receta de chunking persistida (``strategy`` + ``sanitized_config`` +
``fingerprint``) debe resolver al ``RuntimeChunkingProfile`` concreto que fijó la
variante. v2 es seleccionable; una receta desconocida o con fingerprint
inconsistente falla cerrado con ``UnsupportedRuntimeChunkingRecipe`` en vez de
caer a v1.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Mapping

import pytest

from rag_platform.domain.errors import UnsupportedRuntimeChunkingRecipe
from rag_platform.domain.identity import IdentityKind, PlatformId
from rag_platform.domain.models import (
    ChunkingProfile,
    ProfileVerificationStatus,
    compute_chunking_profile_fingerprint,
)
from rag_platform.infrastructure.runtime_chunking_profiles import (
    RuntimeChunkingProfileResolver,
)


def _chunking_profile(
    *,
    strategy: str,
    sanitized_config: Mapping[str, object],
    fingerprint: str | None = None,
) -> ChunkingProfile:
    """Construye un perfil de chunking con su fingerprint canónico (o uno dado)."""

    canonical = fingerprint or compute_chunking_profile_fingerprint(
        strategy=strategy, sanitized_config=sanitized_config
    )
    return ChunkingProfile(
        chunking_profile_id=PlatformId(IdentityKind.CHUNKING_PROFILE, "cp_structural"),
        project_id=PlatformId(IdentityKind.PROJECT, "proj_demo"),
        strategy=strategy,
        sanitized_config=dict(sanitized_config),
        fingerprint=canonical,
        status=ProfileVerificationStatus.VERIFIED,
        created_at=datetime.now(timezone.utc),
    )


def test_resuelve_runtime_v2_cuando_receta_es_local_structural_v2() -> None:
    platform_profile = _chunking_profile(
        strategy="local-structural-v2",
        sanitized_config={"include_section_context": True},
    )

    runtime = RuntimeChunkingProfileResolver().resolve(platform_profile)

    assert runtime.profile_id == "local-structural-v2"
    assert runtime.include_section_context is True


def test_resuelve_runtime_v1_cuando_receta_es_structural_sin_contexto() -> None:
    platform_profile = _chunking_profile(strategy="structural", sanitized_config={})

    runtime = RuntimeChunkingProfileResolver().resolve(platform_profile)

    assert runtime.profile_id == "local-structural-v1"
    assert runtime.include_section_context is False


def test_falla_cerrado_cuando_la_receta_es_desconocida() -> None:
    platform_profile = _chunking_profile(
        strategy="local-structural-v99",
        sanitized_config={"include_section_context": True},
    )

    with pytest.raises(UnsupportedRuntimeChunkingRecipe):
        RuntimeChunkingProfileResolver().resolve(platform_profile)


def test_falla_cerrado_cuando_el_fingerprint_no_corresponde_a_la_receta() -> None:
    # Fingerprint válido en forma (64 hex) pero ajeno a la receta persistida: el
    # resolver no confía en un fingerprint que no reproduce la receta canónica.
    tampered = _chunking_profile(
        strategy="local-structural-v2",
        sanitized_config={"include_section_context": True},
        fingerprint="a" * 64,
    )

    with pytest.raises(UnsupportedRuntimeChunkingRecipe):
        RuntimeChunkingProfileResolver().resolve(tampered)
