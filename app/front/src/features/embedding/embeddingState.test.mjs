import assert from "node:assert/strict";

import { toEmbeddingProfile } from "../../../.tmp-tests/features/embedding/embeddingMappers.js";
import {
  embeddingCatalogFullyBlocked,
  embeddingProfileBlockedReason,
  embeddingProfileSelectable,
  embeddingRunIsTerminal,
  embeddingRunProducedBundleId,
  embeddingRunProgressPercent,
  requiredEmbeddingBundleLinks,
} from "../../../.tmp-tests/features/embedding/embeddingState.js";

function test(name, assertion) {
  try {
    assertion();
    console.log(`ok - ${name}`);
  } catch (error) {
    console.error(`not ok - ${name}`);
    throw error;
  }
}

test("marks a profile as blocked when can_embed_documents is false", () => {
  const profile = toEmbeddingProfile({
    profile_id: "local-bge-m3-v1",
    active: true,
    document_enabled: false,
    can_embed_documents: false,
    compatibility_status: "compatibility_not_proven",
  });

  assert.equal(embeddingProfileSelectable(profile), false);
  assert.equal(embeddingProfileBlockedReason(profile), "compatibility_not_proven");
});

test("marks a fully enabled profile as selectable with no blocked reason", () => {
  const profile = toEmbeddingProfile({
    profile_id: "local-bge-m3-v1",
    active: true,
    document_enabled: true,
    can_embed_documents: true,
    compatibility_status: "verified",
  });

  assert.equal(embeddingProfileSelectable(profile), true);
  assert.equal(embeddingProfileBlockedReason(profile), null);
});

test("uses bundle chunks instead of embedding run items", () => {
  const links = requiredEmbeddingBundleLinks({
    chunks: "/api/embedding/bundles/bundle-1/chunks",
    validation: "/api/embedding/bundles/bundle-1/validation",
  });

  assert.equal(links.chunks.includes("/chunks"), true);
  assert.equal(links.chunks.includes("/items"), false);
  assert.equal(links.chunks.includes("/documents"), false);
});

test("reports a fully blocked catalog when every profile is blocked", () => {
  const blocked = toEmbeddingProfile({
    profile_id: "local-bge-m3-v1",
    active: true,
    document_enabled: false,
    can_embed_documents: false,
    compatibility_status: "compatibility_not_proven",
  });

  assert.equal(embeddingCatalogFullyBlocked([blocked]), true);
  assert.equal(embeddingCatalogFullyBlocked([]), false);
});

test("treats completed, failed, cancelled and blocked as terminal", () => {
  assert.equal(embeddingRunIsTerminal("completed"), true);
  assert.equal(embeddingRunIsTerminal("failed"), true);
  assert.equal(embeddingRunIsTerminal("cancelled"), true);
  assert.equal(embeddingRunIsTerminal("blocked"), true);
  assert.equal(embeddingRunIsTerminal("pending"), false);
  assert.equal(embeddingRunIsTerminal("running"), false);
});

test("computes run progress from embedded and requested children", () => {
  assert.equal(
    embeddingRunProgressPercent({ requestedChildren: 12, embeddedChildren: 6 }),
    50,
  );
  assert.equal(
    embeddingRunProgressPercent({ requestedChildren: 0, embeddedChildren: 0 }),
    0,
  );
});

test("pivots a completed run detail to the produced embedding bundle id", () => {
  assert.equal(
    embeddingRunProducedBundleId({
      status: "completed",
      producedEmbeddingBundleId: "embedding-bundle-1",
    }),
    "embedding-bundle-1",
  );
  assert.equal(
    embeddingRunProducedBundleId({
      status: "running",
      producedEmbeddingBundleId: null,
    }),
    null,
  );
});
