import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const source = await readFile(new URL("./Billing.jsx", import.meta.url), "utf8");

// ---------------------------------------------------------------------------
// PR #69 final closure round — PART A: cancel a scheduled downgrade and stay
// on the current plan (undo for change_plan's Subscription Schedule).
// ---------------------------------------------------------------------------

function handleCancelPlanChangeBody() {
  const start = source.indexOf("async function handleCancelPlanChange");
  assert.ok(start !== -1, "handleCancelPlanChange must exist");
  const end = source.indexOf("\n  }", start);
  assert.ok(end !== -1);
  return source.slice(start, end);
}

test("cancelBillingPlanChange is imported from dataSource", () => {
  assert.match(source, /cancelBillingPlanChange,/);
});

test("the cancel-plan-change CTA only renders alongside a pending downgrade notice, never a bare pending_plan_code", () => {
  const start = source.indexOf('subscription?.pending_plan_code && subscription?.pending_change_reason === "downgrade"');
  assert.ok(start !== -1, "pending downgrade branch must exist");
  const end = source.indexOf('pending_change_reason === "upgrade_pending_payment"', start);
  const branch = source.slice(start, end);
  assert.match(branch, /Plan değişikliğini iptal et/);
  assert.match(branch, /onClick=\{\(\) => setConfirmPlanChangeCancel\(true\)\}/);
});

test("clicking the CTA opens a confirmation dialog instead of calling the endpoint directly", () => {
  const start = source.indexOf('subscription?.pending_plan_code && subscription?.pending_change_reason === "downgrade"');
  const end = source.indexOf('pending_change_reason === "upgrade_pending_payment"', start);
  const branch = source.slice(start, end);
  assert.doesNotMatch(branch, /cancelBillingPlanChange\(/, "the inline CTA must only open the confirm dialog, never mutate directly");
});

test("ConfirmDialog for plan-change cancellation is wired with the confirm/cancel handlers", () => {
  assert.match(source, /isOpen=\{Boolean\(confirmPlanChangeCancel\)\}/);
  assert.match(source, /title="Plan değişikliğini iptal et"/);
  assert.match(source, /onCancel=\{\(\) => setConfirmPlanChangeCancel\(null\)\}/);
  assert.match(source, /onConfirm=\{handleCancelPlanChange\}/);
  assert.match(source, /isLoading=\{busyAction === "cancel-plan-change"\}/);
});

test("handleCancelPlanChange calls cancelBillingPlanChange exactly once through the shared bounded sync helper", () => {
  const body = handleCancelPlanChangeBody();
  assert.match(body, /runActionWithSync\(/, "must reuse the shared bounded sync helper, not a bespoke loop");
  assert.match(body, /"cancel-plan-change"/);
  assert.match(body, /cancelBillingPlanChange\(\)/);
  const matches = body.match(/cancelBillingPlanChange\(\)/g);
  assert.equal(matches.length, 1, "must call the endpoint exactly once per confirm");
});

test("handleCancelPlanChange closes the confirm dialog before the request starts", () => {
  const body = handleCancelPlanChangeBody();
  assert.match(body, /setConfirmPlanChangeCancel\(null\);\s*\n\s*const planBeforeCancel/, "dialog must close synchronously before the async action runs");
});

test("convergence requires all three pending_* fields to clear, not just one", () => {
  const body = handleCancelPlanChangeBody();
  assert.match(body, /s\?\.pending_plan_code == null/);
  assert.match(body, /s\?\.pending_change_reason == null/);
  assert.match(body, /s\?\.pending_change_at == null/);
});

test("convergence also confirms plan_code held steady at the pre-cancel plan — no optimistic entitlement change", () => {
  const body = handleCancelPlanChangeBody();
  assert.match(body, /s\?\.plan_code === planBeforeCancel/);
});

test("does not optimistically mutate subscription state before the authoritative sync resolves", () => {
  const body = handleCancelPlanChangeBody();
  assert.doesNotMatch(body, /setSubscription\(/, "must rely on load() re-fetching, never a direct setSubscription optimistic write");
});

test("converged message reflects the plan that stayed active; pending message admits it is still processing", () => {
  const body = handleCancelPlanChangeBody();
  assert.match(body, /convergedMessage: `Plan değişikliği iptal edildi\. \$\{PLAN_LABELS\[planBeforeCancel\] \|\| planBeforeCancel\} planınız devam edecek\.`/);
  assert.match(body, /pendingMessage: "Plan değişikliği iptali alındı\. Bilgileriniz birkaç saniye içinde güncellenecek\."/);
});

test("falls back to the same manual-refresh affordance as other billing actions when sync does not converge", () => {
  // runActionWithSync sets pendingSync, and the shared banner already renders
  // handleManualSync — reused here, not a bespoke fallback.
  assert.match(source, /pendingSync \? \(\s*<Button variant="secondary" className="billing-inline-refresh" onClick=\{handleManualSync\}/);
});

test("the CTA and its confirm dialog are disabled while any billing action is in flight", () => {
  const start = source.indexOf('subscription?.pending_plan_code && subscription?.pending_change_reason === "downgrade"');
  const end = source.indexOf('pending_change_reason === "upgrade_pending_payment"', start);
  const branch = source.slice(start, end);
  assert.match(branch, /disabled=\{!canManage \|\| Boolean\(busyAction\)\}/);
});
