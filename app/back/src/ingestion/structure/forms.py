from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from ingestion.normalization.text import normalize_text
from ingestion.schemas.artifacts import FormControl, FormGroup, FormLabel, FormsArtifact
from ingestion.schemas.common import BBox, Evidence, Observation


@dataclass
class FormExtractionResult:
    page_number: int
    groups: list[FormGroup] = field(default_factory=list)
    observation: Observation | None = None
    warnings: list[str] = field(default_factory=list)


class FormExtractor:
    def __init__(self, *, backend_available: bool = True, method: str = "vector_geometry") -> None:
        self.backend_available = backend_available
        self.method = method

    def evaluate(self, page: Any) -> FormExtractionResult:
        page_number = _page_number(page)
        if not self.backend_available:
            return FormExtractionResult(
                page_number=page_number,
                observation=Observation(
                    status="not_evaluated",
                    value=None,
                    method=self.method,
                    warnings=["form_extractor_unavailable"],
                ),
                warnings=["form_extractor_unavailable"],
            )

        labels = _labels(page)
        controls = _controls(page, labels)
        if not labels and not controls:
            return FormExtractionResult(
                page_number=page_number,
                observation=Observation(status="not_detected", value=False, method=self.method),
            )

        group = FormGroup(
            group_id=_group_id(page),
            page_number=page_number,
            bbox=_union_bbox([item.bbox for item in labels] + [item.bbox for item in controls]),
            title=_group_title(page),
            labels=labels,
            controls=controls,
        )
        evidence = [
            Evidence(page_number=page_number, bbox=control.bbox, source=self.method)
            for control in controls
        ] or [Evidence(page_number=page_number, source=self.method)]
        return FormExtractionResult(
            page_number=page_number,
            groups=[group],
            observation=Observation(
                status="detected",
                value=True,
                method=self.method,
                evidence=evidence,
            ),
        )

    def evaluate_pages(self, pages: Iterable[Any], *, document_id: str = "pending") -> FormsArtifact:
        results = [self.evaluate(page) for page in pages]
        groups = [group for result in results for group in result.groups]
        observations = [result.observation for result in results if result.observation is not None]
        warnings = sorted({warning for result in results for warning in result.warnings})
        return FormsArtifact(
            schema_version="2.0",
            document_id=document_id,
            groups=groups,
            page_observations=observations,
            warnings=warnings,
        )


def _page_number(page: Any) -> int:
    return int(getattr(page, "page_number", 0) or 0)


def _labels(page: Any) -> list[FormLabel]:
    labels: list[FormLabel] = []
    for block in getattr(page, "blocks", []) or []:
        if str(getattr(block, "role", "") or "") == "label" or _looks_like_label(getattr(block, "text", "")):
            text = normalize_text(str(getattr(block, "text", "") or ""))
            if text:
                labels.append(FormLabel(label_id=_slug(text), text=text, bbox=getattr(block, "bbox", None)))
    return labels


def _controls(page: Any, labels: list[FormLabel]) -> list[FormControl]:
    controls: list[FormControl] = []
    for index, block in enumerate(getattr(page, "blocks", []) or [], start=1):
        role = str(getattr(block, "role", "") or "").lower()
        kind = str(getattr(block, "kind", getattr(block, "block_type", "")) or "").lower()
        bbox = getattr(block, "bbox", None)
        if not isinstance(bbox, BBox):
            continue
        if role not in {"control", "blank_area"} and kind not in {"line", "rect", "rectangle"}:
            continue
        nearest = _nearest_label(bbox, labels)
        width = bbox.x1 - bbox.x0
        height = bbox.bottom - bbox.top
        control_type = "checkbox" if width <= 18 and height <= 18 else "blank_area"
        controls.append(
            FormControl(
                control_id=f"control_{index}",
                control_type=control_type,
                bbox=bbox,
                label_id=nearest.label_id if nearest is not None else None,
            )
        )
    return controls


def _looks_like_label(text: str) -> bool:
    normalized = normalize_text(text).casefold().rstrip(":")
    if not normalized:
        return False
    known = {
        "nombre",
        "cargo",
        "fecha",
        "area",
        "documento",
        "descripcion",
        "testigo",
        "firma",
        "telefono",
        "correo",
    }
    return text.strip().endswith(":") or normalized in known


def _nearest_label(control_bbox: BBox, labels: list[FormLabel]) -> FormLabel | None:
    candidates = [label for label in labels if label.bbox is not None]
    if not candidates:
        return None
    same_line = [
        label
        for label in candidates
        if label.bbox is not None
        and abs(((label.bbox.top + label.bbox.bottom) / 2) - ((control_bbox.top + control_bbox.bottom) / 2)) <= 12
        and label.bbox.x1 <= control_bbox.x0
    ]
    pool = same_line or candidates
    return min(
        pool,
        key=lambda label: abs((label.bbox.bottom if label.bbox else 0) - control_bbox.top)
        + abs((label.bbox.x1 if label.bbox else 0) - control_bbox.x0),
    )


def _group_title(page: Any) -> str | None:
    for block in getattr(page, "blocks", []) or []:
        text = normalize_text(str(getattr(block, "text", "") or ""))
        folded = text.casefold()
        if any(word in folded for word in ("queja", "reclamo", "convivencia", "denuncia")):
            return text
    return None


def _group_id(page: Any) -> str:
    title = _group_title(page)
    if title and any(word in title.casefold() for word in ("queja", "reclamo", "denuncia")):
        return "complaint"
    return f"form_page_{_page_number(page)}"


def _slug(text: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "_", text.casefold()).strip("_")
    return value or "label"


def _union_bbox(values: list[BBox | None]) -> BBox | None:
    bboxes = [value for value in values if value is not None]
    if not bboxes:
        return None
    return BBox(
        x0=min(bbox.x0 for bbox in bboxes),
        top=min(bbox.top for bbox in bboxes),
        x1=max(bbox.x1 for bbox in bboxes),
        bottom=max(bbox.bottom for bbox in bboxes),
        coordinate_system=bboxes[0].coordinate_system,
    )
