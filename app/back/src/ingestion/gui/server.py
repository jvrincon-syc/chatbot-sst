from __future__ import annotations

import cgi
import json
import shutil
from dataclasses import asdict
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from ingestion.config.env import load_runtime_llama_settings, load_secrets_env
from ingestion.config.llama_settings import LlamaSettings
from ingestion.gui.review_store import (
    ReviewDecision,
    load_review_decisions,
    save_review_decision,
)
from ingestion.manifests.writer import dump_json
from ingestion.paths import canonical_relpath
from ingestion.pipeline import run_pipeline
from ingestion.validation.normalized import validate_normalized_tree


ROOT = Path(__file__).resolve().parents[5]
DOCS_RAW = ROOT / "data" / "docs_raw"
DOCS_NORMALIZED = ROOT / "data" / "docs_normalized"
MANIFESTS_DIR = DOCS_NORMALIZED / "_manifests"
REVIEW_DECISIONS_PATH = MANIFESTS_DIR / "review_decisions.json"
GOLDEN_PATH = ROOT / "docs" / "ingestion" / "pdf_corpus_expected.json"
ALLOWED_UPLOAD_SUFFIXES = {".pdf", ".md", ".markdown"}


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def _latest_validation_report() -> dict[str, Any] | None:
    reports = sorted(
        MANIFESTS_DIR.glob("validation_*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not reports:
        return None
    payload = _read_json(reports[0], {})
    if not isinstance(payload, dict):
        return None
    return {"path": reports[0].relative_to(ROOT).as_posix(), **payload}


def _review_decision_map() -> dict[str, ReviewDecision]:
    return {
        decision.document_id: decision
        for decision in load_review_decisions(REVIEW_DECISIONS_PATH)
    }


def build_status_payload() -> dict[str, Any]:
    inventory = _read_json(MANIFESTS_DIR / "inventory.json", {})
    needs_review_manifest = _read_json(MANIFESTS_DIR / "needs_review.json", {})
    errors_manifest = _read_json(MANIFESTS_DIR / "errors.json", {})
    records = inventory.get("records", []) if isinstance(inventory, dict) else []
    review_items = (
        needs_review_manifest.get("items", [])
        if isinstance(needs_review_manifest, dict)
        else []
    )
    error_items = (
        errors_manifest.get("items", []) if isinstance(errors_manifest, dict) else []
    )
    decisions = _review_decision_map()
    review_by_id = {
        item.get("document_id"): item
        for item in review_items
        if isinstance(item, dict) and item.get("document_id")
    }

    documents = []
    for record in records:
        if not isinstance(record, dict):
            continue
        document_id = record.get("document_id", "")
        source_relpath = record.get("source_relpath", "")
        review_item = review_by_id.get(document_id, {})
        decision = decisions.get(document_id)
        documents.append(
            {
                "documentId": document_id,
                "sourceRelpath": source_relpath,
                "documentName": record.get("document_name", Path(source_relpath).name),
                "detectedExtension": record.get("detected_extension"),
                "mimeType": record.get("mime_type"),
                "category": record.get("category_inferred"),
                "fileSize": record.get("file_size", 0),
                "processingStatus": record.get("processing_status", "pending"),
                "ingestionDate": record.get("ingestion_date"),
                "reviewReasons": review_item.get("reasons", []),
                "reviewDetails": review_item.get("details", []),
                "decision": asdict(decision) if decision else None,
            }
        )

    approved = sum(1 for decision in decisions.values() if decision.decision == "approved")
    rejected = sum(1 for decision in decisions.values() if decision.decision == "rejected")
    pending_review = [
        document
        for document in documents
        if document["processingStatus"] == "needs_review" and document["decision"] is None
    ]
    summary = {
        "total": len(documents),
        "processed": sum(
            1 for document in documents if document["processingStatus"] == "processed"
        ),
        "needsReview": len(pending_review),
        "normalizedNeedsReview": sum(
            1 for document in documents if document["processingStatus"] == "needs_review"
        ),
        "failed": sum(
            1 for document in documents if document["processingStatus"] == "failed"
        ),
        "approved": approved,
        "rejected": rejected,
        "runId": needs_review_manifest.get("run_id") if isinstance(needs_review_manifest, dict) else None,
        "generatedAt": inventory.get("generated_at") if isinstance(inventory, dict) else None,
        "schemaVersion": inventory.get("schema_version") if isinstance(inventory, dict) else None,
    }

    return {
        "summary": summary,
        "llamaFirst": _llama_first_status_payload(),
        "documents": documents,
        "needsReview": pending_review,
        "errors": error_items,
        "validation": _latest_validation_report(),
        "manifests": {
            "inventory": "data/docs_normalized/_manifests/inventory.json",
            "needsReview": "data/docs_normalized/_manifests/needs_review.json",
            "errors": "data/docs_normalized/_manifests/errors.json",
            "reviewDecisions": "data/docs_normalized/_manifests/review_decisions.json",
        },
    }


def _llama_first_status_payload() -> dict[str, Any]:
    try:
        settings = load_runtime_llama_settings(ROOT / "secrets.env")
    except ValueError as exc:
        return {
            "provider": "llama_cloud",
            "configurationStatus": "invalid",
            "error": str(exc),
        }
    return {
        "provider": "llama_cloud",
        "configurationStatus": "ready" if settings.cloud_enabled else "disabled",
        "cloudEnabled": settings.cloud_enabled,
        "localFallbackEnabled": settings.local_fallback_enabled,
        "parseTier": settings.parse_tier,
        "parseVersion": settings.parse_version,
        "parseMaxCreditsPerRun": settings.parse_max_credits_per_run,
        "classifyMode": settings.classify_mode,
        "classifyMaxPages": settings.classify_max_pages,
        "extractTier": settings.extract_tier,
        "extractParseTier": settings.extract_parse_tier,
        "extractMaxPages": settings.extract_max_pages,
        "classifyEnabled": settings.classify_enabled,
        "extractEnabled": settings.extract_enabled,
        "callOrder": list(settings.call_order),
    }


class Phase1GuiHandler(BaseHTTPRequestHandler):
    server_version = "Phase1GuiApi/0.1"

    def do_OPTIONS(self) -> None:
        self._send_no_content()

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/status":
            self._send_json(build_status_payload())
            return
        self._send_error(HTTPStatus.NOT_FOUND, "endpoint not found")

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/upload":
            self._handle_upload()
            return
        if path.startswith("/api/review/"):
            document_id = unquote(path.removeprefix("/api/review/"))
            self._handle_review(document_id)
            return
        if path == "/api/pipeline/run":
            self._handle_pipeline_run()
            return
        if path == "/api/validate":
            self._handle_validate()
            return
        self._send_error(HTTPStatus.NOT_FOUND, "endpoint not found")

    def _handle_upload(self) -> None:
        content_type = self.headers.get("Content-Type", "")
        if not content_type.startswith("multipart/form-data"):
            self._send_error(HTTPStatus.BAD_REQUEST, "multipart/form-data required")
            return
        form = cgi.FieldStorage(
            fp=self.rfile,
            headers=self.headers,
            environ={
                "REQUEST_METHOD": "POST",
                "CONTENT_TYPE": content_type,
                "CONTENT_LENGTH": self.headers.get("Content-Length", "0"),
            },
        )
        category = _field_value(form, "category")
        folder = _field_value(form, "folder")
        upload = form["file"] if "file" in form else None
        if not category or not folder or upload is None or not upload.filename:
            self._send_error(HTTPStatus.BAD_REQUEST, "category, folder and file are required")
            return

        filename = Path(upload.filename).name
        suffix = Path(filename).suffix.lower()
        if suffix not in ALLOWED_UPLOAD_SUFFIXES:
            self._send_error(HTTPStatus.BAD_REQUEST, "only .pdf, .md and .markdown files are allowed")
            return
        try:
            relpath = canonical_relpath(f"{category}/{folder}/{filename}")
        except ValueError as exc:
            self._send_error(HTTPStatus.BAD_REQUEST, str(exc))
            return

        destination = DOCS_RAW / relpath
        if destination.exists():
            self._send_error(HTTPStatus.CONFLICT, "raw document already exists")
            return
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("wb") as handle:
            shutil.copyfileobj(upload.file, handle)
        self._send_json(
            {
                "ok": True,
                "sourceRelpath": relpath,
                "path": destination.relative_to(ROOT).as_posix(),
            },
            status=HTTPStatus.CREATED,
        )

    def _handle_review(self, document_id: str) -> None:
        if not document_id:
            self._send_error(HTTPStatus.BAD_REQUEST, "document_id is required")
            return
        try:
            body = self._read_json_body()
        except (json.JSONDecodeError, ValueError) as exc:
            self._send_error(HTTPStatus.BAD_REQUEST, str(exc))
            return
        decision_value = body.get("decision")
        reason = str(body.get("reason", "")).strip()
        document = _find_document(document_id)
        if document is None:
            self._send_error(HTTPStatus.NOT_FOUND, "document not found in inventory")
            return
        try:
            decision = ReviewDecision(
                document_id=document_id,
                source_relpath=document["sourceRelpath"],
                decision=decision_value,
                reason=reason,
                decided_at=_now(),
            )
        except (TypeError, ValueError) as exc:
            self._send_error(HTTPStatus.BAD_REQUEST, str(exc))
            return
        save_review_decision(REVIEW_DECISIONS_PATH, decision)
        self._send_json({"ok": True, "decision": asdict(decision), "status": build_status_payload()})

    def _handle_pipeline_run(self) -> None:
        try:
            body = self._read_json_body(required=False)
        except (json.JSONDecodeError, ValueError) as exc:
            self._send_error(HTTPStatus.BAD_REQUEST, str(exc))
            return
        only_sources = body.get("onlySources")
        if only_sources is not None and not isinstance(only_sources, list):
            self._send_error(HTTPStatus.BAD_REQUEST, "onlySources must be a list")
            return
        try:
            llama_settings = _llama_settings_for_pipeline_run(body)
        except ValueError as exc:
            self._send_error(HTTPStatus.BAD_REQUEST, str(exc))
            return
        run_id = "gui_phase1_" + datetime.now(timezone.utc).astimezone().strftime("%Y%m%d_%H%M%S")
        staging_root = ROOT / ".tmp" / run_id
        try:
            summary = run_pipeline(
                docs_raw=DOCS_RAW,
                docs_normalized=DOCS_NORMALIZED,
                staging_root=staging_root,
                promote=False,
                only_sources=only_sources,
                force=bool(body.get("force", False)),
                corpus_version="phase1-main",
                pipeline_version="2.0.0",
                run_id=run_id,
                llama_settings_override=llama_settings,
            )
        except Exception as exc:
            self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))
            return
        self._send_json(
            {
                "ok": True,
                "runId": run_id,
                "summary": summary,
                "stagingRoot": staging_root.relative_to(ROOT).as_posix(),
            }
        )

    def _handle_validate(self) -> None:
        run_id = "gui_validation_" + datetime.now(timezone.utc).astimezone().strftime("%Y%m%d_%H%M%S")
        try:
            report = validate_normalized_tree(
                DOCS_NORMALIZED,
                raw_root=DOCS_RAW,
                mode="closure",
                golden_path=GOLDEN_PATH if GOLDEN_PATH.exists() else None,
                run_id=run_id,
            )
            output = MANIFESTS_DIR / f"validation_{run_id}.json"
            dump_json(output, report)
        except Exception as exc:
            self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))
            return
        self._send_json(
            {
                "ok": report.status == "passed",
                "status": report.status,
                "errors": report.errors,
                "runId": run_id,
                "path": output.relative_to(ROOT).as_posix(),
            }
        )

    def _read_json_body(self, *, required: bool = True) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length == 0:
            if required:
                raise ValueError("JSON body is required")
            return {}
        payload = self.rfile.read(length)
        return json.loads(payload.decode("utf-8"))

    def _send_json(self, payload: Any, *, status: HTTPStatus = HTTPStatus.OK) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._send_common_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_no_content(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self._send_common_headers()
        self.end_headers()

    def _send_error(self, status: HTTPStatus, message: str) -> None:
        self._send_json({"ok": False, "error": message}, status=status)

    def _send_common_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "http://127.0.0.1:5173")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def log_message(self, format: str, *args: Any) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] {self.address_string()} {format % args}")


