from __future__ import annotations

import pytest
from llama_index.core.schema import TextNode


@pytest.fixture
def nodes() -> list[TextNode]:
    return [
        TextNode(
            id_="child_1",
            text="Contenido SST uno",
            metadata={
                "ref_doc_id": "doc_1",
                "node_role": "child",
                "source_relpath": "manual/doc.pdf",
                "source_hash": "a" * 64,
                "ingestion_origin": "llama_cloud",
                "chunking_version": "structure-aware-v1",
            },
        ),
        TextNode(
            id_="child_2",
            text="Contenido SST dos",
            metadata={
                "ref_doc_id": "doc_1",
                "node_role": "child",
                "source_relpath": "manual/doc.pdf",
                "source_hash": "a" * 64,
                "ingestion_origin": "llama_cloud",
                "chunking_version": "structure-aware-v1",
            },
        ),
    ]
