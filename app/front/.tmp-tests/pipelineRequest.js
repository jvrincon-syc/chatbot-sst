import { llamaCloudConfigFromRoute } from "./llamaRoutes.js";
export function pipelineRequestForControls(controls) {
    const body = {
        force: controls.force,
        providerMode: controls.providerMode,
        ocrReviewThresholdPercent: controls.ocrReviewThresholdPercent,
    };
    if (controls.providerMode === "llama_cloud") {
        body.llamaCloud = llamaCloudConfigFromRoute(controls.route);
    }
    return body;
}
