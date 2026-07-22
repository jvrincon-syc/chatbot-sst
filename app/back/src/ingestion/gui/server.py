from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from typing import Any, BinaryIO
from urllib.parse import unquote, urlparse

from ingestion.config.env import load_runtime_llama_settings, load_secrets_env
from ingestion.config.llama_settings import LlamaSettings
from ingestion.gui.review_store import (
    ReviewDecision,
    load_review_decisions,
    save_review_decision,
)
from ingestion.manifests.writer import dump_json, write_text_atomic
from ingestion.pipeline import DEFAULT_OCR_REVIEW_THRESHOLD
from ingestion.paths import canonical_relpath
from ingestion.pipeline import run_pipeline
from ingestion.promotion import PromotionError, promote_candidate
from ingestion.validation.normalized import validate_normalized_tree


ROOT = Path(__file__).resolve().parents[5]
DOCS_RAW = ROOT / "data" / "docs_raw"
DOCS_NORMALIZED = ROOT / "data" / "docs_normalized"
MANIFESTS_DIR = DOCS_NORMALIZED / "_manifests"
REVIEW_DECISIONS_PATH = MANIFESTS_DIR / "review_decisions.json"
GUI_SETTINGS_PATH = MANIFESTS_DIR / "gui_settings.json"
ALLOWED_UPLOAD_SUFFIXES = {".pdf", ".md", ".markdown"}


@dataclass
class UploadedFormFile:
    filename: str
    file: BytesIO


@dataclass(frozen=True)
class ValidationTarget:
    name: str
    normalized_root: Path
    manifests_dir: Path


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
                **_ingestion_details_for_record(record),
                **_document_ocr_confidence_for_record(record),
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
        "settings": _gui_settings_payload(),
        "documents": documents,
        "needsReview": pending_review,
        "errors": error_items,
        "validation": _latest_validation_report(),
        "manifests": {
            "inventory": "data/docs_normalized/_manifests/inventory.json",
            "needsReview": "data/docs_normalized/_manifests/needs_review.json",
            "errors": "data/docs_normalized/_manifests/errors.json",
            "reviewDecisions": "data/docs_normalized/_manifests/review_decisions.json",
            "guiSettings": "data/docs_normalized/_manifests/gui_settings.json",
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
        if path == "/api/settings":
            self._handle_settings()
            return
        if path == "/api/validate":
            self._handle_validate()
            return
        if path == "/api/promote":
            self._handle_promote()
            return
        self._send_error(HTTPStatus.NOT_FOUND, "endpoint not found")

    def _handle_upload(self) -> None:
        content_type = self.headers.get("Content-Type", "")
        if not content_type.startswith("multipart/form-data"):
            self._send_error(HTTPStatus.BAD_REQUEST, "multipart/form-data required")
            return
        form = _parse_multipart_form(
            content_type=content_type,
            content_length=self.headers.get("Content-Length", "0"),
            body=self.rfile,
        )
        category = _field_value(form, "category")
        folder = _field_value(form, "folder")
        upload = form.get("file")
        if (
            not category
            or not folder
            or not isinstance(upload, UploadedFormFile)
            or not upload.filename
        ):
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
            pipeline_options = _pipeline_run_options_from_body(body)
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
                ocr_review_threshold=pipeline_options["ocr_review_threshold"],
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
        try:
            body = self._read_json_body(required=False)
            target = _validation_target_from_body(body)
        except (json.JSONDecodeError, ValueError) as exc:
            self._send_error(HTTPStatus.BAD_REQUEST, str(exc))
            return
        run_id = "gui_validation_" + datetime.now(timezone.utc).astimezone().strftime("%Y%m%d_%H%M%S")
        try:
            report, output = _write_validation_report(target, run_id)
        except Exception as exc:
            self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))
            return
        payload = {
            "ok": report.status == "passed",
            "status": report.status,
            "errors": report.errors,
            "runId": run_id,
            "path": output.relative_to(ROOT).as_posix(),
            "target": target.name,
        }
        if target.name == "staging":
            payload["stagingRoot"] = target.normalized_root.relative_to(ROOT).as_posix()
        self._send_json(payload)

    def _handle_promote(self) -> None:
        try:
            body = self._read_json_body()
            target = _staging_target_from_body(body)
        except (json.JSONDecodeError, ValueError) as exc:
            self._send_error(HTTPStatus.BAD_REQUEST, str(exc))
            return
        run_id = "gui_promotion_" + datetime.now(timezone.utc).astimezone().strftime("%Y%m%d_%H%M%S")
        try:
            report, output = _write_validation_report(target, run_id)
            if report.status != "passed":
                self._send_json(
                    {
                        "ok": False,
                        "status": report.status,
                        "errors": report.errors,
                        "runId": run_id,
                        "path": output.relative_to(ROOT).as_posix(),
                        "target": target.name,
                    },
                    status=HTTPStatus.CONFLICT,
                )
                return
            promote_candidate(
                target.normalized_root,
                DOCS_NORMALIZED,
                {
                    "structural_status": report.status,
                    "run_id": run_id,
                    "validation_path": output.relative_to(ROOT).as_posix(),
                },
            )
        except PromotionError as exc:
            self._send_error(HTTPStatus.CONFLICT, str(exc))
            return
        except Exception as exc:
            self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))
            return
        self._send_json(
            {
                "ok": True,
                "status": "promoted",
                "errors": report.errors,
                "runId": run_id,
                "path": DOCS_NORMALIZED.relative_to(ROOT).as_posix(),
                "sourceStagingRoot": target.normalized_root.relative_to(ROOT).as_posix(),
                "validationPath": (DOCS_NORMALIZED / "_manifests" / output.name)
                .relative_to(ROOT)
                .as_posix(),
                "target": "official",
            }
        )

    def _handle_settings(self) -> None:
        try:
            body = self._read_json_body()
            settings = _save_gui_settings(body)
        except (json.JSONDecodeError, ValueError) as exc:
            self._send_error(HTTPStatus.BAD_REQUEST, str(exc))
            return
        self._send_json({"ok": True, "settings": settings, "status": build_status_payload()})

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


