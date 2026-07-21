from pathlib import Path

from PIL import Image, ImageDraw

from ingestion.structure.handwriting import HandwritingDetector


def test_handwriting_detector_detects_large_signature_strokes(tmp_path: Path) -> None:
    image = Image.new("L", (900, 1100), "white")
    draw = ImageDraw.Draw(image)
    draw.text((120, 150), "Texto impreso", fill="black")
    draw.line([(160, 760), (520, 760)], fill="black", width=3)
    draw.line(
        [(170, 705), (230, 760), (330, 690), (460, 725), (610, 670)],
        fill="black",
        width=5,
        joint="curve",
    )
    source = tmp_path / "signed.pdf"

    detector = HandwritingDetector(renderer=lambda _path: [(1, image)])

    observation = detector.evaluate_pdf(source, page_texts={1: "firma"})

    assert observation.status == "detected"
    assert observation.evidence[0].page_number == 1


def test_handwriting_detector_marks_blank_rendered_page_as_not_detected(
    tmp_path: Path,
) -> None:
    image = Image.new("L", (900, 1100), "white")
    draw = ImageDraw.Draw(image)
    draw.text((120, 720), "JOAN MAURICIO ARENAS CLAVIJO", fill="black")
    source = tmp_path / "unsigned.pdf"

    detector = HandwritingDetector(renderer=lambda _path: [(1, image)])

    observation = detector.evaluate_pdf(source)

    assert observation.status == "not_detected"


def test_handwriting_detector_skips_signature_like_shapes_without_textual_cue(
    tmp_path: Path,
) -> None:
    image = Image.new("L", (900, 1100), "white")
    draw = ImageDraw.Draw(image)
    draw.line(
        [(170, 705), (230, 760), (330, 690), (460, 725), (610, 670)],
        fill="black",
        width=5,
    )
    source = tmp_path / "exercise.pdf"

    detector = HandwritingDetector(renderer=lambda _path: [(1, image)])

    observation = detector.evaluate_pdf(source, page_texts={1: "masaje para cabeza"})

    assert observation.status == "not_detected"
