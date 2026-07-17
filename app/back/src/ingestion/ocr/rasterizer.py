from __future__ import annotations

import os
from uuid import uuid4
from pathlib import Path
from typing import Callable, Optional

import pypdfium2 as pdfium
from pydantic import Field

from ingestion.schemas.common import BBox, StrictModel


class RasterizationCapabilityError(RuntimeError):
    pass


class RasterRegion(StrictModel):
    image_path: Path
    page_number: int = Field(ge=1)
    bbox: Optional[BBox] = None
    dpi: int = Field(gt=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class PageRasterizer:
    def __init__(self, renderer: Callable[..., RasterRegion] | None = None, dpi: int = 300) -> None:
        self.renderer = renderer or _render_with_pdfium
        self.dpi = dpi

    def render(
        self,
        path: Path,
        page_number: int,
        clip: BBox | None = None,
        dpi: int | None = None,
    ) -> RasterRegion:
        if self.renderer is None:
            raise RasterizationCapabilityError("PDF rasterization backend is unavailable.")
        return self.renderer(path=path, page_number=page_number, clip=clip, dpi=dpi or self.dpi)


def _render_with_pdfium(
    *,
    path: Path,
    page_number: int,
    clip: BBox | None,
    dpi: int,
) -> RasterRegion:
    try:
        document = pdfium.PdfDocument(str(path))
        page = document[page_number - 1]
        width, height = page.get_size()
        crop = None
        if clip is not None:
            crop = (
                clip.x0,
                height - clip.bottom,
                width - clip.x1,
                clip.top,
            )
        render_options = {"scale": dpi / 72}
        if crop is not None:
            render_options["crop"] = crop
        bitmap = page.render(**render_options)
        image = bitmap.to_pil()
        temp_root = Path(os.getenv("OCR_TEMP_DIR", ".tmp/ocr"))
        temp_root.mkdir(parents=True, exist_ok=True)
        image_path = temp_root / f"region-{uuid4().hex}.png"
        image.save(image_path, format="PNG")
        return RasterRegion(
            image_path=image_path,
            page_number=page_number,
            bbox=clip,
            dpi=dpi,
            width=image.width,
            height=image.height,
        )
    except Exception as exc:
        raise RasterizationCapabilityError(
            f"PDFium could not render page {page_number} of {path}."
        ) from exc
