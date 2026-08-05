import assert from "node:assert/strict";

import { matchesDocumentReviewQuery } from "../.tmp-tests/documentReview.js";

const document = {
  sourceRelpath: "general_sst/manuales/politica/politica.md",
  documentId: "doc_001",
  documentName: "Politica SST",
  ingestionProviderLabel: "Local",
  ingestionMethodLabel: "OCR Tesseract",
  reviewReasons: ["classification_mismatch"],
  reviewDetails: ["La tabla de control indica politica pero la ruta parecia manual"],
};

function test(name, assertion) {
  try {
    assertion();
    console.log(`ok - ${name}`);
  } catch (error) {
    console.error(`not ok - ${name}`);
    throw error;
  }
}

test("matches inventory search by review mismatch reason", () => {
  assert.equal(matchesDocumentReviewQuery(document, "classification_mismatch"), true);
});

test("matches inventory search by review detail text", () => {
  assert.equal(matchesDocumentReviewQuery(document, "tabla de control"), true);
});

test("ignores unrelated inventory search text", () => {
  assert.equal(matchesDocumentReviewQuery(document, "seguridad vial"), false);
});
