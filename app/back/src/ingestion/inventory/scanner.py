from __future__ import annotations

import hashlib
import mimetypes
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional

from ingestion.schemas.inventory import InventoryRecord


PDF_SIGNATURE = b"%PDF"
MARKDOWN_EXTENSIONS = {".md", ".markdown"}


def compute_content_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def detect_extension(path: Path) -> Optional[str]:
    suffix = path.suffix.lower()
    if suffix:
        return ".md" if suffix in MARKDOWN_EXTENSIONS else suffix
    with path.open("rb") as handle:
        signature = handle.read(8)
    if signature.startswith(PDF_SIGNATURE):
        return ".pdf"
    return None


def detect_mime_type(path: Path, detected_extension: Optional[str]) -> str:
    if detected_extension == ".pdf":
        return "application/pdf"
    if detected_extension == ".md":
        return "text/markdown"
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or "application/octet-stream"


def stable_document_id(relative_path: Path, content_hash: str = "") -> str:
    identity = relative_path.as_posix().encode("utf-8")
    return "doc_" + hashlib.sha1(identity).hexdigest()[:16]


def infer_category(relative_path: Path) -> str:
    return relative_path.parts[0] if len(relative_path.parts) > 1 else "root"


def iter_files(root: Path) -> Iterable[Path]:
    return (path for path in sorted(root.rglob("*")) if path.is_file())


def scan_docs_raw(
    docs_raw: Path,
    *,
    corpus_version: str,
    pipeline_version: str,
    ingestion_date: Optional[datetime] = None,
) -> List[InventoryRecord]:
    timestamp = ingestion_date or datetime.now(timezone.utc).astimezone()
    records: List[InventoryRecord] = []
    for path in iter_files(docs_raw):
        relative_path = path.relative_to(docs_raw)
        content_hash = compute_content_hash(path)
        detected_extension = detect_extension(path)
        reported_extension = path.suffix.lower() or None
        records.append(
            InventoryRecord(
                document_id=stable_document_id(relative_path, content_hash),
                source_path=str(path),
                document_name=path.name,
                detected_extension=detected_extension,
                reported_extension=reported_extension,
                mime_type=detect_mime_type(path, detected_extension),
                content_hash=content_hash,
                file_size=path.stat().st_size,
                ingestion_date=timestamp.isoformat(),
                category_inferred=infer_category(relative_path),
                document_version=None,
                page_count=None,
                processing_status="pending",
                pipeline_version=pipeline_version,
                corpus_version=corpus_version,
            )
        )
    return records
