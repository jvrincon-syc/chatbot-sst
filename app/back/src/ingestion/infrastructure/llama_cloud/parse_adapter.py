from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ingestion.application.ports.parser import ParseRequest
from ingestion.domain.models.parsed_document import (
    ParsedDocument,
    ParsedItemsPage,
    ParsedPage,
    ParsedPageMetadata,
)
from ingestion.domain.models.provider import ProviderJobRef
from ingestion.infrastructure.llama_cloud.errors import ProviderMalformedResultError
from ingestion.infrastructure.llama_cloud.parse_config import LlamaParseConfig


class LlamaParseAdapter:
    def __init__(self, *, client: object, config: LlamaParseConfig) -> None:
        self._client = client
        self._config = config

    async def parse(self, request: ParseRequest) -> ParsedDocument:
        parsing = getattr(self._client, "parsing")
        result = await parsing.parse(
            upload_file=request.source_path,
            **self._config.to_parse_kwargs(),
        )
        parse_payload = _payload(result)
        job_id = _job_id(parse_payload)
        result = await parsing.get(job_id, expand=list(self._config.effective_expand()))
        return map_parse_response_to_parsed_document(
            result,
            configuration_hash=self._config.configuration_hash(),
            fallback_job_payload=parse_payload,
        )


def map_parse_response_to_parsed_document(
    response: object,
    *,
    configuration_hash: str,
    fallback_job_payload: dict[str, Any] | None = None,
) -> ParsedDocument:
    payload = _payload(response)
    fallback_job_payload = fallback_job_payload or {}
    job_payload = payload.get("job") if isinstance(payload.get("job"), dict) else {}
    fallback_job = (
        fallback_job_payload.get("job")
        if isinstance(fallback_job_payload.get("job"), dict)
        else {}
    )
    job_id = str(
        payload.get("id")
        or payload.get("job_id")
        or job_payload.get("id")
        or fallback_job_payload.get("id")
        or fallback_job_payload.get("job_id")
        or fallback_job.get("id")
        or ""
    )
    if not job_id:
        raise ProviderMalformedResultError("LlamaParse response did not include a job id")
    status = str(
        payload.get("status")
        or job_payload.get("status")
        or fallback_job_payload.get("status")
        or fallback_job.get("status")
        or "completed"
    )
    provider_job = ProviderJobRef(
        provider="llama_cloud",
        capability="parse",
        job_id=job_id,
        status=_coerce_status(status),
        configuration_hash=configuration_hash,
        created_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc) if status == "completed" else None,
    )
    return ParsedDocument(
        provider_job=provider_job,
        markdown_pages=_markdown_pages(
            payload.get("markdown")
            or payload.get("markdown_full")
            or payload.get("text")
            or payload.get("text_full")
        ),
        items_pages=_items_pages(payload.get("items")),
        page_metadata=_page_metadata(payload.get("metadata")),
        job_metadata=_dict_or_empty(payload.get("job_metadata")),
        warnings=[],
    )


def _job_id(payload: dict[str, Any]) -> str:
    job_payload = payload.get("job") if isinstance(payload.get("job"), dict) else {}
    job_id = str(payload.get("id") or payload.get("job_id") or job_payload.get("id") or "")
    if not job_id:
        raise ProviderMalformedResultError("LlamaParse response did not include a job id")
    return job_id


def _payload(response: object) -> dict[str, Any]:
    if isinstance(response, dict):
        return response
    if hasattr(response, "model_dump"):
        return response.model_dump(mode="json")
    if hasattr(response, "dict"):
        return response.dict()
    raise ProviderMalformedResultError("unsupported LlamaParse response type")


def _coerce_status(status: str) -> str:
    folded = status.lower()
    if folded in {"pending", "running", "completed", "failed", "cancelled"}:
        return folded
    return "completed"


def _markdown_pages(value: object) -> list[ParsedPage]:
    if isinstance(value, str):
        return [ParsedPage(page_number=1, markdown=value)]
    if isinstance(value, dict):
        pages_value = value.get("pages")
        if isinstance(pages_value, list):
            value = pages_value
        else:
            markdown = value.get("markdown") or value.get("text")
            return [ParsedPage(page_number=1, markdown=str(markdown))] if markdown else []
    if not isinstance(value, list):
        return []
    pages: list[ParsedPage] = []
    for index, item in enumerate(value, start=1):
        if isinstance(item, dict):
            page_number = int(item.get("page") or item.get("page_number") or index)
            markdown = str(item.get("markdown") or item.get("text") or "")
        else:
            page_number = index
            markdown = str(item)
        pages.append(ParsedPage(page_number=page_number, markdown=markdown))
    return pages


def _items_pages(value: object) -> list[ParsedItemsPage]:
    if isinstance(value, dict):
        pages_value = value.get("pages")
        if isinstance(pages_value, list):
            value = pages_value
    if not isinstance(value, list):
        return []
    pages: list[ParsedItemsPage] = []
    for index, item in enumerate(value, start=1):
        if isinstance(item, dict):
            page_number = int(item.get("page") or item.get("page_number") or index)
            items = item.get("items") if isinstance(item.get("items"), list) else []
        else:
            page_number = index
            items = []
        pages.append(ParsedItemsPage(page_number=page_number, items=items))
    return pages


def _page_metadata(value: object) -> list[ParsedPageMetadata]:
    if isinstance(value, dict):
        pages_value = value.get("pages")
        if isinstance(pages_value, list):
            value = pages_value
    if not isinstance(value, list):
        return []
    pages: list[ParsedPageMetadata] = []
    for index, item in enumerate(value, start=1):
        if isinstance(item, dict):
            page_number = int(item.get("page") or item.get("page_number") or index)
            metadata = {key: child for key, child in item.items() if key not in {"page", "page_number"}}
        else:
            page_number = index
            metadata = {}
        pages.append(ParsedPageMetadata(page_number=page_number, metadata=metadata))
    return pages


def _dict_or_empty(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
