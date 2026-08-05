from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import pytest


def pytest_configure() -> None:
    """Disable Windows basetemp symlink cleanup when the workspace ACL blocks it.

    The integration suites in this workspace execute correctly, but pytest's
    dead-symlink cleanup can fail on Windows-managed folders with
    PermissionError during session finish. This hook keeps the test run focused
    on the application contract instead of the temporary-directory teardown.
    """

    if os.environ.get("CHATBOT_SST_DISABLE_PYTEST_SYMLINK_CLEANUP", "1") != "1":
        return

    try:
        import _pytest.pathlib as pytest_pathlib
        import _pytest.tmpdir as pytest_tmpdir
    except Exception:
        return

    def _noop_cleanup(*_args, **_kwargs) -> None:
        return None

    pytest_pathlib.cleanup_dead_symlinks = _noop_cleanup
    pytest_tmpdir.cleanup_dead_symlinks = _noop_cleanup


@pytest.fixture
def tmp_path() -> Path:
    """Provide a writable temporary path without pytest's Windows basetemp cleanup.

    Pytest's built-in ``tmp_path`` fixture uses a basetemp implementation that
    is failing in this managed Windows workspace. A plain ``mkdtemp`` directory
    keeps the contract under test identical while avoiding the ACL issue.
    """

    root = Path("manual-test-temp") / "pytest-fixtures"
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"tmp-{uuid4().hex[:8]}"
    path.mkdir(parents=True, exist_ok=False)
    return path.resolve()
