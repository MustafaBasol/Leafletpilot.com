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

// ---------------------------------------------------------------------------
// Post-upgrade sync: an "applied" plan change must not require a manual page
// refresh, but the bounded re-fetch must stay bounded (no setInterval / no
// unbounded while-true) and must never fabricate a plan change the backend
// hasn't confirmed.
// ---------------------------------------------------------------------------

function confirmPlanChangeBody() {
  const start = source.indexOf("async function confirmPlanChange");
  const end = source.indexOf("async function handleManualSync");
  assert.ok(start !== -1 && end !== -1, "confirmPlanChange/handleManualSync boundary must exist");
  return source.slice(start, end);
}

test("load() returns the fetched subscription so callers can check whether the plan actually changed", () => {
  assert.match(source, /async function load\(\) \{[\s\S]*?return subscriptionResult;[\s\S]*?\}\s*\n\s*\n\s*useEffect/);
});

test("an applied upgrade enters a bounded sync loop instead of assuming the mutation response is authoritative", () => {
  const body = confirmPlanChangeBody();
  assert.match(body, /isSyncing: true/, "modal must switch to a distinct processing state during sync");
  assert.match(body, /PLAN_SYNC_MAX_ATTEMPTS/, "retry loop must be bounded by a fixed attempt count");
  assert.match(body, /synced = subscriptionResult\?\.plan_code === targetPlanCode/, "sync success must be judged against the authoritative refetched plan_code, not assumed");
  assert.doesNotMatch(source, /setInterval/, "must not introduce continuous polling");
  assert.doesNotMatch(body, /while\s*\(\s*true\s*\)/, "must not introduce unbounded polling");
});

test("bounded refetch stops after PLAN_SYNC_MAX_ATTEMPTS attempts and never blocks indefinitely", () => {
  assert.match(source, /const PLAN_SYNC_MAX_ATTEMPTS = 4;/);
  assert.match(source, /for \(let attempt = 0; attempt < PLAN_SYNC_MAX_ATTEMPTS && !synced; attempt\+\+\)/);
});

test("pending_payment and scheduled (downgrade) results close the modal immediately without entering the sync loop", () => {
  const body = confirmPlanChangeBody();
  const pendingPaymentBranch = body.slice(body.indexOf('"pending_payment"'), body.indexOf('"scheduled"'));
  assert.match(pendingPaymentBranch, /setPlanChange\(null\)/);
  assert.doesNotMatch(pendingPaymentBranch, /isSyncing/, "pending payment must not show the upgrade-processing sync state");

  const scheduledBranch = body.slice(body.indexOf('"scheduled"'), body.indexOf('// status === "applied"'));
  assert.match(scheduledBranch, /setPlanChange\(null\)/);
  assert.doesNotMatch(scheduledBranch, /isSyncing/, "a scheduled downgrade must not be treated as an immediate state change");
});

test("a failed change-plan request never closes the modal or shows a false success message", () => {
  const body = confirmPlanChangeBody();
  const catchBlock = body.slice(body.indexOf("} catch (e) {"));
  assert.match(catchBlock, /isConfirming: false/);
  assert.match(catchBlock, /isSyncing: false/);
  assert.doesNotMatch(catchBlock, /setPlanChange\(null\)/, "an error must keep the modal open with the error shown, not silently close it");
  assert.doesNotMatch(catchBlock, /setMessage/, "an error must not also show a success message");
});

test("when the bounded sync exhausts without confirmation, the UI shows an awaiting-sync message with a manual refresh action instead of lying about the plan", () => {
  assert.match(source, /Ödemeniz alındı\. Plan bilgileriniz birkaç saniye içinde güncellenecek\./);
  assert.match(source, /setPendingSync\(!synced\)/);
  assert.match(source, /async function handleManualSync\(\) \{/);
  assert.match(source, /pendingSync \? \(/, "the success banner must offer a manual refresh affordance when sync did not complete");
});

test("a confirmed sync shows the target plan's own success wording, not a generic message", () => {
  assert.match(source, /\$\{PLAN_LABELS\[targetPlanCode\] \|\| targetPlanCode\} planınız etkinleştirildi\./);
});

test("PlanChangeModal is wired with the isSyncing processing state", () => {
  assert.match(source, /isSyncing=\{Boolean\(planChange\?\.isSyncing\)\}/);
});
