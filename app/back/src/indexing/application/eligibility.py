from __future__ import annotations

from typing import Mapping

from pydantic import Field

from ingestion.schemas.common import StrictModel


class EligibilityResult(StrictModel):
    """Result of evaluating whether a normalized document can be indexed."""

    document_id: str = Field(min_length=1)
    source_relpath: str = Field(min_length=1)
    source_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    ingestion_origin: str = Field(pattern=r"^(local|llama_cloud)$")
    eligible: bool
    reason: str = Field(min_length=1)


class IndexingEligibilityService:
    """Decide whether a normalized record can proceed to indexing."""

    def evaluate(
        self,
        *,
        record: Mapping[str, object],
        decision: object | None,
    ) -> EligibilityResult:
        status = str(record.get("processing_status", "") or "")
        eligible = status == "processed"
        reason = "processed" if eligible else "needs_review_without_approval"

        if status == "needs_review" and decision is not None:
            decision_value = getattr(decision, "decision", None)
            if decision_value == "approved":
                eligible = True
                reason = "human_approved"
            elif decision_value == "rejected":
                reason = "needs_review_rejected"

        if status not in {"processed", "needs_review"}:
            eligible = False
            reason = f"unsupported_status:{status or 'missing'}"

        return EligibilityResult(
            document_id=str(record["document_id"]),
            source_relpath=str(record["source_relpath"]),
            source_hash=_normalized_hash(record),
            ingestion_origin=_ingestion_origin(record),
            eligible=eligible,
            reason=reason,
        )


def _ingestion_origin(record: Mapping[str, object]) -> str:
    origin = record.get("ingestion_origin") or record.get("ingestion_provider")
    if origin is None:
        origin = record.get("ingestionProvider")
    return str(origin or "local")


def _normalized_hash(record: Mapping[str, object]) -> str:
    value = str(record.get("source_hash") or record.get("content_hash") or "")
    if value.startswith("sha256:"):
        return value.removeprefix("sha256:")
    return value
