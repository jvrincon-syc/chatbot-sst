import assert from "node:assert/strict";

import { readJsonResponse } from "../../.tmp-tests/shared/readJsonResponse.js";

async function test(name, assertion) {
  try {
    await assertion();
    console.log(`ok - ${name}`);
  } catch (error) {
    console.error(`not ok - ${name}`);
    throw error;
  }
}

await test("reads JSON from mock responses that only expose json()", async () => {
  const response = {
    json: async () => ({ ok: true, answer: 42 }),
  };

  const payload = await readJsonResponse(response);

  assert.deepEqual(payload, { ok: true, answer: 42 });
});

await test("rejects HTML responses with an actionable error", async () => {
  const response = new Response("<!doctype html><html><body>index</body></html>", {
    status: 200,
    headers: {
      "Content-Type": "text/html; charset=utf-8",
    },
  });

  await assert.rejects(readJsonResponse(response), /HTML/i);
});
