from __future__ import annotations

from scripts.rag_platform.check_pre_phase7_health import run_pre_phase7_health_checks


def test_health_checker_blocks_on_orphans_or_mismatches() -> None:
    connection = RecordingConnection(
        {
            "orphans": [
                {
                    "issue": "release_membership_chunk_bundle_missing",
                    "owner_id": "ragrel_1",
                    "referenced_id": "bundle_missing",
                }
            ],
            "project_mismatches": [
                {
                    "issue": "release_variant_project_mismatch",
                    "owner_id": "ragrel_1",
                    "expected_project_id": "proj_alpha",
                    "actual_project_id": "proj_beta",
                }
            ],
        }
    )

    report = run_pre_phase7_health_checks(connection=connection)

    assert report["status"] == "blocked"
    assert report["checks"]["orphans"]
    assert report["checks"]["project_mismatches"]


def test_health_checker_passes_when_every_category_is_empty() -> None:
    report = run_pre_phase7_health_checks(connection=RecordingConnection({}))

    assert report["status"] == "passed"
    assert set(report["checks"]) == {
        "ownership",
        "orphans",
        "releases",
        "runs",
        "materializations",
        "vectors",
        "project_mismatches",
    }
    assert all(report["checks"][name] == [] for name in report["checks"])


def test_health_checker_is_read_only() -> None:
    connection = RecordingConnection({})

    run_pre_phase7_health_checks(connection=connection)

    assert connection.executed
    assert all(
        " insert " not in statement.lower()
        and " update " not in statement.lower()
        and " delete " not in statement.lower()
        and " alter " not in statement.lower()
        and " drop " not in statement.lower()
        and " truncate " not in statement.lower()
        for statement in connection.executed
    )


class RecordingConnection:
    def __init__(self, rows_by_category: dict[str, list[dict[str, object]]]) -> None:
        self.executed: list[str] = []
        self._rows_by_category = rows_by_category
        self._cursor = RecordingCursor(self)

    def cursor(self) -> "RecordingCursor":
        return self._cursor


class RecordingCursor:
    def __init__(self, connection: RecordingConnection) -> None:
        self._connection = connection
        self._current_rows: list[dict[str, object]] = []

    def __enter__(self) -> "RecordingCursor":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def execute(self, statement: str) -> None:
        self._connection.executed.append(statement)
        category = statement.split("pre_phase7_health:", 1)[1].split("*/", 1)[0].strip()
        self._current_rows = self._connection._rows_by_category.get(category, [])

    def fetchall(self) -> list[dict[str, object]]:
        return list(self._current_rows)
