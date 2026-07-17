from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

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
        self.renderer = renderer
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
