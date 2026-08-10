import assert from "node:assert/strict";

import {
  readDashboardPreferences,
  createStatusDrivenDashboardPreferences,
  resolveDashboardPreferences,
  writeDashboardPreferences,
} from "../.tmp-tests/features/dashboard/dashboardPersistence.js";
import { createDefaultDashboardPreferences, viewTitles } from "../.tmp-tests/features/dashboard/dashboardTypes.js";
import {
  DASHBOARD_VIEWS,
  isDashboardView,
} from "../.tmp-tests/features/dashboard/dashboardNavigation.js";

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

const STORAGE_KEY_V1 = "chatbot-sst.dashboard.preferences.v1";
const STORAGE_KEY_V2 = "chatbot-sst.dashboard.preferences.v2";

function withMockWindow(initialEntries, assertion) {
  const store = new Map(Object.entries(initialEntries));
  const previousWindow = globalThis.window;
  const windowMock = {
    localStorage: {
      getItem(key) {
        return store.has(key) ? store.get(key) : null;
      },
      setItem(key, value) {
        store.set(key, String(value));
      },
      removeItem(key) {
        store.delete(key);
      },
    },
  };

  globalThis.window = windowMock;
  try {
    assertion({
      getItem(key) {
        return store.has(key) ? store.get(key) : null;
      },
      entries() {
        return Object.fromEntries(store);
      },
    });
  } finally {
    if (previousWindow === undefined) {
      delete globalThis.window;
    } else {
      globalThis.window = previousWindow;
    }
  }
}

test("uses status defaults when no stored dashboard preferences exist", () => {
  const preferences = resolveDashboardPreferences({
    stored: null,
    status,
  });

  assert.equal(preferences.activeView, "review");
  assert.equal(preferences.llamaControls.providerMode, "llama_cloud");
  assert.equal(preferences.llamaControls.route, "classify,parse,extract");
  assert.equal(preferences.ocrThresholdInput, "91");
  assert.equal(preferences.embeddingIndexing.activeStage, "embedding");
});

