"""Preflight fail-closed de la etapa normalize del CLI ``run_project_ingestion.py``.

``resolve_platform_contexts_or_raise`` resuelve la identidad de plataforma de
*todos* los documentos seleccionados antes de leer/escribir/promover ninguno. Un
documento seleccionado sin revisión registrada aborta el normalize completo con
``platform_identity_incomplete`` (Task 1), en vez del comportamiento legacy
fail-open que normalizaba sin identidad. Pieza pura: sin Postgres ni motor de
normalización.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from ingestion.application.platform_metadata import (
    PlatformContextResolutionError,
    resolve_platform_contexts_or_raise,
)
from rag_platform.application.platform_access import PlatformActor
from rag_platform.application.project_normalization_service import (
    NormalizeProjectDocumentsUseCase,
    ProjectNormalizeOutcome,
)
from rag_platform.domain.errors import (
    RevisionProjectMismatch,
    VariantProjectMismatch,
)
from rag_platform.domain.identity import IdentityKind, PlatformId
from rag_platform.infrastructure.in_memory.repositories import AllowAllAccessPolicy


class _Id:
    def __init__(self, value: str) -> None:
        self.value = value


class _Revision:
    """Stub de ``SourceDocumentRevision`` con solo los campos que lee el preflight."""

    def __init__(self, *, logical: str, revision: str) -> None:
        self.logical_document_id = _Id(logical)
        self.source_document_revision_id = _Id(revision)


class _Record:
    """Stub de ``InventoryRecord``: el preflight solo lee ``source_relpath``."""

    def __init__(self, source_relpath: str) -> None:
        self.source_relpath = source_relpath


_FP = "a" * 64
_RECIPE = "b" * 64


def test_preflight_falla_si_un_record_seleccionado_no_tiene_revision() -> None:
    records = [_Record("a/manual.pdf"), _Record("b/manual.pdf")]
    revisions = {"a/manual.pdf": _Revision(logical="sdoc_a", revision="srev_a")}

    with pytest.raises(PlatformContextResolutionError, match="b/manual.pdf"):
        resolve_platform_contexts_or_raise(
            records=records,
            revisions_by_relpath=revisions,
            project_id="proj_demo",
            processing_profile_id="pp_local",
            processing_profile_fingerprint=_FP,
            rag_variant_id="ragv_demo",
            semantic_recipe_fingerprint=_RECIPE,
        )


def test_preflight_mapea_todas_las_revisiones_registradas() -> None:
    records = [_Record("general/manual.md")]
    revisions = {"general/manual.md": _Revision(logical="sdoc_x", revision="srev_x")}

    resolved = resolve_platform_contexts_or_raise(
        records=records,
        revisions_by_relpath=revisions,
        project_id="proj_sst-general",
        processing_profile_id="pp_local",
        processing_profile_fingerprint=_FP,
        rag_variant_id="ragv_bge",
        semantic_recipe_fingerprint=_RECIPE,
    )

    context = resolved["general/manual.md"]
    assert context.project_id == "proj_sst-general"
    assert context.source_document_id == "sdoc_x"
    assert context.source_document_revision_id == "srev_x"
    assert context.processing_profile_id == "pp_local"
    assert context.processing_profile_fingerprint == _FP
    assert context.normalized_document_id.startswith("ndoc_")
    assert context.rag_variant_id == "ragv_bge"
    assert context.semantic_recipe_fingerprint == _RECIPE


# --------------------------------------------------------------------------- #
# NormalizeProjectDocumentsUseCase: orquestación pura (motor tras el puerto)   #
# --------------------------------------------------------------------------- #


def _pid(kind: IdentityKind, value: str) -> PlatformId:
    return PlatformId(kind=kind, value=value)


_PROJ = _pid(IdentityKind.PROJECT, "proj_demo")
_OTHER = _pid(IdentityKind.PROJECT, "proj_otro")
_VARIANT = _pid(IdentityKind.RAG_VARIANT, "ragv_demo")
_PROFILE = _pid(IdentityKind.PROCESSING_PROFILE, "pp_local")


@dataclass
class _StubProject:
    project_id: PlatformId


@dataclass
class _StubVariant:
    project_id: PlatformId
    rag_variant_id: PlatformId
    processing_profile_id: PlatformId
    semantic_recipe_fingerprint: str


@dataclass
class _StubProfile:
    fingerprint: str


@dataclass
class _StubRevision:
    project_id: PlatformId
    source_document_revision_id: PlatformId
    logical_document_id: PlatformId
    source_relpath: str


class _Repo:
    def __init__(self, value):
        self._value = value


class _Projects(_Repo):
    def get(self, project_id):
        return self._value


class _Variants(_Repo):
    def get(self, rag_variant_id):
        return self._value


class _Profiles(_Repo):
    def get(self, processing_profile_id):
        return self._value


class _Docs:
    def __init__(self, revisions):
        self._by_id = {r.source_document_revision_id.value: r for r in revisions}

    def get_revision(self, revision_id):
        return self._by_id[revision_id.value]


class _RecordingNormalizer:
    def __init__(self):
        self.captured = None

    def normalize(self, **kwargs):
        self.captured = kwargs
        return ProjectNormalizeOutcome(
            rag_variant_id=kwargs["rag_variant_id"],
            processed=len(kwargs["revisions"]),
            needs_review=0,
            skipped=0,
            failed=0,
            revision_ids=tuple(
                r.source_document_revision_id.value for r in kwargs["revisions"]
            ),
        )


def _variant(*, project: PlatformId = _PROJ) -> _StubVariant:
    return _StubVariant(
        project_id=project,
        rag_variant_id=_VARIANT,
        processing_profile_id=_PROFILE,
        semantic_recipe_fingerprint=_RECIPE,
    )


def _revision(*, project: PlatformId = _PROJ, rid: str = "srev_a") -> _StubRevision:
    return _StubRevision(
        project_id=project,
        source_document_revision_id=_pid(
            IdentityKind.SOURCE_DOCUMENT_REVISION, rid
        ),
        logical_document_id=_pid(IdentityKind.SOURCE_DOCUMENT, "sdoc_a"),
        source_relpath="general/manual.md",
    )


def _use_case(*, variant, revisions, normalizer) -> NormalizeProjectDocumentsUseCase:
    return NormalizeProjectDocumentsUseCase(
        projects=_Projects(_StubProject(project_id=_PROJ)),
        documents=_Docs(revisions),
        variants=_Variants(variant),
        processing_profiles=_Profiles(_StubProfile(fingerprint=_FP)),
        normalizer=normalizer,
        access_policy=AllowAllAccessPolicy(),
    )


_ACTOR = PlatformActor(actor_id="op-1", project_scope=None)


def test_normalize_delega_con_perfil_y_revisiones_resueltas() -> None:
    normalizer = _RecordingNormalizer()
    use_case = _use_case(
        variant=_variant(), revisions=[_revision()], normalizer=normalizer
    )

    outcome = use_case.execute(
        project_id=_PROJ,
        rag_variant_id=_VARIANT,
        document_revision_ids=["srev_a"],
        force=False,
        actor=_ACTOR,
    )

    assert outcome.processed == 1
    assert outcome.revision_ids == ("srev_a",)
    # El fingerprint del perfil (autoridad de la receta física) llega al motor.
    assert normalizer.captured["processing_profile_fingerprint"] == _FP
    assert normalizer.captured["rag_variant_id"] == "ragv_demo"
    assert len(normalizer.captured["revisions"]) == 1


def test_normalize_variante_de_otro_proyecto_falla_cerrado() -> None:
    normalizer = _RecordingNormalizer()
    use_case = _use_case(
        variant=_variant(project=_OTHER),
        revisions=[_revision()],
        normalizer=normalizer,
    )

    with pytest.raises(VariantProjectMismatch):
        use_case.execute(
            project_id=_PROJ,
            rag_variant_id=_VARIANT,
            document_revision_ids=["srev_a"],
            force=False,
            actor=_ACTOR,
        )
    assert normalizer.captured is None  # nunca toca el motor


def test_normalize_revision_de_otro_proyecto_falla_cerrado() -> None:
    normalizer = _RecordingNormalizer()
    use_case = _use_case(
        variant=_variant(),
        revisions=[_revision(project=_OTHER)],
        normalizer=normalizer,
    )

    with pytest.raises(RevisionProjectMismatch):
        use_case.execute(
            project_id=_PROJ,
            rag_variant_id=_VARIANT,
            document_revision_ids=["srev_a"],
            force=False,
            actor=_ACTOR,
        )
    assert normalizer.captured is None
