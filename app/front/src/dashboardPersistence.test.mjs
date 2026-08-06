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

  const preferences = resolveDashboardPreferences({
    stored,
    status,
  });

  assert.equal(preferences.activeView, "inventory");
  assert.deepEqual(preferences.selectedDocumentIds, stored.selectedDocumentIds);
  assert.equal(preferences.embeddingIndexing.activeStage, "retrieval");
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

  const preferences = resolveDashboardPreferences({
    stored,
    status,
  });

  assert.equal(preferences.activeView, "embedding-indexing");
  assert.equal(preferences.embeddingIndexing.activeStage, "activation");
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
      assert.equal(storage.getItem(STORAGE_KEY_V1), null);
      assert.deepEqual(JSON.parse(storage.getItem(STORAGE_KEY_V2)), {
        activeView: "chunking",
        selectedDocumentIds: {
          review: "doc-review",
          inventory: "doc-inventory",
        },
        embeddingIndexing: {
          activeStage: "embedding",
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