def _parse_multipart_form(
    *,
    content_type: str,
    content_length: str,
    body: BinaryIO,
) -> dict[str, str | UploadedFormFile]:
    try:
        length = int(content_length or "0")
    except ValueError:
        length = 0
    raw_body = body.read(max(length, 0))
    message = BytesParser(policy=policy.default).parsebytes(
        b"Content-Type: "
        + content_type.encode("utf-8")
        + b"\r\nMIME-Version: 1.0\r\n\r\n"
        + raw_body
    )
    form: dict[str, str | UploadedFormFile] = {}
    for part in message.iter_parts():
        if part.get_content_disposition() != "form-data":
            continue
        name = part.get_param("name", header="content-disposition")
        if not name:
            continue
        payload = part.get_payload(decode=True) or b""
        filename = part.get_filename()
        if filename is not None:
            form[name] = UploadedFormFile(filename=filename, file=BytesIO(payload))
            continue
        charset = part.get_content_charset() or "utf-8"
        form[name] = payload.decode(charset, errors="replace")
    return form


def _field_value(form: dict[str, str | UploadedFormFile], name: str) -> str:
    field = form.get(name)
    if not isinstance(field, str):
        return ""
    return field.strip()


def _find_document(document_id: str) -> dict[str, Any] | None:
    for document in build_status_payload()["documents"]:
        if document["documentId"] == document_id:
            return document
    return None


def _gui_settings_payload(
    *,
    settings_path: Path = GUI_SETTINGS_PATH,
) -> dict[str, float]:
    payload = _read_json(settings_path, {})
    threshold = DEFAULT_OCR_REVIEW_THRESHOLD
    if isinstance(payload, dict):
        raw_threshold = payload.get("ocr_review_threshold")
        if isinstance(raw_threshold, (int, float)) and not isinstance(raw_threshold, bool):
            threshold = float(raw_threshold)
    threshold = _validate_threshold_ratio(threshold)
    return {
        "ocrReviewThreshold": threshold,
        "ocrReviewThresholdPercent": round(threshold * 100, 1),
    }