def _field_value(form: cgi.FieldStorage, name: str) -> str:
    field = form[name] if name in form else None
    if field is None or isinstance(field, list):
        return ""
    value = field.value
    return value.strip() if isinstance(value, str) else ""


def _find_document(document_id: str) -> dict[str, Any] | None:
    for document in build_status_payload()["documents"]:
        if document["documentId"] == document_id:
            return document
    return None


def _llama_settings_for_pipeline_run(body: dict[str, Any]) -> LlamaSettings:
    provider_mode = body.get("providerMode")
    try:
        settings = load_runtime_llama_settings(ROOT / "secrets.env")
    except ValueError:
        if provider_mode != "local":
            raise
        settings = LlamaSettings(cloud_enabled=False)
    if provider_mode is None:
        return settings
    if provider_mode not in {"local", "llama_cloud"}:
        raise ValueError("providerMode must be 'local' or 'llama_cloud'")

    data = settings.model_dump()
    data["api_key"] = settings.api_key.get_secret_value() if settings.api_key else None
    data["cloud_enabled"] = provider_mode == "llama_cloud"

    llama_cloud = body.get("llamaCloud", {})
    if llama_cloud is None:
        llama_cloud = {}
    if not isinstance(llama_cloud, dict):
        raise ValueError("llamaCloud must be an object")
    if "classifyEnabled" in llama_cloud:
        data["classify_enabled"] = bool(llama_cloud["classifyEnabled"])
    if "extractEnabled" in llama_cloud:
        data["extract_enabled"] = bool(llama_cloud["extractEnabled"])
    if "callOrder" in llama_cloud:
        call_order = llama_cloud["callOrder"]
        if isinstance(call_order, list):
            data["call_order"] = tuple(str(stop) for stop in call_order)
        else:
            data["call_order"] = str(call_order)
    return LlamaSettings(**data)


def main() -> int:
    load_secrets_env(ROOT / "secrets.env")
    host = "127.0.0.1"
    port = 8765
    server = ThreadingHTTPServer((host, port), Phase1GuiHandler)
    print(f"Phase 1 GUI API listening on http://{host}:{port}")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
