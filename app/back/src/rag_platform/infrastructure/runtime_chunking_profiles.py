"""Resolución fail-closed de una receta de chunking persistida a su runtime.

Una ``ChunkingProfile`` de plataforma persiste ``strategy`` + ``sanitized_config``
+ ``fingerprint``. El build de release necesita el ``RuntimeChunkingProfile``
concreto (política de tokens/overlap y ``include_section_context``) que esa receta
selecciona. Este resolver hace ese mapeo **sin degradar** recetas desconocidas a
v1: si la estrategia/configuración no está soportada, o si el fingerprint no
corresponde a la receta canónica, falla cerrado con
``UnsupportedRuntimeChunkingRecipe``.

Vive en infraestructura porque cruza dos dominios (``rag_platform`` y ``chunking``)
para traducir una receta persistida a un objeto de runtime; el dominio de
plataforma no conoce el runtime de chunking.
"""

from __future__ import annotations

from chunking.domain.models import ChunkingProfile as RuntimeChunkingProfile
from rag_platform.domain.errors import UnsupportedRuntimeChunkingRecipe
from rag_platform.domain.models import (
    ChunkingProfile,
    compute_chunking_profile_fingerprint,
)


class RuntimeChunkingProfileResolver:
    """Mapea una ``ChunkingProfile`` persistida a su ``RuntimeChunkingProfile``.

    v1 (``structural`` sin contexto de sección) y v2 (``local-structural-v2`` con
    ``include_section_context``) son las únicas recetas seleccionables. Cualquier
    otra combinación es fail-closed.
    """

    #: Recetas que resuelven a la política v1 (sin contexto de sección). Se
    #: aceptan los alias históricos de la estrategia para no romper perfiles ya
    #: persistidos, todos con ``include_section_context`` en falso.
    _V1_KEYS = frozenset(
        {
            ("structural", False),
            ("local-structural", False),
            ("local-structural-v1", False),
            ("local_structural_v1", False),
        }
    )
    #: Recetas que resuelven a la política v2 (contexto de sección habilitado).
    _V2_KEYS = frozenset(
        {
            ("local-structural-v2", True),
            ("local_structural_v2", True),
        }
    )

    def resolve(self, profile: ChunkingProfile) -> RuntimeChunkingProfile:
        """Resuelve el runtime de una receta persistida o falla cerrado.

        Args:
            profile: Perfil de chunking de plataforma persistido.

        Returns:
            El ``RuntimeChunkingProfile`` concreto que la receta selecciona.

        Raises:
            UnsupportedRuntimeChunkingRecipe: Si el fingerprint no corresponde a
                la receta canónica, o si la estrategia/configuración no está
                soportada por el runtime.
        """

        expected_fingerprint = compute_chunking_profile_fingerprint(
            strategy=profile.strategy,
            sanitized_config=profile.sanitized_config,
        )
        if profile.fingerprint != expected_fingerprint:
            raise UnsupportedRuntimeChunkingRecipe(
                f"chunking profile {profile.chunking_profile_id.value!r} fingerprint "
                "does not match its canonical recipe; refusing to run a tampered recipe"
            )

        key = (
            profile.strategy,
            bool(profile.sanitized_config.get("include_section_context")),
        )
        if key in self._V1_KEYS:
            return RuntimeChunkingProfile.local_structural_v1()
        if key in self._V2_KEYS:
            return RuntimeChunkingProfile.local_structural_v2()

        raise UnsupportedRuntimeChunkingRecipe(
            "unsupported runtime chunking recipe: "
            f"strategy={profile.strategy!r} "
            f"include_section_context={key[1]!r}"
        )
