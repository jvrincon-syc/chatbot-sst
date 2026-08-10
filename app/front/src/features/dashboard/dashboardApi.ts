import { pipelineRequestForControls } from "../../pipelineRequest";
import { readJsonResponse } from "../../shared/readJsonResponse.js";
import type {
  ActionResult,
  DashboardUploadForm,
  LlamaControls,
  StatusPayload,
} from "./dashboardTypes";

async function readJson<T>(response: Response): Promise<T> {
  const payload = (await readJsonResponse(response)) as T & { error?: string };
  if (!response.ok) {
    throw new Error(payload.error ?? `HTTP ${response.status}`);
  }
  return payload;
}

export async function loadDashboardStatus(): Promise<StatusPayload> {
  const response = await fetch("/api/status");
  return readJson<StatusPayload>(response);
}

export async function uploadDashboardDocument(
  form: DashboardUploadForm,
): Promise<ActionResult> {
  const body = new FormData();
  body.append("category", form.category.trim());
  body.append("folder", form.folder.trim());
  body.append("file", form.file as File);

  const response = await fetch("/api/upload", {
    method: "POST",
    body,
  });
  return readJson<ActionResult>(response);
}

export async function submitDashboardReview(options: {
  documentId: string;
  decision: "approved" | "rejected";
  reason: string;
}): Promise<ActionResult> {
  const response = await fetch(`/api/review/${options.documentId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      decision: options.decision,
      reason: options.reason,
    }),
  });
  return readJson<ActionResult>(response);
}

export async function runDashboardPipeline(options: {
  controls: LlamaControls;
  ocrReviewThresholdPercent: number;
}): Promise<ActionResult> {
  const body = pipelineRequestForControls({
    force: false,
    providerMode: options.controls.providerMode,
    route: options.controls.route,
    ocrReviewThresholdPercent: options.ocrReviewThresholdPercent,
  });

  const response = await fetch("/api/pipeline/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return readJson<ActionResult>(response);
}

export async function saveDashboardSettings(options: {
  ocrReviewThresholdPercent: number;
  llamaControls: LlamaControls;
}): Promise<{
  ok?: boolean;
  settings?: StatusPayload["settings"];
  status?: StatusPayload;
}> {
  const response = await fetch("/api/settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      ocrReviewThresholdPercent: options.ocrReviewThresholdPercent,
      providerMode: options.llamaControls.providerMode,
      route: options.llamaControls.route,
    }),
  });
  return readJson<{
    ok?: boolean;
    settings?: StatusPayload["settings"];
    status?: StatusPayload;
  }>(response);
}

export async function validateDashboardBundle(options: {
  stagingRoot?: string | null;
}): Promise<ActionResult> {
  const response = await fetch("/api/validate", {
    method: "POST",
    headers: options.stagingRoot ? { "Content-Type": "application/json" } : undefined,
    body: options.stagingRoot ? JSON.stringify({ stagingRoot: options.stagingRoot }) : undefined,
  });
  return readJson<ActionResult>(response);
}

export async function promoteDashboardStaging(options: {
  stagingRoot: string;
}): Promise<ActionResult> {
  const response = await fetch("/api/promote", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ stagingRoot: options.stagingRoot }),
  });
  return readJson<ActionResult>(response);
}
