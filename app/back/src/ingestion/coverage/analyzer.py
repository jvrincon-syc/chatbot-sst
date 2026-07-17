from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import Field

from ingestion.schemas.common import BBox, StrictModel


class CandidateRegion(StrictModel):
    page_number: int = Field(ge=1)
    bbox: BBox
    reason: str = Field(min_length=1)
    source_block_id: Optional[str] = None


class CoverageAssessment(StrictModel):
    page_number: int = Field(ge=1)
    status: Literal["complete", "partial", "unavailable"]
    word_count: int = Field(ge=0)
    candidate_regions: list[CandidateRegion] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class CoverageAnalyzer:
    def __init__(self, *, sparse_page_word_threshold: int = 20, logo_max_area_ratio: float = 0.04) -> None:
        self.sparse_page_word_threshold = sparse_page_word_threshold
        self.logo_max_area_ratio = logo_max_area_ratio

    def assess(self, page: Any) -> CoverageAssessment:
        page_number = int(getattr(page, "page_number"))
        text = str(getattr(page, "text_normalized", getattr(page, "text", "")) or "")
        word_count = len(text.split())
        candidates: list[CandidateRegion] = []
        page_area = _page_area(page)

        for block in getattr(page, "blocks", []) or []:
            role = str(getattr(block, "role", "") or "").casefold()
            block_type = str(getattr(block, "block_type", role) or "").casefold()
            bbox = getattr(block, "bbox", None)
            if not isinstance(bbox, BBox):
                continue
            if block_type != "image" and role != "image":
                continue
            if _is_logo_like(role, bbox, page_area, self.logo_max_area_ratio):
                continue
            if word_count < self.sparse_page_word_threshold:
                candidates.append(
                    CandidateRegion(
                        page_number=page_number,
                        bbox=bbox,
                        reason="image_region_on_sparse_page",
                        source_block_id=getattr(block, "block_id", None),
                    )
                )

        return CoverageAssessment(
            page_number=page_number,
            status="partial" if candidates else "complete",
            word_count=word_count,
            candidate_regions=candidates,
        )


def _page_area(page: Any) -> float | None:
    width = getattr(page, "width", None)
    height = getattr(page, "height", None)
    if width is None or height is None:
        return None
    return float(width) * float(height)


def _is_logo_like(role: str, bbox: BBox, page_area: float | None, max_area_ratio: float) -> bool:
    if role == "logo":
        return True
    if page_area is None:
        return False
    area = (bbox.x1 - bbox.x0) * (bbox.bottom - bbox.top)
    return area / page_area <= max_area_ratio and bbox.top <= 100
