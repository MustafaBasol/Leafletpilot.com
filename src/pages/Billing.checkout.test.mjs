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
    /onClick=\{\(\) => \(isActiveSubscription \? openPlanChangeModal\(planCode\) : handleCheckout\(planCode\)\)\}/,
    "an active subscriber's plan click must open the confirmation modal, not change the plan directly",
  );
  assert.doesNotMatch(
    source,
    /onClick=\{\(\) => \(isActiveSubscription \? handleChangePlan/,
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
  assert.match(source, /disabled=\{!hasSubscriptionRow \|\| Boolean\(busyAction\)\}/);
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

test("pending_payment closes the modal immediately without entering a sync loop", () => {
  const body = confirmPlanChangeBody();
  const pendingPaymentBranch = body.slice(body.indexOf('"pending_payment"'), body.indexOf('"scheduled"'));
  assert.match(pendingPaymentBranch, /setPlanChange\(null\)/);
  assert.doesNotMatch(pendingPaymentBranch, /isSyncing/, "pending payment must not show the upgrade-processing sync state");
});

// ---------------------------------------------------------------------------
// Post-downgrade sync (PR #69 hotfix): a "scheduled" plan change must not
// trust a single unchecked load() — the local mirror write can race the
// read, exactly like the upgrade webhook race, so it needs the same bounded
// re-fetch. The success condition is different from upgrade though: the
// *current* plan must stay unchanged and only pending_plan_code/pending_
// change_at should reflect the downgrade — never an optimistic entitlement
// flip to the target plan.
// ---------------------------------------------------------------------------

function scheduledBranchBody() {
  const body = confirmPlanChangeBody();
  const start = body.indexOf('"scheduled"');
  const end = body.indexOf('// status === "applied"');
  assert.ok(start !== -1 && end !== -1, "scheduled branch boundary must exist");
  return body.slice(start, end);
}

test("a scheduled downgrade enters a bounded sync loop instead of trusting the mutation response", () => {
  const branch = scheduledBranchBody();
  assert.match(branch, /isSyncing: true/, "modal must switch to the processing state during downgrade sync too");
  assert.match(branch, /PLAN_SYNC_MAX_ATTEMPTS/, "downgrade retry loop must reuse the same bounded attempt count as upgrade");
  assert.match(branch, /PLAN_SYNC_RETRY_DELAY_MS/, "downgrade retry loop must reuse the same timing as upgrade");
  assert.doesNotMatch(source, /setInterval/, "must not introduce continuous polling");
  assert.doesNotMatch(branch, /while\s*\(\s*true\s*\)/, "must not introduce unbounded polling");
});

test("downgrade sync success requires authoritative pending state, not plan_code === targetPlan", () => {
  const branch = scheduledBranchBody();
  assert.doesNotMatch(
    branch,
    /downgradeSynced\s*=\s*subscriptionResult\?\.plan_code === targetPlanCode/,
    "downgrade must not reuse the upgrade success condition — the current plan never becomes the target",
  );
  assert.match(
    branch,
    /subscriptionResult\?\.plan_code === currentPlanCode/,
    "downgrade success must confirm the current plan stayed put (no optimistic entitlement change)",
  );
  assert.match(
    branch,
    /subscriptionResult\?\.pending_plan_code === targetPlanCode/,
    "downgrade success must confirm the authoritative pending_plan_code matches the requested downgrade target",
  );
  assert.match(
    branch,
    /Boolean\(subscriptionResult\?\.pending_change_at\)/,
    "downgrade success must confirm pending_change_at was populated by the backend",
  );
});

test("downgrade sync never fabricates an immediate plan change and offers manual refresh when it doesn't converge", () => {
  const branch = scheduledBranchBody();
  assert.match(branch, /setPendingSync\(!downgradeSynced\)/);
  assert.match(
    branch,
    /Plan değişikliğiniz alındı\. Bilgileriniz birkaç saniye içinde güncellenecek\./,
    "an unconverged downgrade must show a safe processing message, never assume success",
  );
  assert.match(
    branch,
    /Plan değişikliği \$\{formatDate\(result\.effective_at\)\} tarihinde geçerli olacak\./,
    "a converged downgrade must show the scheduled-effective-date message",
  );
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

// ---------------------------------------------------------------------------
// Terminal subscription lifecycle (PR #69 hotfix): canceled/incomplete_expired/
// unassigned must start a fresh Checkout, never reach change-plan/preview, and
// must never render stale active-plan data as if it were current.
// ---------------------------------------------------------------------------

test("CHANGEABLE_SUBSCRIPTION_STATUSES matches backend CHECKOUT_BLOCKING_STATUSES exactly, and excludes every terminal status", () => {
  const match = source.match(/const CHANGEABLE_SUBSCRIPTION_STATUSES = new Set\(\[([^\]]*)\]\);/);
  assert.ok(match, "CHANGEABLE_SUBSCRIPTION_STATUSES constant must exist");
  const statuses = match[1].split(",").map((entry) => entry.trim().replace(/"/g, ""));
  assert.deepEqual(statuses, ["active", "trialing", "past_due", "incomplete", "paused"]);
  for (const terminal of ["canceled", "unpaid", "incomplete_expired"]) {
    assert.ok(!statuses.includes(terminal), `${terminal} must never be treated as changeable`);
  }
});

test("isActiveSubscription requires both a subscription row and a changeable status — not a generic truthy check", () => {
  assert.match(
    source,
    /const isActiveSubscription = hasSubscriptionRow && CHANGEABLE_SUBSCRIPTION_STATUSES\.has\(subscription\.status\);/,
  );
  assert.doesNotMatch(
    source,
    /const hasSubscription = Boolean\(subscription\?\.status\);/,
    "the old generic-truthy hasSubscription flag must be gone, not just aliased",
  );
});

test("terminal/no-subscription state renders a clean 'no active subscription' state, not stale active-plan data", () => {
  assert.match(source, /Aktif abonelik yok\. Devam etmek için aşağıdan bir plan seçin\./);
  const cardStart = source.indexOf('title="Mevcut Abonelik"');
  const cardEnd = source.indexOf('</Card>', cardStart);
  const card = source.slice(cardStart, cardEnd);
  const terminalBranchStart = card.indexOf("Aktif abonelik yok");
  assert.ok(terminalBranchStart !== -1, "terminal branch must live inside the Mevcut Abonelik card");
  const activeBranch = card.slice(0, terminalBranchStart);
  const terminalBranch = card.slice(terminalBranchStart);
  // The stale-data fields (price, dates, cancel-at-period-end/past_due alerts)
  // must only appear in the active branch, never repeated in the terminal one.
  assert.match(activeBranch, /Aylık ücret: <strong>\{formatMoney\(subscription\.unit_amount, subscription\.currency\)\}/);
  assert.match(activeBranch, /Yenilenme tarihi/);
  assert.doesNotMatch(terminalBranch, /formatMoney\(subscription\.unit_amount/);
  assert.doesNotMatch(terminalBranch, /Yenilenme tarihi/);
});

test("terminal state may show the cancellation date only as clearly historical, separate from current-entitlement fields", () => {
  assert.match(
    source,
    /Son aboneliğiniz <strong>\{formatDate\(subscription\.canceled_at\)\}<\/strong> tarihinde iptal edildi\./,
  );
});

test("canceled/unassigned hides the cancel-subscription action and the resume action (no terminal-subscription actions offered)", () => {
  assert.match(source, /\{isActiveSubscription \? \(\s*<div className="page-actions billing-cancel-row">/);
  assert.doesNotMatch(
    source,
    /\{hasSubscriptionRow \? \(\s*<div className="page-actions billing-cancel-row">/,
    "the cancel/resume row must gate on active-subscription lifecycle, not merely row existence",
  );
});

test("resume stays reachable for an active subscription with cancel_at_period_end=true (only the terminal-canceled case loses it)", () => {
  const rowStart = source.indexOf('className="page-actions billing-cancel-row"');
  const rowEnd = source.indexOf("</div>", source.indexOf("</div>", rowStart) + 1);
  const row = source.slice(rowStart, rowEnd);
  assert.match(row, /subscription\?\.cancel_at_period_end \? \(/);
  assert.match(row, /handleResume/);
});

test("usage section does not render a 0-limit progress bar for an unassigned/terminal plan", () => {
  assert.match(source, /plan\.code === "unassigned"/);
  assert.match(source, /Aktif plan yok\. Plan seçtiğinizde kullanım limitleri burada görüntülenecek\./);
  const cardStart = source.indexOf('title="Plan / Kullanım"');
  const cardEnd = source.indexOf("</Card>", cardStart);
  const card = source.slice(cardStart, cardEnd);
  const unassignedBranchEnd = card.indexOf("<div className=\"metric-grid\"");
  const unassignedBranch = card.slice(0, unassignedBranchEnd);
  assert.doesNotMatch(unassignedBranch, /UsageCard/, "no usage bars must render before the metric-grid branch");
});

// ---------------------------------------------------------------------------
// Post-cancel/resume sync (PR #69 hotfix): cancel_at_period_end mutations
// race the webhook-driven MarketSubscription write exactly like upgrade/
// downgrade did. handleCancel/handleResume must not trust a single
// unchecked load() — they must bounded-retry against authoritative state
// via the shared runActionWithSync helper, same as confirmPlanChange does
// for plan changes.
// ---------------------------------------------------------------------------

function runActionWithSyncBody() {
  const start = source.indexOf("async function runActionWithSync");
  const end = source.indexOf("async function handleCancel");
  assert.ok(start !== -1 && end !== -1, "runActionWithSync/handleCancel boundary must exist");
  return source.slice(start, end);
}

function handleCancelBody() {
  const start = source.indexOf("async function handleCancel");
  const end = source.indexOf("async function handleResume");
  assert.ok(start !== -1 && end !== -1, "handleCancel/handleResume boundary must exist");
  return source.slice(start, end);
}

function handleResumeBody() {
  const start = source.indexOf("async function handleResume");
  const end = source.indexOf("// A subscription row existing at all");
  assert.ok(start !== -1 && end !== -1, "handleResume boundary must exist");
  return source.slice(start, end);
}

test("cancel and resume share one generic bounded sync helper instead of duplicating the polling loop", () => {
  const helper = runActionWithSyncBody();
  assert.match(helper, /PLAN_SYNC_MAX_ATTEMPTS/, "shared helper must reuse the bounded attempt count");
  assert.match(helper, /PLAN_SYNC_RETRY_DELAY_MS/, "shared helper must reuse the bounded retry delay");
  assert.match(helper, /for \(let attempt = 0; attempt < PLAN_SYNC_MAX_ATTEMPTS && !converged; attempt\+\+\)/);
  assert.doesNotMatch(helper, /setInterval/, "must not introduce continuous polling");
  assert.doesNotMatch(helper, /while\s*\(\s*true\s*\)/, "must not introduce unbounded polling");

  const cancelBody = handleCancelBody();
  const resumeBody = handleResumeBody();
  assert.match(cancelBody, /runActionWithSync\(/, "cancel must go through the shared sync helper, not runAction");
  assert.match(resumeBody, /runActionWithSync\(/, "resume must go through the shared sync helper, not runAction");
});

test("cancel waits for cancel_at_period_end=true before declaring success", () => {
  const body = handleCancelBody();
  assert.match(body, /s\?\.cancel_at_period_end === true/);
});

test("cancel also waits for the stale pending-downgrade fields to clear, not just cancel_at_period_end", () => {
  const body = handleCancelBody();
  assert.match(body, /s\?\.pending_plan_code == null/);
  assert.match(body, /s\?\.pending_change_reason == null/);
  assert.match(body, /s\?\.pending_change_at == null/);
});

test("cancel does not optimistically mutate subscription state before the authoritative sync resolves", () => {
  const body = handleCancelBody();
  assert.doesNotMatch(body, /setSubscription\(/, "cancel must rely on load() re-fetching, never a direct setSubscription optimistic write");
});

test("cancel falls back to a safe processing message (not a false success) when the bounded sync does not converge", () => {
  const body = handleCancelBody();
  assert.match(body, /pendingMessage: "İptal talebiniz alındı\. Bilgileriniz birkaç saniye içinde güncellenecek\."/);
  assert.match(body, /convergedMessage: "İptal talebiniz alındı; dönem sonuna kadar erişiminiz devam edecek\."/);
});

test("resume waits for cancel_at_period_end=false before declaring success", () => {
  const body = handleResumeBody();
  assert.match(body, /s\?\.cancel_at_period_end === false/);
});

test("resume does not optimistically mutate subscription state before the authoritative sync resolves", () => {
  const body = handleResumeBody();
  assert.doesNotMatch(body, /setSubscription\(/, "resume must rely on load() re-fetching, never a direct setSubscription optimistic write");
});

test("resume falls back to a safe processing message (not a false success) when the bounded sync does not converge", () => {
  const body = handleResumeBody();
  assert.match(body, /pendingMessage: "Abonelik yenilemesi işleniyor\. Bilgileriniz birkaç saniye içinde güncellenecek\."/);
  assert.match(body, /convergedMessage: "Abonelik yenilemesi yeniden etkinleştirildi\."/);
});

test("converged cancel state (cancel_at_period_end=true) renders the cancellation warning and the resume CTA, driven purely by re-fetched subscription state", () => {
  assert.match(source, /subscription\?\.cancel_at_period_end \? \(\s*<Button onClick=\{handleResume\}/);
  assert.match(source, /İptal talep edildi; erişiminiz \{formatDate\(subscription\.current_period_end\)\} tarihine/);
});

test("converged resume state (cancel_at_period_end=false) renders the cancel CTA instead of resume", () => {
  const rowStart = source.indexOf('className="page-actions billing-cancel-row"');
  const rowEnd = source.indexOf("</div>", source.indexOf("</div>", rowStart) + 1);
  const row = source.slice(rowStart, rowEnd);
  assert.match(row, /Aboneliği iptal et/);
  assert.match(row, /variant="danger" onClick=\{\(\) => setConfirm\(true\)\}/);
});

test("cancel/resume reuse the same manual-sync fallback affordance as plan changes when sync does not converge", () => {
  assert.match(source, /pendingSync \? \(\s*<Button variant="secondary" className="billing-inline-refresh" onClick=\{handleManualSync\}/);
});

test("bounded cancel/resume retry stays finite: PLAN_SYNC_MAX_ATTEMPTS is unchanged and reused, not a new unbounded constant", () => {
  const matches = source.match(/PLAN_SYNC_MAX_ATTEMPTS\s*=\s*4/g);
  assert.ok(matches && matches.length === 1, "PLAN_SYNC_MAX_ATTEMPTS must be defined exactly once and reused everywhere");
});

test("plan-picker CTA and click routing depend on isActiveSubscription, not row existence, for every terminal status", () => {
  assert.match(
    source,
    /const isCurrent = isActiveSubscription && currentPlanCode === planCode;/,
  );
  assert.match(
    source,
    /\(isActiveSubscription \? `\$\{PLAN_LABELS\[planCode\]\} planına geç` : `\$\{PLAN_LABELS\[planCode\]\} planıyla başla`\)|isActiveSubscription \? `\$\{PLAN_LABELS\[planCode\]\} planına geç`/,
  );
  assert.match(
    source,
    /\(isActiveSubscription && hasPendingUpgrade\)/,
    "pending-upgrade disable must not fire for a terminal subscription that has no such concept",
  );
});
