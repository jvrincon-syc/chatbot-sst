import subprocess

from ingestion.ocr.doctor import check_ocr_environment


class FakeCompletedProcess:
    def __init__(self, stdout: str = "") -> None:
        self.stdout = stdout
        self.stderr = ""


def test_ocr_doctor_passes_when_ocrmypdf_tesseract_and_spanish_are_available() -> None:
    def runner(command, **kwargs):
        if command[:2] == ["ocrmypdf", "--version"]:
            return FakeCompletedProcess(stdout="")
        if command[:2] == ["tesseract", "--version"]:
            return FakeCompletedProcess(stdout="tesseract 5.5.2\n")
        if command[:2] == ["tesseract", "--list-langs"]:
            return FakeCompletedProcess(stdout="eng\nspa\n")
        raise AssertionError(command)

    report = check_ocr_environment(runner=runner)

    assert report.ok is True
    assert report.ocrmypdf_available is True
    assert report.ocrmypdf_version == "unknown"
    assert report.tesseract_available is True
    assert report.language_available is True
    assert report.issues == []


def test_ocr_doctor_reports_missing_dependencies_and_language() -> None:
    def runner(command, **kwargs):
        if command[:2] == ["ocrmypdf", "--version"]:
            raise FileNotFoundError("ocrmypdf")
        if command[:2] == ["tesseract", "--version"]:
            return FakeCompletedProcess(stdout="tesseract 5.5.2\n")
        if command[:2] == ["tesseract", "--list-langs"]:
            return FakeCompletedProcess(stdout="eng\nosd\n")
        raise AssertionError(command)

    report = check_ocr_environment(runner=runner)

    assert report.ok is False
    assert "ocrmypdf_unavailable" in report.issues
    assert "tesseract_language_missing" in report.issues


def test_ocr_doctor_reports_tesseract_command_failure() -> None:
    def runner(command, **kwargs):
        if command[:2] == ["ocrmypdf", "--version"]:
            return FakeCompletedProcess(stdout="17.8.0\n")
        raise subprocess.CalledProcessError(returncode=1, cmd=command, stderr="boom")

    report = check_ocr_environment(runner=runner)

    assert report.ok is False
    assert "tesseract_unavailable" in report.issues


def test_ocr_doctor_reads_ocrmypdf_version_from_stderr() -> None:
    class VersionProcess:
        stdout = ""
        stderr = "17.8.0\n"

    def runner(command, **kwargs):
        if command[:2] == ["ocrmypdf", "--version"]:
            return VersionProcess()
        if command[:2] == ["tesseract", "--version"]:
            return FakeCompletedProcess(stdout="tesseract 5.5.2\n")
        if command[:2] == ["tesseract", "--list-langs"]:
            return FakeCompletedProcess(stdout="spa\n")
        raise AssertionError(command)

    report = check_ocr_environment(runner=runner)

    assert report.ocrmypdf_version == "17.8.0"
