import { pipelineRequestForControls } from "../../pipelineRequest.js";
import { readJsonResponse } from "../../shared/readJsonResponse.js";
async function readJson(response) {
    const payload = await readJsonResponse(response);
    const envelope = payload && typeof payload === "object" ? payload : {};
    if (!response.ok) {
        throw new Error(envelope.error ?? `HTTP ${response.status}`);
    }
    return payload;
}
export async function loadDashboardStatus() {
    const response = await fetch("/api/status");
    return readJson(response);
}
export async function uploadDashboardDocument(form) {
    const body = new FormData();
    body.append("category", form.category.trim());
    body.append("folder", form.folder.trim());
    body.append("file", form.file);
    const response = await fetch("/api/upload", {
        method: "POST",
        body,
    });
    return readJson(response);
}
export async function submitDashboardReview(options) {
    const response = await fetch(`/api/review/${options.documentId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            decision: options.decision,
            reason: options.reason,
        }),
    });
    return readJson(response);
}
export async function runDashboardPipeline(options) {
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
    return readJson(response);
}
export async function saveDashboardSettings(options) {
    const response = await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            ocrReviewThresholdPercent: options.ocrReviewThresholdPercent,
            providerMode: options.llamaControls.providerMode,
            route: options.llamaControls.route,
        }),
    });
    return readJson(response);
}
export async function validateDashboardBundle(options) {
    const response = await fetch("/api/validate", {
        method: "POST",
        headers: options.stagingRoot ? { "Content-Type": "application/json" } : undefined,
        body: options.stagingRoot ? JSON.stringify({ stagingRoot: options.stagingRoot }) : undefined,
    });
    return readJson(response);
}
export async function promoteDashboardStaging(options) {
    const response = await fetch("/api/promote", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ stagingRoot: options.stagingRoot }),
    });
    return readJson(response);
}
