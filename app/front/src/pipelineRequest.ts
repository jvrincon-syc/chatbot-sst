import { llamaCloudConfigFromRoute } from "./llamaRoutes.js";
import type { LlamaRoute } from "./llamaRoutes";

export type ProviderMode = "local" | "llama_cloud";

export type PipelineRequest = {
  force: boolean;
  providerMode: ProviderMode;
  ocrReviewThresholdPercent: number;
  llamaCloud?: {
    classifyEnabled: boolean;
    extractEnabled: boolean;
    callOrder: LlamaRoute;
  };
};

export type PipelineRequestControls = {
  force: boolean;
  providerMode: ProviderMode;
  route: LlamaRoute;
  ocrReviewThresholdPercent: number;
};

export function pipelineRequestForControls(
  controls: PipelineRequestControls,
): PipelineRequest {
  const body: PipelineRequest = {
    force: controls.force,
    providerMode: controls.providerMode,
    ocrReviewThresholdPercent: controls.ocrReviewThresholdPercent,
  };
  if (controls.providerMode === "llama_cloud") {
    body.llamaCloud = llamaCloudConfigFromRoute(controls.route);
  }
  return body;
}
