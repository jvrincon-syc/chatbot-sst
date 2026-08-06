from __future__ import annotations

import os
import shutil
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


def _remove_tree(path: Path) -> None:
    """Best-effort recursive delete tolerant of Windows MAX_PATH and ACLs.

    The deep-Windows-path bundle test builds a directory tree whose length
    exceeds MAX_PATH, which a plain ``rmtree`` cannot traverse. On Windows we
    prefix the extended-length ``\\\\?\\`` marker so cleanup succeeds; on every
    platform teardown stays best-effort so it never fails a passing test.
    """

    if not path.exists():
        return

    def _on_error(func, target, _exc_info) -> None:
        try:
            os.chmod(target, 0o700)
            func(target)
        except OSError:
            pass  # Leave residue rather than fail teardown of a passing test.

    target = str(path.resolve())
    if os.name == "nt" and not target.startswith("\\\\?\\"):
        target = "\\\\?\\" + target
    shutil.rmtree(target, onerror=_on_error)


@pytest.fixture
def tmp_path(request: pytest.FixtureRequest) -> Path:
    """Provide a per-test temporary path without pytest's Windows basetemp cleanup.

    Pytest's built-in ``tmp_path`` fixture uses a basetemp implementation that
    is failing in this managed Windows workspace. This fixture keeps the
    contract under test identical while avoiding the ACL issue.

    Isolation contract: each test gets its own **case** directory, and the
    directory handed to the test is a ``work`` child inside it. Traversal and
    symlink-escape tests inspect ``tmp_path.parent`` (the case directory), which
    must never contain residue from a previous run — otherwise a stale
    ``outside.md`` would fail the assertion even though the security control
    correctly raised ``ValueError``. A fresh UUID-named case directory per test,
    cleaned up afterwards, guarantees that.
    """

    root = Path("manual-test-temp") / "pytest-fixtures"
    root.mkdir(parents=True, exist_ok=True)
    # One isolated case directory per test node; `w` is what the test writes
    # into, so its parent (the case dir) is private to this test. Names are kept
    # short on purpose: the deep-Windows-path test builds a MAX_PATH-length tree
    # under tmp_path, so the fixture prefix must stay within the old budget
    # (previously a single `tmp-XXXXXXXX` component).
    case_dir = root / uuid4().hex[:8]
    work_dir = case_dir / "w"
    work_dir.mkdir(parents=True, exist_ok=False)

    request.addfinalizer(lambda: _remove_tree(case_dir))
    return work_dir.resolve()
