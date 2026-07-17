from ingestion.fingerprint import processing_fingerprint, validation_fingerprint


def test_processing_fingerprint_ignores_absolute_roots_and_secrets() -> None:
    first = processing_fingerprint(
        {
            "docs_raw": "/tmp/a/raw",
            "docs_normalized": "/tmp/a/normalized",
            "pipeline_version": "2.0",
            "ocr": {"language": "spa", "api_token": "secret-a"},
        },
        {"tesseract": "5.5.2"},
    )
    second = processing_fingerprint(
        {
            "docs_raw": "/mnt/moved/raw",
            "docs_normalized": "/mnt/moved/normalized",
            "pipeline_version": "2.0",
            "ocr": {"language": "spa", "api_token": "secret-b"},
        },
        {"tesseract": "5.5.2"},
    )

    assert first == second


def test_processing_fingerprint_changes_for_semantic_configuration() -> None:
    base = processing_fingerprint({"pipeline_version": "2.0", "ocr": {"language": "spa"}}, {})
    changed = processing_fingerprint({"pipeline_version": "2.1", "ocr": {"language": "spa"}}, {})

    assert base != changed


def test_validation_fingerprint_changes_with_golden_hash() -> None:
    assert validation_fingerprint("v1", "abc") != validation_fingerprint("v1", "def")
