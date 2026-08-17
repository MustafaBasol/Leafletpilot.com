import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const source = await readFile(new URL("./PlatformBilling.jsx", import.meta.url), "utf8");

test("PlatformBilling loads both the health summary and the plan mapping table", () => {
  assert.match(source, /platformApi\s*\n?\s*\.getBillingHealth\(\)/);
  assert.match(source, /platformApi\s*\n?\s*\.getBillingPlanHealth\(\)/);
});

test("PlatformBilling renders the health summary metric cards (Stripe connection, environment, webhook health, subscriptions, failures)", () => {
  assert.match(source, /label="Stripe Bağlantısı"/);
  assert.match(source, /label="Ortam"/);
  assert.match(source, /label="Webhook Sağlığı"/);
  assert.match(source, /label="Aktif Abonelikler"/);
  assert.match(source, /label="Başarısız Webhook"/);
  assert.match(source, /label="Başarısız Ödeme\/Fatura"/);
});

test("PlatformBilling renders TEST vs LIVE environment state distinctly", () => {
  assert.match(source, /ENVIRONMENT_LABELS\s*=\s*\{\s*live:\s*"CANLI",\s*sandbox:\s*"TEST",\s*not_configured:/);
  assert.match(source, /health\.environment === "live" \? "warning" : "success"/);
});

test("PlatformBilling flags unhealthy webhook state as a warning/danger tone, not silently as success", () => {
  assert.match(source, /const webhookTone = failedWebhooks > 0 \|\| stuckReceived > 0 \? "danger" : "success";/);
  assert.match(source, /tone=\{webhookTone\}/);
});

test("PlatformBilling keeps the existing plan-mapping table (Plan Eşleştirmeleri)", () => {
  assert.match(source, /title="Plan Eşleştirmeleri"/);
  assert.match(source, /columns=\{\["Plan", "Lookup key", "Durum", "Stripe Price", "Tutar", "Detay"\]\}/);
});

test("PlatformBilling renders the attention markets and recent failures sections", () => {
  assert.match(source, /title="Dikkat Gerektiren Marketler"/);
  assert.match(source, /title="Son Faturalandırma Hataları"/);
  assert.match(source, /health\.attention_markets/);
  assert.match(source, /health\.recent_failures/);
});

test("PlatformBilling never references a raw Stripe secret/webhook key field", () => {
  assert.doesNotMatch(source, /stripe_secret_key/);
  assert.doesNotMatch(source, /stripe_webhook_secret/);
  assert.doesNotMatch(source, /sk_live_|sk_test_|whsec_/);
});
