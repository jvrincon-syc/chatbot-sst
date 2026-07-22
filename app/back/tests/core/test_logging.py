import json
import logging

import pytest

from core.logging.logger import get_logger


def test_core_logging_package_is_included_cuando_backend_distribution_is_built() -> None:
    from setuptools import find_packages

    packages = set(find_packages("app/back/src"))

    assert "core" in packages
    assert "core.logging" in packages


def test_logger_emits_structured_info_to_stdout_cuando_context_is_provided(
    capsys: pytest.CaptureFixture[str],
) -> None:
    logger = get_logger("tests.core.logging.stdout")

    logger.info(
        "Processing document",
        extra={
            "run_id": "run_test",
            "document_id": "doc_123",
            "stage": "reading",
            "status": "started",
        },
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["level"] == "INFO"
    assert payload["message"] == "Processing document"
    assert payload["run_id"] == "run_test"
    assert payload["document_id"] == "doc_123"
    assert payload["stage"] == "reading"
    assert payload["status"] == "started"
    assert captured.err == ""
    assert logger.propagate is False
    assert any(handler.level <= logging.INFO for handler in logger.handlers)
