from __future__ import annotations

from collections.abc import Mapping

from pydantic import Field

from ingestion.schemas.common import StrictModel


class PostgresIndexingSettings(StrictModel):
    """PostgreSQL settings loaded at the infrastructure boundary."""

    dsn: str | None = Field(default=None, repr=False)

    @property
    def is_configured(self) -> bool:
        """Return whether a PostgreSQL DSN is available."""

        return bool(self.dsn)

    @classmethod
    def from_env(cls, environ: Mapping[str, str]) -> "PostgresIndexingSettings":
        """Load settings from environment without inventing defaults."""

        dsn = environ.get("SST_POSTGRES_DSN")
        return cls(dsn=dsn or None)
