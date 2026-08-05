import assert from "node:assert/strict";

import { pipelineRequestForControls } from "../.tmp-tests/pipelineRequest.js";

function test(name, assertion) {
  try {
    assertion();
    console.log(`ok - ${name}`);
  } catch (error) {
    console.error(`not ok - ${name}`);
    throw error;
  }
}

test("builds the LlamaCloud pipeline payload for parse classify extract", () => {
  assert.deepEqual(
    pipelineRequestForControls({
      force: false,
      providerMode: "llama_cloud",
      route: "parse,classify,extract",
      ocrReviewThresholdPercent: 82.5,
    }),
    {
      force: false,
      providerMode: "llama_cloud",
      ocrReviewThresholdPercent: 82.5,
      llamaCloud: {
        classifyEnabled: true,
        extractEnabled: true,
        callOrder: "parse,classify,extract",
      },
    },
  );
});

test("does not attach LlamaCloud config for local pipeline runs", () => {
  assert.deepEqual(
    pipelineRequestForControls({
      force: false,
      providerMode: "local",
      route: "parse,classify,extract",
      ocrReviewThresholdPercent: 80,
    }),
    {
      force: false,
      providerMode: "local",
      ocrReviewThresholdPercent: 80,
    },
  );
});