test("keeps stored ui preferences while status drives operational settings", () => {
  const stored = createStatusDrivenDashboardPreferences(null);
  stored.activeView = "inventory";
  stored.llamaControls.providerMode = "local";
  stored.llamaControls.route = "parse";
  stored.ocrThresholdInput = "77.5";
  stored.selectedDocumentIds.review = "doc-review";
  stored.selectedDocumentIds.inventory = "doc-inventory";
  stored.embeddingIndexing.activeStage = "retrieval";
  stored.embeddingIndexing.selectedEmbeddingProfileId = "local-bge-m3-v1";
  stored.embeddingIndexing.selectedChunkBundleId = "chunk-bundle-1";
  stored.embeddingIndexing.activeEmbeddingRunId = "embedding-run-1";
  stored.embeddingIndexing.selectedEmbeddingBundleId = "embedding-bundle-1";
  stored.embeddingIndexing.activeIndexingRunId = "indexing-run-1";
  stored.embeddingIndexing.activeActivationRunId = "indexing-run-1";
  stored.embeddingIndexing.selectedRetrievalProfileId = "retrieval-profile-1";

  const preferences = resolveDashboardPreferences({
    stored,
    status,
  });

  assert.equal(preferences.activeView, "inventory");
  assert.deepEqual(preferences.selectedDocumentIds, stored.selectedDocumentIds);
  assert.equal(preferences.embeddingIndexing.activeStage, "retrieval");
  assert.equal(preferences.embeddingIndexing.selectedEmbeddingProfileId, "local-bge-m3-v1");
  assert.equal(preferences.embeddingIndexing.selectedChunkBundleId, "chunk-bundle-1");
  assert.equal(preferences.embeddingIndexing.activeEmbeddingRunId, "embedding-run-1");
  assert.equal(preferences.embeddingIndexing.selectedEmbeddingBundleId, "embedding-bundle-1");
  assert.equal(preferences.embeddingIndexing.activeIndexingRunId, "indexing-run-1");
  assert.equal(preferences.embeddingIndexing.activeActivationRunId, "indexing-run-1");
  assert.equal(preferences.embeddingIndexing.selectedRetrievalProfileId, "retrieval-profile-1");
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

test("preserves embedding-indexing as a stored dashboard view", () => {
  const stored = createStatusDrivenDashboardPreferences(null);
  stored.activeView = "embedding-indexing";
  stored.embeddingIndexing.activeStage = "activation";
  stored.embeddingIndexing.selectedEmbeddingProfileId = "local-bge-m3-v1";
  stored.embeddingIndexing.selectedChunkBundleId = "chunk-bundle-1";

  const preferences = resolveDashboardPreferences({
    stored,
    status,
  });

  assert.equal(preferences.activeView, "embedding-indexing");
  assert.equal(preferences.embeddingIndexing.activeStage, "activation");
  assert.equal(preferences.embeddingIndexing.selectedEmbeddingProfileId, "local-bge-m3-v1");
  assert.equal(preferences.embeddingIndexing.selectedChunkBundleId, "chunk-bundle-1");
});

test("migrates dashboard preferences from v1 to v2 with minimal embedding-indexing state", () => {
  withMockWindow(
    {
      [STORAGE_KEY_V1]: JSON.stringify({
        activeView: "chunking",
        selectedDocumentIds: {
          review: "doc-review",
          inventory: "doc-inventory",
        },
      }),
    },
    (storage) => {
      const preferences = readDashboardPreferences();

      assert.equal(preferences?.activeView, "chunking");
      assert.deepEqual(preferences?.selectedDocumentIds, {
        review: "doc-review",
        inventory: "doc-inventory",
      });
      assert.equal(preferences?.embeddingIndexing.activeStage, "embedding");
      assert.equal(preferences?.embeddingIndexing.selectedEmbeddingProfileId, null);
      assert.equal(preferences?.embeddingIndexing.selectedChunkBundleId, null);
      assert.equal(preferences?.embeddingIndexing.activeEmbeddingRunId, null);
      assert.equal(preferences?.embeddingIndexing.selectedEmbeddingBundleId, null);
      assert.equal(preferences?.embeddingIndexing.activeIndexingRunId, null);
      assert.equal(preferences?.embeddingIndexing.activeActivationRunId, null);
      assert.equal(preferences?.embeddingIndexing.selectedRetrievalProfileId, null);
      assert.equal(storage.getItem(STORAGE_KEY_V1), null);
      assert.deepEqual(JSON.parse(storage.getItem(STORAGE_KEY_V2)), {
        activeView: "chunking",
        selectedDocumentIds: {
          review: "doc-review",
          inventory: "doc-inventory",
        },
        embeddingIndexing: {
          activeStage: "embedding",
          selectedEmbeddingProfileId: null,
          selectedChunkBundleId: null,
          activeEmbeddingRunId: null,
          selectedEmbeddingBundleId: null,
          activeIndexingRunId: null,
          activeActivationRunId: null,
          selectedRetrievalProfileId: null,
        },
      });
    },
  );
});

test("writes only the compact v2 dashboard preferences payload", () => {
  withMockWindow({}, (storage) => {
    const preferences = createDefaultDashboardPreferences();
    preferences.activeView = "embedding-indexing";
    preferences.selectedDocumentIds.review = "doc-review";
    preferences.embeddingIndexing.activeStage = "retrieval";
    preferences.embeddingIndexing.selectedEmbeddingProfileId = "local-bge-m3-v1";

    writeDashboardPreferences(preferences);

    assert.equal(storage.getItem(STORAGE_KEY_V1), null);
    assert.deepEqual(storage.entries(), {
      [STORAGE_KEY_V2]: JSON.stringify({
        activeView: "embedding-indexing",
        selectedDocumentIds: {
          review: "doc-review",
          inventory: null,
        },
        embeddingIndexing: {
          activeStage: "retrieval",
          selectedEmbeddingProfileId: "local-bge-m3-v1",
          selectedChunkBundleId: null,
          activeEmbeddingRunId: null,
          selectedEmbeddingBundleId: null,
          activeIndexingRunId: null,
          activeActivationRunId: null,
          selectedRetrievalProfileId: null,
        },
      }),
    });
  });
});

test("defines the dashboard navigation from a single source of truth", () => {
  assert.deepEqual(
    DASHBOARD_VIEWS.map((item) => item.view),
    ["operations", "review", "inventory", "chunking", "embedding-indexing"],
  );
  assert.equal(isDashboardView("embedding-indexing"), true);
  assert.equal(viewTitles["embedding-indexing"], "Embedding e Indexing");
});
