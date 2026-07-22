from __future__ import annotations

import re
from typing import Any

from llama_index.core import Document

from ingestion.schemas.artifacts import MetadataArtifact, PagesArtifact
from indexing.domain.models import IndexingProfile


_FRONT_MATTER_RE = re.compile(r"\A---\r?\n.*?\r?\n---\r?\n?", re.DOTALL)
_PAGE_MARKER_RE = re.compile(r"<!--\s*page:\s*(\d+)\s*-->")


class NormalizedDocumentFactory:
    excluded_embed_metadata_keys = [
        "document_id",
        "ref_doc_id",
        "source_relpath",
        "source_hash",
        "normalized_relpath",
        "processing_fingerprint",
        "corpus_version",
        "pipeline_version",
        "processing_status",
        "review_reasons",
        "page_catalog",
        "profile_id",
        "chunking_version",
        "embedding_provider",
        "embedding_model",
        "embedding_dimension",
        "vector_store",
        "ingestion_origin",
        "distance_metric",
        "vector_table",
    ]

    def create_document(
        self,
        *,
        markdown: str,
        metadata: MetadataArtifact,
        pages: PagesArtifact,
        profile: IndexingProfile,
        processing_fingerprint: str,
    ) -> Document:
        text = self._strip_front_matter(markdown)
        document_metadata = self._metadata(
            metadata=metadata,
            pages=pages,
            profile=profile,
            processing_fingerprint=processing_fingerprint,
            text=text,
        )
        return Document(
            text=text,
            id_=metadata.document_id,
            metadata=document_metadata,
            excluded_embed_metadata_keys=list(self.excluded_embed_metadata_keys),
        )

    def _metadata(
        self,
        *,
        metadata: MetadataArtifact,
        pages: PagesArtifact,
        profile: IndexingProfile,
        processing_fingerprint: str,
        text: str,
    ) -> dict[str, Any]:
        classification = metadata.classification
        return {
            "document_id": metadata.document_id,
            "ref_doc_id": metadata.document_id,
            "document_name": metadata.document_name,
            "source_relpath": metadata.source_relpath,
            "source_hash": metadata.source_hash,
            "normalized_relpath": metadata.normalized_relpath,
            "document_type": classification.document_type,
            "topic": classification.topic,
            "subtopic": classification.subtopic,
            "page_count": metadata.page_count,
            "language": metadata.language,
            "extraction_method": metadata.extraction_method,
            "corpus_version": metadata.corpus_version,
            "pipeline_version": metadata.pipeline_version,
            "processing_status": metadata.processing_status,
            "review_reasons": list(metadata.review_reasons),
            "processing_fingerprint": processing_fingerprint,
            "profile_id": profile.profile_id,
            "chunking_version": profile.chunking_version,
            "embedding_provider": profile.embedding_provider,
            "embedding_model": profile.embedding_model,
            "embedding_dimension": profile.embedding_dimension,
            "vector_store": profile.vector_store,
            "page_catalog": self._page_catalog(text=text, pages=pages),
        }

    def _strip_front_matter(self, markdown: str) -> str:
        return _FRONT_MATTER_RE.sub("", markdown, count=1).strip()

    def _page_catalog(self, *, text: str, pages: PagesArtifact) -> list[dict[str, int]]:
        matches = list(_PAGE_MARKER_RE.finditer(text))
        if not matches:
            return [
                {
                    "page_number": page.page_number,
                    "char_start": 0,
                    "char_end": len(text),
                }
                for page in pages.pages
            ]

        catalog: list[dict[str, int]] = []
        for index, match in enumerate(matches):
            next_start = (
                matches[index + 1].start()
                if index + 1 < len(matches)
                else len(text)
            )
            char_end = next_start
            while char_end > match.start() and text[char_end - 1].isspace():
                char_end -= 1
            catalog.append(
                {
                    "page_number": int(match.group(1)),
                    "char_start": match.start(),
                    "char_end": char_end,
                }
            )
        return catalog
