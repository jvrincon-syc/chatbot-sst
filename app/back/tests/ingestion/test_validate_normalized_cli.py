from __future__ import annotations

import json

import pytest

from ingestion.schemas.artifacts import ValidationCheck, ValidationReport
from scripts.ingestion import validate_normalized


def _report(
    *,
    status: str,
    documents_checked: int = 55,
    errors: int = 0,
    warnings: int = 0,
) -> ValidationReport:
    return ValidationReport(
        schema_version="2.0",
        status=status,
        documents_checked=documents_checked,
        errors=errors,
        warnings=warnings,
        checks=[ValidationCheck(check="structure", status="passed")],
    )


@pytest.fixture(autouse=True)
def _isolate_cli(monkeypatch) -> None:
    """Keep the CLI hermetic: never read the real `secrets.env` from a test."""

    monkeypatch.setattr(validate_normalized, "load_secrets_env", lambda _path: None)


def _run(monkeypatch, tmp_path, report_or_error) -> int:
    output = tmp_path / "validation_test.json"

    def _fake_validate(*_args, **_kwargs) -> ValidationReport:
        if isinstance(report_or_error, Exception):
            raise report_or_error
        return report_or_error

    monkeypatch.setattr(validate_normalized, "validate_normalized_tree", _fake_validate)
    monkeypatch.setattr(
        "sys.argv",
        [
            "validate_normalized.py",
            "--docs-normalized",
            str(tmp_path / "docs_normalized"),
            "--output",
            str(output),
            "--run-id",
            "test",
        ],
    )
    return validate_normalized.main()


def test_cli_reporta_conteos_enteros_y_sale_cero_cuando_la_validacion_pasa(
    tmp_path, monkeypatch, capsys
) -> None:
    """Regression: the CLI used to call len() on ValidationReport.errors (an int)."""

    exit_code = _run(monkeypatch, tmp_path, _report(status="passed"))

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["status"] == "passed"
    assert payload["documents_checked"] == 55
    assert payload["error_count"] == 0
    assert payload["warning_count"] == 0


def test_cli_sale_uno_cuando_la_validacion_falla(tmp_path, monkeypatch, capsys) -> None:
    exit_code = _run(
        monkeypatch, tmp_path, _report(status="failed", errors=3, warnings=2)
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload["status"] == "failed"
    assert payload["error_count"] == 3
    assert payload["warning_count"] == 2


def test_cli_sale_dos_sin_traceback_cuando_la_ejecucion_falla(
    tmp_path, monkeypatch, capsys
) -> None:
    exit_code = _run(monkeypatch, tmp_path, RuntimeError("dsn=postgres://user:pass@host/db"))

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 2
    assert payload["status"] == "error"
    assert payload["error_type"] == "RuntimeError"
    # The boundary reports the exception class only: no message, no traceback.
    assert "postgres://" not in captured.out


def test_cli_escribe_el_reporte_en_la_ruta_indicada(tmp_path, monkeypatch, capsys) -> None:
    exit_code = _run(monkeypatch, tmp_path, _report(status="passed"))
    capsys.readouterr()

    written = json.loads((tmp_path / "validation_test.json").read_text(encoding="utf-8"))
    assert exit_code == 0
    assert written["status"] == "passed"
    assert written["errors"] == 0
    assert written["documents_checked"] == 55
