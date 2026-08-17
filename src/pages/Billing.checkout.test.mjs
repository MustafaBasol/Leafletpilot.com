import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const source = await readFile(new URL("./Billing.jsx", import.meta.url), "utf8");

test("Billing renders the current subscription: plan, status, price, renewal/cancellation notices", () => {
  assert.match(source, /<strong>\{PLAN_LABELS\[currentPlanCode\] \|\| currentPlanCode\}<\/strong>/);
  assert.match(source, /<StatusBadge status=\{statusLabel\(subscription\?\.status\)\} \/>/);
  assert.match(source, /Aylık ücret: <strong>\{formatMoney\(subscription\.unit_amount, subscription\.currency\)\}/);
  assert.match(source, /Yenilenme tarihi.*formatDate\(subscription\.current_period_end\)/);
  assert.match(source, /İptal talep edildi/);
  assert.match(source, /Son ödeme başarısız oldu/);
});

test("Billing usage section renders entitlements as stat cards with progress styling, not a plain bullet list", () => {
  assert.doesNotMatch(source, /<ul>\s*<li>\s*Aylık kampanya/, "usage must not regress to a plain bullet list");
  assert.match(source, /function UsageCard\(/);
  assert.match(source, /className="metric-grid"/);
  assert.match(source, /used=\{plan\.monthly_campaigns_used\}/);
  assert.match(source, /limit=\{plan\.monthly_campaigns_limit\}/);
  assert.match(source, /className="usage-bar"/);
});

test("Billing plan selection highlights the current plan and routes upgrade/downgrade clicks through the confirmation flow, not an instant change", () => {
  assert.match(source, /PLAN_ORDER\.map\(\(planCode\) => \{/);
  assert.match(source, /<StatusBadge status="Mevcut plan" \/>/);
  assert.match(source, /planına geç/);
  assert.match(source, /planıyla başla/);
  assert.match(
    source,
    /onClick=\{\(\) => \(hasSubscription \? openPlanChangeModal\(planCode\) : handleCheckout\(planCode\)\)\}/,
    "an existing subscriber's plan click must open the confirmation modal, not change the plan directly",
  );
  assert.doesNotMatch(
    source,
    /onClick=\{\(\) => \(hasSubscription \? handleChangePlan/,
    "the old instant-change handler must not be wired to the plan buttons anymore",
  );
});

test("openPlanChangeModal fetches a preview before any mutation, and never calls changeBillingPlan itself", () => {
  const start = source.indexOf("function openPlanChangeModal");
  const end = source.indexOf("function closePlanChangeModal");
  assert.ok(start !== -1 && end !== -1);
  const body = source.slice(start, end);
  assert.match(body, /previewBillingPlanChange\(planCode\)/);
  assert.doesNotMatch(body, /changeBillingPlan\(/, "opening the modal must only preview, never mutate the subscription");
});

test("confirmPlanChange only calls changeBillingPlan after the user confirms, then refreshes and closes the modal", () => {
  const start = source.indexOf("async function confirmPlanChange");
  const end = source.indexOf("async function handlePortal");
  assert.ok(start !== -1 && end !== -1);
  const body = source.slice(start, end);
  assert.match(body, /changeBillingPlan\(targetPlanCode\)/);
  assert.match(body, /setPlanChange\(null\)/);
  assert.match(body, /await load\(\)/);
  assert.match(body, /isConfirming: true/, "must disable the confirm button while the request is in flight");
});

test("closePlanChangeModal never mutates the subscription and refuses to close mid-confirmation", () => {
  const start = source.indexOf("function closePlanChangeModal");
  const end = source.indexOf("async function confirmPlanChange");
  assert.ok(start !== -1 && end !== -1);
  const body = source.slice(start, end);
  assert.doesNotMatch(body, /changeBillingPlan/);
  assert.match(body, /current\?\.isConfirming \? current : null/);
});

test("PlanChangeModal is wired with the preview state and confirm/cancel handlers", () => {
  assert.match(source, /<PlanChangeModal/);
  assert.match(source, /isOpen=\{Boolean\(planChange\)\}/);
  assert.match(source, /preview=\{planChange\?\.preview \|\| null\}/);
  assert.match(source, /onConfirm=\{confirmPlanChange\}/);
  assert.match(source, /onCancel=\{closePlanChangeModal\}/);
});

test("Payment method portal button shows a loading label while redirecting and disables against double-submit", () => {
  assert.match(source, /disabled=\{!hasSubscription \|\| Boolean\(busyAction\)\}/);
  assert.match(source, /busyAction === "portal" \? "Yönlendiriliyor\.\.\." : "Ödeme yöntemini yönet"/);
});

test("Billing renders a polished, iconized error alert (not a raw technical string) for failed actions like the portal", () => {
  assert.match(source, /inline-result inline-result-danger billing-alert/);
  assert.match(source, /<Icon name="alert" \/> \{error\}/);
});

test("Success and info banners still render", () => {
  assert.match(source, /inline-result inline-result-success billing-alert/);
  assert.match(source, /\{message\}/);
});

test("Billing renders invoice history with date, number, amount, status, hosted link, and an empty state", () => {
  const table = source.slice(source.indexOf('title="Fatura Geçmişi"'), source.indexOf("</Card>\n      </section>"));
  assert.match(table, /formatDate\(invoice\.created_at\)/);
  assert.match(table, /invoice\.number/);
  assert.match(table, /formatMoney\(invoice\.total, invoice\.currency\)/);
  assert.match(table, /invoiceStatusLabel\(invoice\)/);
  assert.match(table, /invoice\.hosted_invoice_url/);
  assert.match(table, /Henüz fatura bulunmuyor\./);
});

test("checkout=success renders a one-time success banner, strips the query param, and schedules a single re-fetch", () => {
  assert.match(source, /export function Billing\(\{ checkoutStatus = "" \}\)/);
  assert.match(source, /useState\(checkoutStatus === "success"\)/);
  assert.match(source, /Ödeme başarıyla tamamlandı\. Aboneliğiniz etkinleştirildi\./);
  assert.match(source, /window\.history\.replaceState\(null, "", `\$\{window\.location\.pathname\}\$\{window\.location\.search\}#\/settings\/billing`\)/);
  assert.match(source, /window\.setTimeout\(load, 2000\)/);
  assert.doesNotMatch(source, /setInterval/, "must not introduce polling");
});
