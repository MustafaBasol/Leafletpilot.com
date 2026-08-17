import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const source = await readFile(new URL("./Billing.jsx", import.meta.url), "utf8");

test("Billing renders the current subscription: plan, status, price, renewal/cancellation notices", () => {
  assert.match(source, /Plan: <strong>\{PLAN_LABELS\[currentPlanCode\]/);
  assert.match(source, /<StatusBadge status=\{statusLabel\(subscription\?\.status\)\} \/>/);
  assert.match(source, /Aylık ücret: \{formatMoney\(subscription\.unit_amount, subscription\.currency\)\}/);
  assert.match(source, /Yenilenme tarihi.*formatDate\(subscription\.current_period_end\)/);
  assert.match(source, /İptal talep edildi/);
  assert.match(source, /Son ödeme başarısız oldu/);
});

test("Billing plan selection identifies the current plan and exposes upgrade/downgrade actions", () => {
  assert.match(source, /PLAN_ORDER\.map\(\(planCode\) => \{/);
  assert.match(source, /\(mevcut plan\)/);
  assert.match(source, /planına geç/);
  assert.match(source, /planıyla başla/);
  assert.match(source, /disabled=\{!canManage \|\| isCurrent \|\| Boolean\(busyAction\)/);
});

test("Billing renders invoice history with date, number, amount, status, and hosted link", () => {
  const table = source.slice(source.indexOf('title="Fatura Geçmişi"'), source.indexOf("</Card>\n\n      <ConfirmDialog"));
  assert.match(table, /formatDate\(invoice\.created_at\)/);
  assert.match(table, /invoice\.number/);
  assert.match(table, /formatMoney\(invoice\.total, invoice\.currency\)/);
  assert.match(table, /invoiceStatusLabel\(invoice\)/);
  assert.match(table, /invoice\.hosted_invoice_url/);
});

test("checkout=success renders a one-time success banner, strips the query param, and schedules a single re-fetch", () => {
  assert.match(source, /export function Billing\(\{ checkoutStatus = "" \}\)/);
  assert.match(source, /useState\(checkoutStatus === "success"\)/);
  assert.match(source, /Ödeme başarıyla tamamlandı\. Aboneliğiniz etkinleştirildi\./);
  assert.match(source, /window\.history\.replaceState\(null, "", `\$\{window\.location\.pathname\}\$\{window\.location\.search\}#\/settings\/billing`\)/);
  assert.match(source, /window\.setTimeout\(load, 2000\)/);
  assert.doesNotMatch(source, /setInterval/, "must not introduce polling");
});
