from __future__ import annotations

import os

import pytest


pytestmark = pytest.mark.postgres_live


def test_postgres_live_requires_explicit_dsn() -> None:
    if not os.environ.get("SST_POSTGRES_DSN"):
        pytest.skip("SST_POSTGRES_DSN is required for live PostgreSQL checks")

    pytest.importorskip("psycopg2")
