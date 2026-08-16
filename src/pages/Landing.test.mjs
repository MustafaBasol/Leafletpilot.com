import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { plans } from "../data/mockData.js";
import { getPublicPlans } from "../data/dataSource.js";

test("mock plans mirror the GET /api/public/plans contract with three plans and Standard recommended", () => {
  assert.equal(plans.length, 3);
  assert.deepEqual(plans.map((plan) => plan.code), ["starter", "standard", "pro"]);
  assert.deepEqual(plans.map((plan) => plan.monthly_price), [59, 119, 199]);
  assert.deepEqual(plans.map((plan) => plan.is_recommended), [false, true, false]);
  for (const plan of plans) {
    assert.ok(Array.isArray(plan.features) && plan.features.length > 0, `${plan.code} must list features`);
    assert.deepEqual(plan.export_formats, ["pdf", "png"], `${plan.code} must only advertise real render formats`);
  }
});

test("dataSource.getPublicPlans falls back to mock plans outside real-API mode", async () => {
  const result = await getPublicPlans();
  assert.deepEqual(result, plans);
});

test("Landing copy does not overclaim WhatsApp as a currently supported input channel", async () => {
  const source = await readFile("src/pages/Landing.jsx", "utf8");
  assert.doesNotMatch(source, /Telegram veya WhatsApp/);
  assert.match(source, /WhatsApp desteği yol haritamızda/);
});

test("Landing feature copy does not promise an Instagram export that the renderer cannot produce", async () => {
  const source = await readFile("src/pages/Landing.jsx", "utf8");
  assert.doesNotMatch(source, /Instagram postu/);
  assert.doesNotMatch(source, /Instagram görseli/);
});

test("Landing renders plan pricing from data rather than a second hardcoded contract", async () => {
  const source = await readFile("src/pages/Landing.jsx", "utf8");
  assert.match(source, /usePublicPlans/);
  assert.match(source, /getPublicPlans/);
});
