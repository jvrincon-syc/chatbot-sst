import assert from "node:assert/strict";

import {
  getOperatorSession,
  loginOperatorSession,
  registerOperatorSession,
  logoutOperatorSession,
} from "../../../.tmp-tests/features/operator/operatorAuthApi.js";

async function test(name, assertion) {
  try {
    await assertion();
    console.log(`ok - ${name}`);
  } catch (error) {
    console.error(`not ok - ${name}`);
    throw error;
  }
}

function jsonResponse(body, { ok = true, status = 200 } = {}) {
  return { ok, status, json: async () => body };
}

function captureFetch(response) {
  const calls = [];
  globalThis.fetch = async (input, init) => {
    calls.push([input, init]);
    return response;
  };
  return calls;
}

await test("getOperatorSession consulta la sesión GUI con same-origin", async () => {
  const calls = captureFetch(jsonResponse({ authenticated: true, principal_id: "op-1", project_scope: null }));
  await getOperatorSession();
  const [url, init] = calls[0];
  assert.equal(url, "/api/auth/session");
  assert.equal(init.method, undefined);
  assert.equal(init.credentials, "same-origin");
});

await test("loginOperatorSession hace POST JSON con usuario y contraseÃ±a", async () => {
  const calls = captureFetch(
    jsonResponse({ authenticated: true, principal_id: "op-1", project_scope: null }),
  );
  await loginOperatorSession({ username: "op-1", password: "Clave123!" });
  const [url, init] = calls[0];
  assert.equal(url, "/api/auth/login");
  assert.equal(init.method, "POST");
  assert.equal(init.headers["Content-Type"], "application/json");
  assert.deepEqual(JSON.parse(init.body), {
    username: "op-1",
    password: "Clave123!",
  });
});

await test("registerOperatorSession crea un usuario local con usuario y contraseÃ±a", async () => {
  const calls = captureFetch(
    jsonResponse({
      authenticated: true,
      principal_id: "nuevo-operador",
      project_scope: null,
    }),
  );
  await registerOperatorSession({
    username: "nuevo-operador",
    password: "Clave123!",
  });
  const [url, init] = calls[0];
  assert.equal(url, "/api/auth/register");
  assert.equal(init.method, "POST");
  assert.deepEqual(JSON.parse(init.body), {
    username: "nuevo-operador",
    password: "Clave123!",
  });
});

await test("logoutOperatorSession revoca la sesión con POST same-origin", async () => {
  const calls = captureFetch(jsonResponse({ authenticated: false }));
  await logoutOperatorSession();
  const [url, init] = calls[0];
  assert.equal(url, "/api/auth/logout");
  assert.equal(init.method, "POST");
  assert.equal(init.credentials, "same-origin");
  assert.deepEqual(JSON.parse(init.body), {});
});

await test("preserva el envelope de error del auth backend", async () => {
  captureFetch(
    jsonResponse(
      { error: { code: "HTTP_AUTH_NOT_CONFIGURED", message: "config missing" } },
      { ok: false, status: 503 },
    ),
  );
  await assert.rejects(
    () => getOperatorSession(),
    (error) => {
      assert.equal(error.status, 503);
      assert.equal(error.code, "HTTP_AUTH_NOT_CONFIGURED");
      return true;
    },
  );
});
