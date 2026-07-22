import assert from "node:assert/strict";

import { validateOcrThresholdPercent } from "../.tmp-tests/ocrSettings.js";

function test(name, assertion) {
  try {
    assertion();
    console.log(`ok - ${name}`);
  } catch (error) {
    console.error(`not ok - ${name}`);
    throw error;
  }
}

test("treats an empty OCR threshold as missing instead of zero", () => {
  const result = validateOcrThresholdPercent("");

  assert.equal(result.status, "empty");
  assert.equal(result.value, null);
});

test("accepts OCR thresholds inside the inclusive percent range", () => {
  const result = validateOcrThresholdPercent("80.5");

  assert.equal(result.status, "valid");
  assert.equal(result.value, 80.5);
});

test("rejects OCR thresholds outside the accepted percent range", () => {
  assert.equal(validateOcrThresholdPercent("-1").status, "out_of_range");
  assert.equal(validateOcrThresholdPercent("101").status, "out_of_range");
});

test("rejects non numeric OCR thresholds", () => {
  assert.equal(validateOcrThresholdPercent("abc").status, "invalid_number");
});
