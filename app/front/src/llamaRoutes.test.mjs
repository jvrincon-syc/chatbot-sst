import assert from "node:assert/strict";

import {
  DEFAULT_LLAMA_ROUTE,
  LLAMA_ROUTE_OPTIONS,
  llamaCloudConfigFromRoute,
  matchingRoutesForServices,
  routeFromStatus,
  routeForServiceSelection,
} from "../.tmp-tests/llamaRoutes.js";

const expectedRoutes = [
  "parse",
  "parse,classify,extract",
  "classify,parse,extract",
  "parse,classify",
  "classify,parse",
  "parse,extract",
];

function test(name, assertion) {
  try {
    assertion();
    console.log(`ok - ${name}`);
  } catch (error) {
    console.error(`not ok - ${name}`);
    throw error;
  }
}

test("hardcodes the supported LlamaCloud route mixes", () => {
  assert.deepEqual(
    LLAMA_ROUTE_OPTIONS.map((option) => option.value),
    expectedRoutes,
  );
});

test("derives enabled capabilities from each selected route", () => {
  assert.deepEqual(llamaCloudConfigFromRoute("parse"), {
    classifyEnabled: false,
    extractEnabled: false,
    callOrder: "parse",
  });
  assert.deepEqual(llamaCloudConfigFromRoute("parse,classify"), {
    classifyEnabled: true,
    extractEnabled: false,
    callOrder: "parse,classify",
  });
  assert.deepEqual(llamaCloudConfigFromRoute("classify,parse"), {
    classifyEnabled: true,
    extractEnabled: false,
    callOrder: "classify,parse",
  });
  assert.deepEqual(llamaCloudConfigFromRoute("parse,extract"), {
    classifyEnabled: false,
    extractEnabled: true,
    callOrder: "parse,extract",
  });
});

test("filters route choices by the selected optional services", () => {
  assert.deepEqual(
    matchingRoutesForServices({ classifyEnabled: true, extractEnabled: true }).map(
      (option) => option.value,
    ),
    ["parse,classify,extract", "classify,parse,extract"],
  );
  assert.deepEqual(
    matchingRoutesForServices({ classifyEnabled: true, extractEnabled: false }).map(
      (option) => option.value,
    ),
    ["parse,classify", "classify,parse"],
  );
  assert.deepEqual(
    matchingRoutesForServices({ classifyEnabled: false, extractEnabled: true }).map(
      (option) => option.value,
    ),
    ["parse,extract"],
  );
});

test("keeps the route when service selection still permits it", () => {
  assert.equal(
    routeForServiceSelection("classify,parse", {
      classifyEnabled: true,
      extractEnabled: false,
    }),
    "classify,parse",
  );
  assert.equal(
    routeForServiceSelection("classify,parse", {
      classifyEnabled: false,
      extractEnabled: true,
    }),
    "parse,extract",
  );
});

test("keeps the configured status route when optional stops are disabled", () => {
  assert.equal(
    routeFromStatus({
      classifyEnabled: true,
      extractEnabled: false,
      callOrder: ["classify", "parse"],
    }),
    "classify,parse",
  );
  assert.equal(
    routeFromStatus({
      classifyEnabled: false,
      extractEnabled: true,
      callOrder: ["parse", "extract"],
    }),
    "parse,extract",
  );
});

test("falls back to the default route for unsupported status order", () => {
  assert.equal(
    routeFromStatus({
      classifyEnabled: true,
      extractEnabled: true,
      callOrder: ["parse", "extract", "classify"],
    }),
    DEFAULT_LLAMA_ROUTE,
  );
});
