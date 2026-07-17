from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median
from typing import Any, Iterable

from ingestion.normalization.text import normalize_text
from ingestion.schemas.common import BBox, Evidence, Observation, RemovedSpan


@dataclass(frozen=True)
class BoilerplateMatch:
    normalized_text: str
    text: str
    region: str
    page_numbers: tuple[int, ...]
    block_ids: tuple[str, ...]
    bboxes: tuple[BBox, ...]


@dataclass
class BoilerplateResult:
    matches: list[BoilerplateMatch] = field(default_factory=list)
    removed_spans_by_page: dict[int, list[RemovedSpan]] = field(default_factory=dict)
    removed_block_ids_by_page: dict[int, set[str]] = field(default_factory=dict)
    observations: list[Observation] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def removed_spans_for_page(self, page_number: int) -> list[RemovedSpan]:
        return list(self.removed_spans_by_page.get(page_number, ()))

    def is_removed(self, page_number: int, block_id: str) -> bool:
        return block_id in self.removed_block_ids_by_page.get(page_number, set())


def detect_boilerplate(
    pages: Iterable[Any],
    *,
    min_repetitions: int = 2,
    band_ratio: float = 0.16,
    vertical_tolerance: float = 8.0,
) -> BoilerplateResult:
    page_list = list(pages)
    groups: dict[tuple[str, str], list[tuple[Any, Any, BBox]]] = {}
    watermark_evidence: list[Evidence] = []

    for page in page_list:
        page_number = _page_number(page)
        page_height = float(getattr(page, "height", 0) or 0)
        for block in getattr(page, "blocks", []) or []:
            text = _block_text(block)
            bbox = _block_bbox(block)
            if not text or bbox is None:
                continue
            role = str(getattr(block, "role", "") or "").lower()
            if role == "watermark":
                watermark_evidence.append(Evidence(page_number=page_number, bbox=bbox, text=text, source="layout"))
                continue
            region = _boilerplate_region(block, bbox, page_height, band_ratio)
            if region is None:
                continue
            key_text = _normalize_key(text)
            if key_text:
                groups.setdefault((key_text, region), []).append((page, block, bbox))

    result = BoilerplateResult()
    for (normalized_text, region), members in groups.items():
        unique_pages = {_page_number(page) for page, _, _ in members}
        if len(unique_pages) < min_repetitions or not _positions_agree([bbox for _, _, bbox in members], vertical_tolerance):
            continue
        block_ids: list[str] = []
        bboxes: list[BBox] = []
        page_numbers: list[int] = []
        representative = _block_text(members[0][1])
        for page, block, bbox in members:
            page_number = _page_number(page)
            block_id = _block_id(page_number, block)
            page_numbers.append(page_number)
            block_ids.append(block_id)
            bboxes.append(bbox)
            result.removed_spans_by_page.setdefault(page_number, []).append(
                RemovedSpan(
                    text=_block_text(block),
                    reason=f"repeated_{region}",
                    bbox=bbox,
                    block_id=block_id,
                )
            )
            result.removed_block_ids_by_page.setdefault(page_number, set()).add(block_id)
        result.matches.append(
            BoilerplateMatch(
                normalized_text=normalized_text,
                text=representative,
                region=region,
                page_numbers=tuple(sorted(set(page_numbers))),
                block_ids=tuple(block_ids),
                bboxes=tuple(bboxes),
            )
        )

    if watermark_evidence:
        result.observations.append(
            Observation(
                status="detected",
                value=True,
                method="layout_watermark_observation",
                evidence=watermark_evidence,
            )
        )
    return result


def build_indexable_text(page: Any, boilerplate: BoilerplateResult) -> str:
    page_number = _page_number(page)
    blocks = list(getattr(page, "blocks", []) or [])
    if not blocks:
        return normalize_text(str(getattr(page, "text", "") or ""))
    body_text = [
        _block_text(block)
        for block in blocks
        if _block_text(block) and not boilerplate.is_removed(page_number, _block_id(page_number, block))
    ]
    return normalize_text("\n".join(body_text))


def _page_number(page: Any) -> int:
    return int(getattr(page, "page_number", 0) or 0)


def _block_id(page_number: int, block: Any) -> str:
    value = getattr(block, "block_id", None)
    if value:
        return str(value)
    return f"p{page_number}_block_{id(block)}"


def _block_text(block: Any) -> str:
    return str(getattr(block, "text", "") or "")


def _block_bbox(block: Any) -> BBox | None:
    value = getattr(block, "bbox", None)
    return value if isinstance(value, BBox) else None


def _normalize_key(text: str) -> str:
    return normalize_text(text).casefold()


def _boilerplate_region(block: Any, bbox: BBox, page_height: float, band_ratio: float) -> str | None:
    explicit_region = str(getattr(block, "region", "") or "").lower()
    if explicit_region in {"header", "footer"}:
        return explicit_region
    if page_height <= 0:
        return None
    top_band = page_height * band_ratio
    bottom_band = page_height * (1 - band_ratio)
    if bbox.top <= top_band:
        return "header"
    if bbox.bottom >= bottom_band:
        return "footer"
    return None


def _positions_agree(bboxes: list[BBox], tolerance: float) -> bool:
    if not bboxes:
        return False
    top_mid = median([bbox.top for bbox in bboxes])
    bottom_mid = median([bbox.bottom for bbox in bboxes])
    return all(
        abs(bbox.top - top_mid) <= tolerance and abs(bbox.bottom - bottom_mid) <= tolerance
        for bbox in bboxes
    )
