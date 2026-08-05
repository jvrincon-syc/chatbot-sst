from __future__ import annotations

from indexing.application.repositories import ProfileRegistry
from indexing.domain.profiles import IngestionOrigin, ResolvedIndexingProfile


class ProfileLaneMismatchError(ValueError):
    """The selected embedding profile is not valid for this ingestion lane."""


class InactiveProfileError(ValueError):
    """The selected profile exists but is not active."""


class EmbeddingProfileOrchestrator:
    """Resolve and validate indexing profiles before durable writes."""

    def __init__(self, registry: ProfileRegistry) -> None:
        self._registry = registry

    def resolve(
        self,
        *,
        profile_id: str,
        ingestion_origin: IngestionOrigin,
    ) -> ResolvedIndexingProfile:
        """Return an active profile only when it matches the normalized lane."""

        profile = self._registry.get(profile_id)
        if not profile.active:
            raise InactiveProfileError(f"profile is inactive: {profile_id}")
        if profile.ingestion_origin != ingestion_origin:
            raise ProfileLaneMismatchError(
                "profile "
                f"{profile_id} belongs to {profile.ingestion_origin}, "
                f"not {ingestion_origin}"
            )
        return profile
