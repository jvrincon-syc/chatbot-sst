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
        if command[:2] == ["gs", "--version"]:
            return FakeCompletedProcess(stdout="10.03.0\n")
        raise AssertionError(command)

    report = check_ocr_environment(runner=runner, module_available=lambda name: True)

    assert report.ok is True
    assert report.ocrmypdf_available is True
    assert report.ocrmypdf_version == "unknown"
    assert report.tesseract_available is True
    assert report.language_available is True
    assert report.pdfplumber_available is True
    assert report.pdfium_available is True
    assert report.opencv_available is True
    assert report.ghostscript_available is True
    assert report.issues == []


def test_ocr_doctor_reports_missing_dependencies_and_language() -> None:
    def runner(command, **kwargs):
        if command[:2] == ["ocrmypdf", "--version"]:
            raise FileNotFoundError("ocrmypdf")
        if command[:2] == ["tesseract", "--version"]:
            return FakeCompletedProcess(stdout="tesseract 5.5.2\n")
        if command[:2] == ["tesseract", "--list-langs"]:
            return FakeCompletedProcess(stdout="eng\nosd\n")
        if command[:2] == ["gs", "--version"]:
            raise FileNotFoundError("gs")
        raise AssertionError(command)

    report = check_ocr_environment(runner=runner, module_available=lambda name: name == "pdfplumber")

    assert report.ok is False
    assert "ocrmypdf_unavailable" in report.issues
    assert "tesseract_language_missing" in report.issues
    assert "pdfium_unavailable" in report.issues
    assert "opencv_unavailable" in report.issues
    assert "ghostscript_unavailable" in report.issues


def test_ocr_doctor_reports_tesseract_command_failure() -> None:
    def runner(command, **kwargs):
        if command[:2] == ["ocrmypdf", "--version"]:
            return FakeCompletedProcess(stdout="17.8.0\n")
        raise subprocess.CalledProcessError(returncode=1, cmd=command, stderr="boom")

    report = check_ocr_environment(runner=runner, module_available=lambda name: True)

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
        if command[:2] == ["gs", "--version"]:
            return FakeCompletedProcess(stdout="10.03.0\n")
        raise AssertionError(command)

    report = check_ocr_environment(runner=runner, module_available=lambda name: True)

    assert report.ocrmypdf_version == "17.8.0"


def test_ocr_doctor_reports_layout_and_vision_capabilities_separately() -> None:
    def runner(command, **kwargs):
        if command[:2] == ["ocrmypdf", "--version"]:
            return FakeCompletedProcess(stdout="17.8.0\n")
        if command[:2] == ["tesseract", "--version"]:
            return FakeCompletedProcess(stdout="tesseract 5.5.2\n")
        if command[:2] == ["tesseract", "--list-langs"]:
            return FakeCompletedProcess(stdout="spa\n")
        if command[:2] == ["gs", "--version"]:
            return FakeCompletedProcess(stdout="10.03.0\n")
        raise AssertionError(command)

    available = {"pdfplumber": True, "pypdfium2": False, "cv2": True}

    report = check_ocr_environment(
        runner=runner,
        module_available=lambda name: available[name],
    )

    assert report.pdfplumber_available is True
    assert report.pdfium_available is False
    assert report.opencv_available is True
    assert "pdfium_unavailable" in report.issues
    assert "pdfplumber_unavailable" not in report.issues
