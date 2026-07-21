from __future__ import annotations

from typing import TYPE_CHECKING

from ingestion.config.llama_settings import LlamaSettings

if TYPE_CHECKING:
    from llama_cloud import AsyncLlamaCloud, LlamaCloud


def create_llama_cloud_client(settings: LlamaSettings) -> "LlamaCloud":
    if settings.api_key is None:
        raise ValueError("LLAMA_CLOUD_API_KEY is required")
    from llama_cloud import LlamaCloud

    return LlamaCloud(api_key=settings.api_key.get_secret_value())


def create_async_llama_cloud_client(settings: LlamaSettings) -> "AsyncLlamaCloud":
    if settings.api_key is None:
        raise ValueError("LLAMA_CLOUD_API_KEY is required")
    from llama_cloud import AsyncLlamaCloud

    return AsyncLlamaCloud(api_key=settings.api_key.get_secret_value())
