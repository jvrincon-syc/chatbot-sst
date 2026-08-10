import assert from "node:assert/strict";

import { loadDashboardStatus } from "../../../.tmp-tests/features/dashboard/dashboardApi.js";

async function test(name, assertion) {
  try {
    await assertion();
    console.log(`ok - ${name}`);
  } catch (error) {
    console.error(`not ok - ${name}`);
    throw error;
  }
}

await test("falls back to a generic HTTP error when dashboard responses are null", async () => {
  globalThis.fetch = async () => ({
    ok: false,
    status: 500,
    json: async () => null,
  });

  let caught = null;
  try {
    await loadDashboardStatus();
  } catch (error) {
    caught = error;
  }

  assert.ok(caught instanceof Error);
  assert.equal(caught.message, "HTTP 500");
});
