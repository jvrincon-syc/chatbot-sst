import assert from "node:assert/strict";

import {
  chunkingPaginationLabel,
  chunkingRunProgressPercent,
  chunkingRunStatusLabel,
  chunkingRunStatusTone,
  chunkingRunIsTerminalStatus,
  parseChunkingDocumentIds,
} from "../../../.tmp-tests/features/chunking/chunkingState.js";

function test(name, assertion) {
  try {
    assertion();
    console.log(`ok - ${name}`);
  } catch (error) {
    console.error(`not ok - ${name}`);
    throw error;
  }
}

test("parses chunking document ids from lines and commas", () => {
  assert.deepEqual(parseChunkingDocumentIds("doc_1\n\ndoc_2, doc_1"), ["doc_1", "doc_2"]);
});

test("calculates chunking progress percentage", () => {
  assert.equal(
    chunkingRunProgressPercent({
      requestedDocuments: 8,
      completedDocuments: 6,
    }),
    75,
  );
  assert.equal(
    chunkingRunProgressPercent({
      requestedDocuments: 0,
      completedDocuments: 0,
    }),
    0,
  );
});

test("maps chunking status labels and tones", () => {
  assert.equal(chunkingRunStatusLabel("completed_with_warnings"), "Completada con alertas");
  assert.equal(chunkingRunStatusTone("failed"), "danger");
  assert.equal(chunkingRunIsTerminalStatus("running"), false);
  assert.equal(chunkingRunIsTerminalStatus("completed"), true);
});

test("formats chunking pagination labels", () => {
  assert.equal(chunkingPaginationLabel(2, 5, 20), "Pagina 2 de 5 · 20 items");
  assert.equal(chunkingPaginationLabel(1, 0, 0), "Sin resultados");
});
