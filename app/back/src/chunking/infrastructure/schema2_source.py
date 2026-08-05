from __future__ import annotations

import json
import re
from pathlib import Path

from chunking.application.source_span_resolver import SourceSpanResolver
from chunking.domain.models import NormalizedDocumentBundle, ValidatedSidecars
from ingestion.schemas.artifacts import (
    FormsArtifact,
    MetadataArtifact,
    OcrArtifact,
    PagesArtifact,
    TablesArtifact,
)
from ingestion.schemas.loader import load_artifact


_FRONT_MATTER_RE = re.compile(r"\A---\r?\n(?P<content>.*?)\r?\n---\r?\n?", re.DOTALL)


class Schema2BundleAssembler:
    """Build a normalized chunking bundle from already loaded Schema 2 artifacts."""

    def __init__(self, resolver: SourceSpanResolver | None = None) -> None:
        self._resolver = resolver or SourceSpanResolver()

    def build(
        self,
        *,
        markdown: str,
        metadata: MetadataArtifact,
        pages: PagesArtifact,
        tables: TablesArtifact | None = None,
        forms: FormsArtifact | None = None,
        ocr: OcrArtifact | None = None,
        relative_path: str | None = None,
    ) -> NormalizedDocumentBundle:
        self._validate_consistency(
            markdown=markdown,
            relative_path=relative_path,
            metadata=metadata,
            pages=pages,
            tables=tables,
            forms=forms,
            ocr=ocr,
        )
        resolution = self._resolver.resolve(markdown=markdown, pages=pages.pages)
        return NormalizedDocumentBundle(
            document_id=metadata.document_id,
            source_hash=metadata.source_hash,
            corpus_version=metadata.corpus_version,
            markdown=markdown,
            source_relpath=str(metadata.source_relpath),
            normalized_relpath=str(metadata.normalized_relpath),
            page_traces=resolution.page_traces,
            sidecars=ValidatedSidecars(
                tables_present=tables is not None,
                forms_present=forms is not None,
                ocr_present=ocr is not None,
                ocr_confidence=ocr.document_confidence.value if ocr is not None else None,
                table_markdown=(
                    tuple(table.markdown_representation for table in tables.tables)
                    if tables is not None
                    else ()
                ),
                form_titles=(
                    tuple(group.title for group in forms.groups if group.title is not None)
                    if forms is not None
                    else ()
                ),
            ),
            warnings=resolution.warnings,
        )

    def _validate_consistency(
        self,
        *,
        markdown: str,
        relative_path: str | None,
        metadata: MetadataArtifact,
        pages: PagesArtifact,
        tables: TablesArtifact | None,
        forms: FormsArtifact | None,
        ocr: OcrArtifact | None,
    ) -> None:
        if relative_path is not None and str(metadata.normalized_relpath) != relative_path:
            raise ValueError("metadata normalized_relpath does not match markdown path")
        if metadata.page_count != pages.page_count:
            raise ValueError("metadata page_count does not match pages page_count")
        document_ids = [metadata.document_id, pages.document_id]
        document_ids.extend(
            sidecar.document_id for sidecar in (tables, forms, ocr) if sidecar is not None
        )
        if any(document_id != metadata.document_id for document_id in document_ids):
            raise ValueError("sidecar document_id does not match metadata document_id")

        front_matter = self._front_matter(markdown)
        for key, expected in (
            ("document_id", metadata.document_id),
            ("source_relpath", str(metadata.source_relpath)),
        ):
            if key in front_matter and front_matter.get(key) != expected:
                raise ValueError(f"markdown {key} does not match metadata")
        source_hash = front_matter.get("source_hash")
        if source_hash is not None and source_hash != metadata.source_hash:
            raise ValueError("markdown source_hash does not match metadata")

    def _front_matter(self, markdown: str) -> dict[str, str]:
        match = _FRONT_MATTER_RE.match(markdown)
        if match is None:
            return {}
        values: dict[str, str] = {}
        for line in match.group("content").splitlines():
            key, separator, value = line.partition(":")
            if separator:
                values[key.strip()] = value.strip()
        return values


class Schema2NormalizedDocumentSource:
    """Loads a validated Schema 2 bundle rooted in ``docs_normalized``."""

    def __init__(self, docs_normalized: Path, resolver: SourceSpanResolver | None = None) -> None:
        """Create a source constrained to one normalized-document root."""
        self._docs_normalized = docs_normalized.resolve()
        self._assembler = Schema2BundleAssembler(resolver=resolver)

    def load(self, relative_markdown_path: str | Path) -> NormalizedDocumentBundle:
        """Return a pre-structural bundle after validating all available sidecars."""
        markdown_path = self._resolve_markdown_path(relative_markdown_path)
        markdown = markdown_path.read_text(encoding="utf-8")
        metadata = self._load_required(markdown_path, "metadata", MetadataArtifact)
        pages = self._load_required(markdown_path, "pages", PagesArtifact)
        tables = self._load_optional(markdown_path, "tables", TablesArtifact)
        forms = self._load_optional(markdown_path, "forms", FormsArtifact)
        ocr = self._load_optional(markdown_path, "ocr", OcrArtifact)

        relative_path = markdown_path.relative_to(self._docs_normalized).as_posix()
        return self._assembler.build(
            markdown=markdown,
            metadata=metadata,
            pages=pages,
            tables=tables,
            forms=forms,
            ocr=ocr,
            relative_path=relative_path,
        )

    def _resolve_markdown_path(self, value: str | Path) -> Path:
        path = Path(value)
        if path.is_absolute():
            candidate = path.resolve()
            if not candidate.is_relative_to(self._docs_normalized):
                raise ValueError("markdown path is outside docs_normalized")
            return candidate
        if any(part in {"", ".", ".."} for part in path.parts) or path.suffix != ".md":
            raise ValueError("markdown path contains an unsafe component")
        candidate = (self._docs_normalized / path).resolve()
        if not candidate.is_relative_to(self._docs_normalized):
            raise ValueError("markdown path is outside docs_normalized")
        return candidate

    def _load_required(self, markdown_path: Path, name: str, artifact_type: type[object]):
        path = self._resolve_sidecar_path(markdown_path, name)
        if not path.is_file():
            raise ValueError(f"required {name} sidecar is missing")
        return self._load(path, artifact_type)

    def _load_optional(self, markdown_path: Path, name: str, artifact_type: type[object]):
        path = self._resolve_sidecar_path(markdown_path, name)
        return self._load(path, artifact_type) if path.is_file() else None

    def _resolve_sidecar_path(self, markdown_path: Path, name: str) -> Path:
        path = markdown_path.with_suffix(f".{name}.json").resolve()
        if not path.is_relative_to(self._docs_normalized):
            raise ValueError(f"{name} sidecar is outside docs_normalized")
        return path

    def _load(self, path: Path, artifact_type: type[object]):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise ValueError(f"invalid JSON sidecar: {path.name}") from error
        return load_artifact(payload, artifact_type)
