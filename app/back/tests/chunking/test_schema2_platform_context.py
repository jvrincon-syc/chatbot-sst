from __future__ import annotations

from chunking.domain.models import NormalizedDocumentBundle, NormalizedDocumentPlatformContext
from ingestion.schemas.artifacts import PlatformArtifactProvenance


def test_schema2_bundle_preserva_platform_provenance() -> None:
    bundle = NormalizedDocumentBundle(
        document_id="legacy-document-id",
        source_hash="a" * 64,
        corpus_version="2026.08.12",
        markdown="# Documento",
        platform_context=NormalizedDocumentPlatformContext(
            project_id="proj_sst-general",
            source_document_id="sdoc_1234",
            source_document_revision_id="srev_1234",
            processing_profile_id="pp_local-pdf",
            processing_profile_fingerprint="a" * 64,
            provenance=PlatformArtifactProvenance(
                rag_variant_id="ragv_local-bge",
                semantic_recipe_fingerprint="b" * 64,
            ),
        ),
    )

    assert bundle.platform_context is not None
    assert bundle.platform_context.project_id == "proj_sst-general"
    assert bundle.platform_context.rag_variant_id == "ragv_local-bge"
