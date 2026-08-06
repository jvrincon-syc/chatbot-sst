"""Server-controlled consumer scope for activation and rollback.

Until authentication exists, the consumer scope that owns a RetrievalProfile is
decided by the server, never by the request body. Localhost binding is not
authorization: a client that could set the scope could deactivate another
scope's active profile. The scope is read from the environment at the
composition root only; no domain or application module reads it directly.
"""

from __future__ import annotations

from collections.abc import Mapping
import os

from ingestion.schemas.common import StrictModel


class ConsumerScope(StrictModel):
    """The scope a mutation is authorized to act on, resolved server-side."""

    scope_type: str = "chatbot"
    scope_id: str = "sst-default"

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "ConsumerScope":
        """Load the scope from ``SST_CONSUMER_SCOPE_*`` with safe defaults."""

        env = os.environ if environ is None else environ
        scope_type = (env.get("SST_CONSUMER_SCOPE_TYPE") or "chatbot").strip() or "chatbot"
        scope_id = (env.get("SST_CONSUMER_SCOPE_ID") or "sst-default").strip() or "sst-default"
        return cls(scope_type=scope_type, scope_id=scope_id)
