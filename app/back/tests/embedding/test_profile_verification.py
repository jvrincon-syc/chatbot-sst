from __future__ import annotations

from embedding.application.engine_registry import DefaultEmbeddingEngineRegistry
from embedding.application.profile_verification import (
    ProfileVerificationRequest,
    VerifyEmbeddingProfileCompatibilityUseCase,
)
from embedding.infrastructure.in_memory.repositories import (
    InMemoryEmbeddingProfileRepository,
    InMemoryIndexingTargetRepository,
    InMemoryReadinessCheckRepository,
)

from pipeline_fixtures import MOCK_REVISION, build_profile, build_target


def _use_case(profile, *, targets=None, allow_mock=True):
    profiles = InMemoryEmbeddingProfileRepository([profile])
    checks = InMemoryReadinessCheckRepository()
    use_case = VerifyEmbeddingProfileCompatibilityUseCase(
        profiles=profiles,
        registry=DefaultEmbeddingEngineRegistry(environ={}, allow_mock=allow_mock),
        targets=targets if targets is not None else InMemoryIndexingTargetRepository([build_target()]),
        readiness_checks=checks,
    )
    return use_case, profiles, checks


def test_habilita_el_perfil_cuando_todas_las_comprobaciones_pasan() -> None:
    blocked = build_profile(
        compatibility_status="compatibility_not_proven",
        document_enabled=False,
        query_enabled=False,
        configuration_fingerprint=None,
    )
    use_case, profiles, checks = _use_case(blocked)

    result = use_case.execute(ProfileVerificationRequest(profile_id=blocked.profile_id))

    assert result.passed is True
    promoted = profiles.get(blocked.profile_id)
    assert promoted.compatibility_status == "verified"
    assert promoted.document_enabled is True
    assert promoted.query_enabled is True
    assert promoted.configuration_fingerprint == promoted.expected_fingerprint().value
    assert checks.latest(check_kind="embedding_profile_verification", subject_id=blocked.profile_id).status == "passed"


def test_bloquea_el_perfil_cuando_la_revision_es_desconocida() -> None:
    legacy = build_profile(
        model_revision="unknown_revision",
        compatibility_status="compatibility_not_proven",
        document_enabled=False,
        query_enabled=False,
        configuration_fingerprint=None,
    )
    use_case, profiles, checks = _use_case(legacy)

    result = use_case.execute(ProfileVerificationRequest(profile_id=legacy.profile_id))

    assert result.passed is False
    assert "model_revision_matches" in {check.name for check in result.failures()}
    assert profiles.get(legacy.profile_id).document_enabled is False
    assert checks.latest(check_kind="embedding_profile_verification", subject_id=legacy.profile_id).status == "failed"


def test_bloquea_el_perfil_cuando_la_revision_observada_no_coincide() -> None:
    profile = build_profile(
        model_revision="another-revision",
        configuration_fingerprint=None,
        compatibility_status="compatibility_not_proven",
        document_enabled=False,
        query_enabled=False,
    )
    use_case, profiles, _ = _use_case(profile)

    result = use_case.execute(ProfileVerificationRequest(profile_id=profile.profile_id))

    assert result.passed is False
    assert result.revision_source == "engine_observed"
    assert profiles.get(profile.profile_id).compatibility_status != "verified"


def test_bloquea_el_perfil_cuando_el_target_usa_otra_metrica() -> None:
    profile = build_profile(configuration_fingerprint=None)
    targets = InMemoryIndexingTargetRepository([build_target(distance_ops="vector_l2_ops")])
    use_case, profiles, _ = _use_case(profile, targets=targets)

    result = use_case.execute(ProfileVerificationRequest(profile_id=profile.profile_id))

    assert result.passed is False
    assert "distance_metric_matches_target" in {check.name for check in result.failures()}


def test_bloquea_el_perfil_cuando_el_fingerprint_almacenado_difiere() -> None:
    profile = build_profile(configuration_fingerprint="f" * 64)
    use_case, profiles, _ = _use_case(profile)

    result = use_case.execute(ProfileVerificationRequest(profile_id=profile.profile_id))

    assert result.passed is False
    assert "configuration_fingerprint_matches" in {check.name for check in result.failures()}


def test_bloquea_el_perfil_cuando_el_motor_no_esta_disponible() -> None:
    profile = build_profile(configuration_fingerprint=None)
    use_case, profiles, _ = _use_case(profile, allow_mock=False)

    result = use_case.execute(ProfileVerificationRequest(profile_id=profile.profile_id))

    assert result.passed is False
    assert "engine_resolved" in {check.name for check in result.failures()}


def test_acepta_una_atestacion_explicita_cuando_el_motor_no_expone_revision() -> None:
    profile = build_profile(
        provider="voyage",
        model="voyage-4",
        model_revision="voyage-4-2026-05",
        normalization="provider_normalized",
        vector_table="idx_vec_local_voyage_4_v1",
        default_indexing_target_id="target-idx-vec-local-voyage-4-v1",
        configuration_fingerprint=None,
        compatibility_status="compatibility_not_proven",
        document_enabled=False,
        query_enabled=False,
    )
    targets = InMemoryIndexingTargetRepository(
        [
            build_target(
                indexing_target_id="target-idx-vec-local-voyage-4-v1",
                vector_table="idx_vec_local_voyage_4_v1",
            )
        ]
    )
    use_case, profiles, _ = _use_case(profile, targets=targets)

    result = use_case.execute(
        ProfileVerificationRequest(
            profile_id=profile.profile_id,
            attested_model_revision="voyage-4-2026-05",
        )
    )

    assert result.passed is True
    assert result.revision_source == "operator_attestation"


def test_ignora_el_perfil_cuando_no_tiene_target_por_defecto() -> None:
    profile = build_profile(default_indexing_target_id=None, configuration_fingerprint=None)
    use_case, _, _ = _use_case(profile)

    result = use_case.execute(ProfileVerificationRequest(profile_id=profile.profile_id))

    assert result.passed is False
    assert "distance_metric_matches_target" in {check.name for check in result.failures()}


def test_no_expone_credenciales_ni_rutas_en_el_reporte() -> None:
    profile = build_profile(configuration_fingerprint=None)
    use_case, _, checks = _use_case(profile)

    use_case.execute(ProfileVerificationRequest(profile_id=profile.profile_id))

    report = checks.latest(check_kind="embedding_profile_verification", subject_id=profile.profile_id)
    serialized = str(report.report)
    assert "api_key" not in serialized.lower()
    assert "/" not in serialized.replace("BAAI/", "")
