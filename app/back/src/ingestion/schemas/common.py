from __future__ import annotations

import re
from typing import Annotated, Any, Literal, Optional

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    model_validator,
)


class StrictModel(BaseModel):
    """Base for canonical schema 2.0 values."""

    model_config = ConfigDict(extra="forbid")


def _validate_relative_posix_path(value: str) -> str:
    if not value:
        raise ValueError("path must not be empty")
    if "\\" in value:
        raise ValueError("path must use POSIX separators")
    if value.startswith("/") or re.match(r"^[A-Za-z]:", value):
        raise ValueError("path must be relative")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("path must not contain empty, '.' or '..' components")
    return value


RelativePosixPath = Annotated[str, AfterValidator(_validate_relative_posix_path)]


def _reject_boolean_number(value: Any) -> Any:
    if isinstance(value, bool):
        raise ValueError("numeric value must not be boolean")
    return value


NonBooleanFloat = Annotated[float, BeforeValidator(_reject_boolean_number)]


class BBox(StrictModel):
    x0: float
    top: float
    x1: float
    bottom: float
    coordinate_system: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_positive_area(self) -> "BBox":
        if self.x1 <= self.x0 or self.bottom <= self.top:
            raise ValueError("bbox must have positive area")
        return self


class Evidence(StrictModel):
    page_number: Optional[int] = Field(default=None, ge=1)
    bbox: Optional[BBox] = None
    region: Optional[str] = None
    text: Optional[str] = None
    pattern: Optional[str] = None
    source: Optional[str] = None
    warnings: list[str] = Field(default_factory=list)


class Observation(StrictModel):
    status: Literal["detected", "not_detected", "not_evaluated"]
    value: Optional[bool]
    engine: Optional[str] = None
    engine_version: Optional[str] = None
    method: Optional[str] = None
    evidence: list[Evidence] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_tristate(self) -> "Observation":
        if self.status == "detected":
            if self.value is not True or not self.evidence:
                raise ValueError(
                    "detected observations require value=true and non-empty evidence"
                )
        elif self.status == "not_detected":
            if self.value is not False or not (self.engine or self.method):
                raise ValueError(
                    "not_detected observations require value=false and a named engine or method"
                )
        elif self.value is not None:
            raise ValueError("not_evaluated observations require value=null")
        return self


class ConfidenceMetric(StrictModel):
    kind: Literal["measured", "estimated", "unavailable"]
    value: Optional[NonBooleanFloat] = Field(default=None, ge=0.0, le=1.0)
    engine: Optional[str] = None
    engine_version: Optional[str] = None
    unit: Optional[str] = None
    sample_size: Optional[int] = None
    method: Optional[str] = None
    provenance: Optional[str] = None
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_metric_provenance(self) -> "ConfidenceMetric":
        if self.kind == "measured":
            if self.value is None:
                raise ValueError("measured confidence requires a numeric value")
            if not all((self.engine, self.engine_version, self.unit)):
                raise ValueError(
                    "measured confidence requires engine, engine_version and unit"
                )
            if self.sample_size is None or self.sample_size <= 0:
                raise ValueError("measured confidence requires positive sample_size")
        elif self.kind == "estimated":
            if self.value is None:
                raise ValueError("estimated confidence requires a numeric value")
            if not (self.method or self.provenance):
                raise ValueError(
                    "estimated confidence requires method or provenance"
                )
        elif self.value is not None:
            raise ValueError("unavailable confidence requires value=null")
        return self


class MeasuredValue(StrictModel):
    status: Literal["measured", "estimated", "unavailable"]
    value: Optional[NonBooleanFloat] = None
    unit: Optional[str] = None
    engine: Optional[str] = None
    engine_version: Optional[str] = None
    method: Optional[str] = None
    provenance: Optional[str] = None
    evidence: list[Evidence] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_measurement(self) -> "MeasuredValue":
        if self.status == "measured":
            if self.value is None:
                raise ValueError("measured status requires a numeric value")
            if not self.unit or not self.engine or not self.engine_version:
                raise ValueError(
                    "measured status requires unit, engine and engine_version"
                )
        elif self.status == "estimated":
            if self.value is None:
                raise ValueError("estimated status requires a numeric value")
            if not self.unit or not (self.method or self.provenance):
                raise ValueError(
                    "estimated status requires unit and method or provenance"
                )
        elif self.value is not None:
            raise ValueError("unavailable status requires value=null")
        return self


class DocumentField(StrictModel):
    value: Optional[Any]
    value_raw: Optional[Any] = None
    status: Literal["extracted", "not_found", "not_evaluated", "conflicting"]
    evidence: list[Evidence] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_status_value(self) -> "DocumentField":
        if self.status == "extracted" and self.value is None:
            raise ValueError("extracted document fields require a value")
        if self.status in {"not_found", "not_evaluated"} and self.value is not None:
            raise ValueError(f"{self.status} document fields require value=null")
        return self


class PageBlock(StrictModel):
    block_id: str = Field(min_length=1)
    text: str
    bbox: Optional[BBox] = None
    extraction_method: Literal["markdown", "pdf_digital", "ocr", "hybrid", "llamaparse", "hybrid_llamaparse"]
    role: Optional[str] = None
    region: Optional[str] = None
    warnings: list[str] = Field(default_factory=list)


class RemovedSpan(StrictModel):
    text: str
    reason: str = Field(min_length=1)
    bbox: Optional[BBox] = None
    block_id: Optional[str] = None
    warnings: list[str] = Field(default_factory=list)


class NormalizationAction(StrictModel):
    action: str = Field(min_length=1)
    before: Optional[str] = None
    after: Optional[str] = None
    details: Optional[str] = None
    evidence: list[Evidence] = Field(default_factory=list)
