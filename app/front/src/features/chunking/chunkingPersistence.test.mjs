import assert from "node:assert/strict";

import {
  createChunkingWorkspaceFormState,
  readChunkingWorkspaceSnapshot,
  writeChunkingWorkspaceSnapshot,
} from "../../../.tmp-tests/features/chunking/chunkingPersistence.js";

function test(name, assertion) {
  try {
    assertion();
    console.log(`ok - ${name}`);
  } catch (error) {
    console.error(`not ok - ${name}`);
    throw error;
  }
}

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
    assertion({
      getItem(key) {
        return store.has(key) ? store.get(key) : null;
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

test("persists the active chunking profile and form fields", () => {
  withMockWindow({}, (storage) => {
    writeChunkingWorkspaceSnapshot({
      scope: "documents",
      documentIdsInput: "doc_1",
      profileId: "local-structural-v2",
      force: true,
      idempotencyKey: "chunking-key",
    });

    assert.deepEqual(JSON.parse(storage.getItem("chatbot-sst.chunking.workspace.v1")), {
      scope: "documents",
      documentIdsInput: "doc_1",
      profileId: "local-structural-v2",
      force: true,
    });
  });
});

test("hydrates a chunking form state from the stored snapshot", () => {
  withMockWindow(
    {
      "chatbot-sst.chunking.workspace.v1": JSON.stringify({
        scope: "corpus",
        documentIdsInput: "doc_1, doc_2",
        profileId: "local-structural-v2",
        force: false,
      }),
    },
    () => {
      const snapshot = readChunkingWorkspaceSnapshot();
      const form = createChunkingWorkspaceFormState(snapshot);

      assert.equal(snapshot?.profileId, "local-structural-v2");
      assert.equal(form.profileId, "local-structural-v2");
      assert.equal(form.scope, "corpus");
      assert.equal(form.documentIdsInput, "doc_1, doc_2");
      assert.equal(form.force, false);
      assert.equal(form.idempotencyKey.startsWith("chunking-"), true);
    },
  );
});
