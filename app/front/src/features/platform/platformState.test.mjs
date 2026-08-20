import assert from "node:assert/strict";

import {
  DEFAULT_PLATFORM_PREFERENCES,
  platformPreferencesEqual,
  resolvePlatformPreferences,
} from "../../../.tmp-tests/features/platform/platformState.js";

function test(name, assertion) {
  try {
    assertion();
    console.log(`ok - ${name}`);
  } catch (error) {
    console.error(`not ok - ${name}`);
    throw error;
  }
}

const STORED = {
  selectedProjectId: "proj_alpha",
  selectedRagVariantId: "ragv_1",
  selectedCorpusSnapshotId: "corp_1",
  selectedRagReleaseId: "ragr_1",
};

const FULL_SCOPE = {
  projectIds: ["proj_alpha", "proj_beta"],
  variantIds: ["ragv_1"],
  corpusSnapshotIds: ["corp_1"],
  releaseIds: ["ragr_1"],
};

test("sin scope (data no cargada) preserva lo persistido", () => {
  const resolved = resolvePlatformPreferences({ stored: STORED, scope: null });
  assert.deepEqual(resolved, STORED);
});

test("stored null sin scope devuelve defaults", () => {
  assert.deepEqual(
    resolvePlatformPreferences({ stored: null, scope: null }),
    DEFAULT_PLATFORM_PREFERENCES,
  );
});

test("con scope completo conserva todas las selecciones válidas", () => {
  const resolved = resolvePlatformPreferences({ stored: STORED, scope: FULL_SCOPE });
  assert.deepEqual(resolved, STORED);
});

test("proyecto fuera de scope limpia TODO (cascada)", () => {
  const resolved = resolvePlatformPreferences({
    stored: STORED,
    scope: { ...FULL_SCOPE, projectIds: ["proj_beta"] },
  });
  assert.deepEqual(resolved, DEFAULT_PLATFORM_PREFERENCES);
});

test("dependiente obsoleto se limpia sin tocar los válidos", () => {
  const resolved = resolvePlatformPreferences({
    stored: STORED,
    scope: { ...FULL_SCOPE, variantIds: [] },
  });
  assert.equal(resolved.selectedProjectId, "proj_alpha");
  assert.equal(resolved.selectedRagVariantId, null);
  assert.equal(resolved.selectedCorpusSnapshotId, "corp_1");
  assert.equal(resolved.selectedRagReleaseId, "ragr_1");
});

test("platformPreferencesEqual compara los 4 IDs", () => {
  assert.equal(platformPreferencesEqual(STORED, { ...STORED }), true);
  assert.equal(
    platformPreferencesEqual(STORED, { ...STORED, selectedRagReleaseId: "ragr_2" }),
    false,
  );
});
