from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import Field, model_validator

from ingestion.schemas.common import BBox, StrictModel


PDF_POINT_COORDINATE_SYSTEM = "pdf_points"
LayoutBlockType = Literal["text", "image", "line", "rect"]


class LayoutBlock(StrictModel):
    block_id: str = Field(min_length=1)
    block_type: LayoutBlockType
    bbox: BBox
    reading_order: int = Field(ge=0)
    text: Optional[str] = None
    source: str = Field(min_length=1)
    raw_attributes: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_geometry_and_text(self) -> "LayoutBlock":
        if self.bbox.coordinate_system != PDF_POINT_COORDINATE_SYSTEM:
            raise ValueError("layout block bbox must use PDF point top-left coordinates")
        if self.block_type == "text" and self.text is None:
            raise ValueError("text layout blocks require text")
        if self.block_type != "text" and self.text is not None:
            raise ValueError("non-text layout blocks must not carry text")
        return self


class LayoutPage(StrictModel):
    page_number: int = Field(ge=1)
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    cropbox: BBox
    rotation: int = 0
    text_raw: str = ""
    blocks: list[LayoutBlock] = Field(default_factory=list)
    tables: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_page_geometry(self) -> "LayoutPage":
        if self.cropbox.coordinate_system != PDF_POINT_COORDINATE_SYSTEM:
            raise ValueError("layout page cropbox must use PDF point top-left coordinates")

        orders = [block.reading_order for block in self.blocks]
        if len(orders) != len(set(orders)):
            raise ValueError("layout block reading_order values must be unique per page")
        if orders != sorted(orders):
            raise ValueError("layout blocks must be sorted by deterministic reading_order")
        return self
