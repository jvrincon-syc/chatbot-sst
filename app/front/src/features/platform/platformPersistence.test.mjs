import assert from "node:assert/strict";

import {
  readPlatformPreferences,
  writePlatformPreferences,
  serializePlatformPreferencesForTest,
} from "../../../.tmp-tests/features/platform/platformPersistence.js";

function test(name, assertion) {
  try {
    assertion();
    console.log(`ok - ${name}`);
  } catch (error) {
    console.error(`not ok - ${name}`);
    throw error;
  }
}

const STORAGE_KEY = "chatbot-sst.platform.preferences.v1";

const PREFS = {
  selectedProjectId: "proj_alpha",
  selectedRagVariantId: "ragv_1",
  selectedCorpusSnapshotId: null,
  selectedRagReleaseId: "ragr_1",
};

function withMockWindow(initialEntries, assertion) {
  const store = new Map(Object.entries(initialEntries));
  const previousWindow = globalThis.window;
  globalThis.window = {
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
  try {
    assertion(store);
  } finally {
    if (previousWindow === undefined) {
      delete globalThis.window;
    } else {
      globalThis.window = previousWindow;
    }
  }
}

test("write luego read hace round-trip de los 4 IDs", () => {
  withMockWindow({}, () => {
    writePlatformPreferences(PREFS);
    assert.deepEqual(readPlatformPreferences(), PREFS);
  });
});

test("solo persiste los 4 IDs declarados (no filtra campos extra)", () => {
  withMockWindow({}, (store) => {
    writePlatformPreferences({ ...PREFS, bearerToken: "SECRETO", idempotencyKey: "x" });
    const raw = store.get(STORAGE_KEY);
    assert.equal(raw.includes("SECRETO"), false);
    assert.equal(raw.includes("idempotencyKey"), false);
  });
});

test("read sin window (SSR) devuelve null", () => {
  const previousWindow = globalThis.window;
  if (previousWindow !== undefined) {
    delete globalThis.window;
  }
  try {
    assert.equal(readPlatformPreferences(), null);
  } finally {
    if (previousWindow !== undefined) {
      globalThis.window = previousWindow;
    }
  }
});

test("raw corrupto se degrada a null (no rompe)", () => {
  withMockWindow({ [STORAGE_KEY]: "{no-json" }, () => {
    assert.equal(readPlatformPreferences(), null);
  });
});

test("serialize incluye los 4 campos", () => {
  const raw = serializePlatformPreferencesForTest(PREFS);
  assert.deepEqual(JSON.parse(raw), PREFS);
});
