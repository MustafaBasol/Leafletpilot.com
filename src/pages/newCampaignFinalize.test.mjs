import assert from "node:assert/strict";
import { test } from "node:test";
import {
  campaignIdFromPersistedDraft,
  finalizeCampaignAndCreateExports,
  finalizePayloadFromPersistedDraft,
} from "./newCampaignFinalize.js";

const persistedDraft = { id: "campaign-42", draft_revision: 7 };

test("finalize payload is the backend's required object contract", () => {
  assert.deepEqual(finalizePayloadFromPersistedDraft(persistedDraft), { expected_revision: 7 });
  assert.equal(campaignIdFromPersistedDraft(persistedDraft), "campaign-42");
  assert.throws(
    () => finalizePayloadFromPersistedDraft({ id: "campaign-42" }),
    /geçerli taslak revizyonu/,
  );
});

test("finalization sends the object body and market id as the third API argument", async () => {
  const calls = [];
  await finalizeCampaignAndCreateExports({
    persistDraft: async () => persistedDraft,
    finalize: async (...args) => calls.push(args),
    createExport: async () => assert.fail("no export format was selected"),
    navigate: (id) => calls.push(["navigate", id]),
    selectedMarketId: "market-9",
    selectedFormats: [],
    exportFormats: [{ id: "pdf" }],
  });

  assert.deepEqual(calls[0], [
    "campaign-42",
    { expected_revision: 7 },
    "market-9",
  ]);
  assert.equal(typeof calls[0][1], "object");
  assert.notEqual(calls[0][1], "market-9");
  assert.deepEqual(calls[1], ["navigate", "campaign-42"]);
});

test("a failed finalize does not create exports or navigate", async () => {
  const calls = [];
  await assert.rejects(
    finalizeCampaignAndCreateExports({
      persistDraft: async () => persistedDraft,
      finalize: async () => { calls.push("finalize"); throw new Error("422"); },
      createExport: async () => calls.push("export"),
      navigate: () => calls.push("navigate"),
      selectedMarketId: "market-9",
      selectedFormats: ["pdf"],
      exportFormats: [{ id: "pdf" }],
    }),
    /422/,
  );
  assert.deepEqual(calls, ["finalize"]);
});

test("exports and navigation run only after a successful finalize", async () => {
  const calls = [];
  await finalizeCampaignAndCreateExports({
    persistDraft: async () => persistedDraft,
    finalize: async () => calls.push("finalize"),
    createExport: async (id, payload, marketId) => calls.push(["export", id, payload, marketId]),
    navigate: (id) => calls.push(["navigate", id]),
    selectedMarketId: "market-9",
    selectedFormats: ["pdf", "instagram_post"],
    exportFormats: [{ id: "pdf" }, { id: "png" }],
  });

  assert.deepEqual(calls, [
    "finalize",
    ["export", "campaign-42", { job_type: "final_export", requested_formats: ["pdf"] }, "market-9"],
    ["navigate", "campaign-42"],
  ]);
});