def _save_gui_settings(
    body: dict[str, Any],
    *,
    settings_path: Path = GUI_SETTINGS_PATH,
) -> dict[str, float]:
    if not isinstance(body, dict):
        raise ValueError("settings body must be an object")
    threshold = _threshold_ratio_from_body(body)
    payload = {
        "ocr_review_threshold": threshold,
        "updated_at": _now(),
    }
    write_text_atomic(
        settings_path,
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    return _gui_settings_payload(settings_path=settings_path)


def _pipeline_run_options_from_body(
    body: dict[str, Any],
    *,
    settings_path: Path = GUI_SETTINGS_PATH,
) -> dict[str, float]:
    if "ocrReviewThresholdPercent" in body or "ocrReviewThreshold" in body:
        threshold = _threshold_ratio_from_body(body)
    else:
        threshold = _gui_settings_payload(settings_path=settings_path)[
            "ocrReviewThreshold"
        ]
    return {"ocr_review_threshold": threshold}


def _threshold_ratio_from_body(body: dict[str, Any]) -> float:
    if "ocrReviewThresholdPercent" in body:
        raw = body["ocrReviewThresholdPercent"]
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise ValueError("ocrReviewThresholdPercent must be numeric")
        return _validate_threshold_ratio(float(raw) / 100)
    if "ocrReviewThreshold" in body:
        raw = body["ocrReviewThreshold"]
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise ValueError("ocrReviewThreshold must be numeric")
        return _validate_threshold_ratio(float(raw))
    raise ValueError("ocrReviewThresholdPercent is required")


def _validate_threshold_ratio(value: float) -> float:
    if value < 0 or value > 1:
        raise ValueError("OCR review threshold must be between 0 and 100 percent")
    return value


def _document_ocr_confidence_for_record(
    record: dict[str, Any],
    *,
    normalized_root: Path = DOCS_NORMALIZED,
) -> dict[str, Any]:
    metric = _ocr_confidence_metric_for_record(record, normalized_root=normalized_root)
    kind = str(metric.get("kind", "unavailable") or "unavailable")
    value = metric.get("value")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return {
            "ocrConfidenceKind": kind,
            "ocrConfidenceValue": None,
            "ocrConfidencePercent": None,
            "ocrConfidenceLabel": "N/A",
        }
    percent = round(float(value) * 100, 1)
    return {
        "ocrConfidenceKind": kind,
        "ocrConfidenceValue": float(value),
        "ocrConfidencePercent": percent,
        "ocrConfidenceLabel": f"{percent:.1f}%",
    }


def _ocr_confidence_metric_for_record(
    record: dict[str, Any],
    *,
    normalized_root: Path,
) -> dict[str, Any]:
    inventory_metric = record.get("ocr_confidence")
    if isinstance(inventory_metric, dict):
        return inventory_metric

    source_relpath = str(record.get("source_relpath", "") or "")
    if not source_relpath:
        return {"kind": "unavailable", "value": None}
    base_path = normalized_root / Path(source_relpath)

    metadata = _read_json(base_path.with_suffix(".metadata.json"), {})
    if isinstance(metadata, dict) and isinstance(metadata.get("ocr_confidence"), dict):
        return metadata["ocr_confidence"]

    ocr = _read_json(base_path.with_suffix(".ocr.json"), {})
    if isinstance(ocr, dict):
        document_confidence = ocr.get("document_confidence")
        if isinstance(document_confidence, dict):
            return document_confidence
        page_values = [
            page.get("confidence", {}).get("value")
            for page in ocr.get("pages", [])
            if isinstance(page, dict) and isinstance(page.get("confidence"), dict)
        ]
        measured_values = [
            float(value)
            for value in page_values
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        ]
        if measured_values:
            return {
                "kind": "estimated",
                "value": sum(measured_values) / len(measured_values),
                "method": "page_confidence_average",
            }

    return {"kind": "unavailable", "value": None}


def _ingestion_details_for_record(
    record: dict[str, Any],
    *,
    normalized_root: Path = DOCS_NORMALIZED,
) -> dict[str, str]:
    source_relpath = str(record.get("source_relpath", "") or "")
    metadata = _read_json(
        (normalized_root / Path(source_relpath)).with_suffix(".metadata.json"),
        {},
    )
    method = (
        str(metadata.get("extraction_method", "") or "")
        if isinstance(metadata, dict)
        else ""
    )
    if method == "llamaparse":
        return _ingestion_details(
            provider="llama_cloud",
            provider_label="LlamaCloud",
            method=method,
            method_label="LlamaParse",
        )
    if method == "hybrid_llamaparse":
        return _ingestion_details(
            provider="llama_cloud",
            provider_label="LlamaCloud",
            method=method,
            method_label="LlamaParse + OCR local",
        )
    local_labels = {
        "markdown": "Markdown local",
        "pdf_digital": "PDF digital local",
        "ocr": "OCR Tesseract local",
        "hybrid": "PDF digital + OCR regional",
    }
    if method in local_labels:
        return _ingestion_details(
            provider="local",
            provider_label="Local",
            method=method,
            method_label=local_labels[method],
        )
    return _ingestion_details(
        provider="unregistered",
        provider_label="Sin ingesta",
        method=method or "unregistered",
        method_label="Sin metadata normalizada",
    )


def _ingestion_details(
    *,
    provider: str,
    provider_label: str,
    method: str,
    method_label: str,
) -> dict[str, str]:
    return {
        "ingestionProvider": provider,
        "ingestionProviderLabel": provider_label,
        "ingestionMethod": method,
        "ingestionMethodLabel": method_label,
    }


def _validation_target_from_body(body: dict[str, Any]) -> ValidationTarget:
    staging_root = body.get("stagingRoot")
    if staging_root is None or str(staging_root).strip() == "":
        return ValidationTarget(
            name="official",
            normalized_root=DOCS_NORMALIZED,
            manifests_dir=MANIFESTS_DIR,
        )
    candidate = (ROOT / str(staging_root)).resolve()
    tmp_root = (ROOT / ".tmp").resolve()
    if not candidate.is_relative_to(tmp_root):
        raise ValueError("stagingRoot must stay under .tmp")
    return ValidationTarget(
        name="staging",
        normalized_root=candidate,
        manifests_dir=candidate / "_manifests",
    )


def _staging_target_from_body(body: dict[str, Any]) -> ValidationTarget:
    target = _validation_target_from_body(body)
    if target.name != "staging":
        raise ValueError("stagingRoot is required")
    return target


def _write_validation_report(target: ValidationTarget, run_id: str):
    report = validate_normalized_tree(
        target.normalized_root,
        raw_root=DOCS_RAW,
        mode="closure",
        run_id=run_id,
    )
    target.manifests_dir.mkdir(parents=True, exist_ok=True)
    output = target.manifests_dir / f"validation_{run_id}.json"
    dump_json(output, report)
    return report, output


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
    data["local_fallback_enabled"] = provider_mode != "llama_cloud"

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
