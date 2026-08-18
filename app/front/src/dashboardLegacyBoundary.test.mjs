import assert from "node:assert/strict";

import { viewTitles } from "../.tmp-tests/features/dashboard/dashboardTypes.js";
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

test("dashboard labels the current surface as legacy pipeline", () => {
  for (const title of Object.values(viewTitles)) {
    assert.equal(title.includes("Legacy pipeline"), true);
  }

  assert.equal(viewTitles.operations.includes("Legacy pipeline"), true);
});

test("dashboard navigation keeps the legacy boundary in its single source of truth", () => {
  assert.deepEqual(
    DASHBOARD_VIEWS.map((item) => item.view),
    ["operations", "review", "inventory", "chunking", "embedding-indexing"],
  );
  assert.equal(isDashboardView("embedding-indexing"), true);
  assert.equal(DASHBOARD_VIEWS.every((item) => item.title.includes("Legacy pipeline")), true);
});
