from __future__ import annotations

from pathlib import Path
import unicodedata
from typing import Callable, Iterable

from PIL import Image

from ingestion.schemas.common import BBox, Evidence, Observation


RenderedPage = tuple[int, Image.Image]


class HandwritingDetector:
    def __init__(
        self,
        *,
        renderer: Callable[[Path], Iterable[RenderedPage]] | None = None,
        method: str = "opencv_signature_stroke",
    ) -> None:
        self.renderer = renderer or _render_pdf_pages
        self.method = method

    def evaluate_pdf(
        self,
        source_path: Path,
        *,
        page_texts: dict[int, str] | None = None,
    ) -> Observation:
        try:
            for page_number, image in self.renderer(source_path):
                if page_texts is not None and not _has_signature_cue(
                    page_texts.get(page_number, "")
                ):
                    continue
                bbox = _signature_bbox(image)
                if bbox is not None:
                    return Observation(
                        status="detected",
                        value=True,
                        method=self.method,
                        evidence=[
                            Evidence(
                                page_number=page_number,
                                bbox=bbox,
                                source=self.method,
                            )
                        ],
                    )
        except Exception as exc:
            return Observation(
                status="not_evaluated",
                value=None,
                method=self.method,
                warnings=[f"handwriting_detector_unavailable:{type(exc).__name__}"],
            )
        return Observation(status="not_detected", value=False, method=self.method)


def _render_pdf_pages(source_path: Path) -> Iterable[RenderedPage]:
    import pypdfium2 as pdfium

    document = pdfium.PdfDocument(str(source_path))
    for index, page in enumerate(document, start=1):
        image = page.render(scale=2).to_pil()
        yield index, image


def _signature_bbox(image: Image.Image) -> BBox | None:
    import cv2
    import numpy as np

    gray = np.asarray(image.convert("L"))
    height, width = gray.shape
    lower_top = int(height * 0.42)
    roi = gray[lower_top:, :]
    mask = (roi < 175).astype("uint8") * 255
    if int(np.count_nonzero(mask)) < 100:
        return None

    horizontal_kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT,
        (max(45, width // 18), 1),
    )
    vertical_kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT,
        (1, max(35, height // 30)),
    )
    horizontal = cv2.morphologyEx(mask, cv2.MORPH_OPEN, horizontal_kernel)
    vertical = cv2.morphologyEx(mask, cv2.MORPH_OPEN, vertical_kernel)
    ink = cv2.subtract(mask, horizontal)
    ink = cv2.subtract(ink, vertical)
    close_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (17, 5))
    ink = cv2.morphologyEx(ink, cv2.MORPH_CLOSE, close_kernel)
    ink = cv2.dilate(
        ink,
        cv2.getStructuringElement(cv2.MORPH_RECT, (7, 3)),
        iterations=1,
    )

    contours, _hierarchy = cv2.findContours(
        ink,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE,
    )
    candidates: list[tuple[float, int, int, int, int]] = []
    for contour in contours:
        x, y, candidate_width, candidate_height = cv2.boundingRect(contour)
        if candidate_width < max(80, width * 0.06):
            continue
        if candidate_height < max(28, height * 0.025):
            continue
        aspect_ratio = candidate_width / max(candidate_height, 1)
        if not 1.0 <= aspect_ratio <= 14.0:
            continue
        candidate_mask = ink[y : y + candidate_height, x : x + candidate_width]
        ink_pixels = int(np.count_nonzero(candidate_mask))
        density = ink_pixels / max(candidate_width * candidate_height, 1)
        if not 0.015 <= density <= 0.28:
            continue
        score = candidate_width * candidate_height * (1.0 - density)
        candidates.append((score, x, y, candidate_width, candidate_height))
    if not candidates:
        return None

    _score, x, y, candidate_width, candidate_height = max(candidates)
    return BBox(
        x0=float(x),
        top=float(lower_top + y),
        x1=float(x + candidate_width),
        bottom=float(lower_top + y + candidate_height),
        coordinate_system="pixels",
    )


def _has_signature_cue(text: str) -> bool:
    normalized = unicodedata.normalize("NFD", text.casefold())
    folded = "".join(
        character
        for character in normalized
        if unicodedata.category(character) != "Mn"
    )
    return any(
        cue in folded
        for cue in (
            "firma",
            "firmante",
            "representante legal",
            "apoderado",
        )
    )
