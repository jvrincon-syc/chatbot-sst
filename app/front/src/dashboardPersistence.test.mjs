import assert from "node:assert/strict";

import {
  createStatusDrivenDashboardPreferences,
  resolveDashboardPreferences,
} from "../.tmp-tests/features/dashboard/dashboardPersistence.js";

function test(name, assertion) {
  try {
    assertion();
    console.log(`ok - ${name}`);
  } catch (error) {
    console.error(`not ok - ${name}`);
    throw error;
  }
}

const status = {
  llamaFirst: {
    cloudEnabled: false,
    callOrder: ["parse"],
  },
  settings: {
    ocrReviewThresholdPercent: 91,
    llamaControls: {
      providerMode: "llama_cloud",
      route: "classify,parse,extract",
    },
  },
};

test("uses status defaults when no stored dashboard preferences exist", () => {
  const preferences = resolveDashboardPreferences({
    stored: null,
    status,
  });

  assert.equal(preferences.activeView, "review");
  assert.equal(preferences.llamaControls.providerMode, "llama_cloud");
  assert.equal(preferences.llamaControls.route, "classify,parse,extract");
  assert.equal(preferences.ocrThresholdInput, "91");
});

test("keeps stored ui preferences while status drives operational settings", () => {
  const stored = createStatusDrivenDashboardPreferences(null);
  stored.activeView = "inventory";
  stored.llamaControls.providerMode = "local";
  stored.llamaControls.route = "parse";
  stored.ocrThresholdInput = "77.5";
  stored.selectedDocumentIds.review = "doc-review";
  stored.selectedDocumentIds.inventory = "doc-inventory";

  const preferences = resolveDashboardPreferences({
    stored,
    status,
  });

  assert.equal(preferences.activeView, "inventory");
  assert.deepEqual(preferences.selectedDocumentIds, stored.selectedDocumentIds);
  assert.equal(preferences.llamaControls.providerMode, "llama_cloud");
  assert.equal(preferences.llamaControls.route, "classify,parse,extract");
  assert.equal(preferences.ocrThresholdInput, "91");
});

test("preserves chunking as a stored dashboard view", () => {
  const stored = createStatusDrivenDashboardPreferences(null);
  stored.activeView = "chunking";

  const preferences = resolveDashboardPreferences({
    stored,
    status,
  });

  assert.equal(preferences.activeView, "chunking");
});
