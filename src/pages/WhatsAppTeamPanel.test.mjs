import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const page = readFileSync(new URL("./WhatsAppTeamPanel.jsx", import.meta.url), "utf8");

test("verification polling runs every 5000ms, never faster", () => {
  const pollBlock = page.slice(page.indexOf("Poll the verification"), page.indexOf("function openVerifyModal"));
  const intervalCalls = pollBlock.match(/window\.setInterval\(/g) || [];
  assert.equal(intervalCalls.length, 1, "expected exactly one setInterval call in the poll effect");
  assert.match(pollBlock, /\}, 5000\);/);
});

test("the countdown tick runs at 1000ms", () => {
  const tickBlock = page.slice(page.indexOf("Countdown tick"), page.indexOf("Poll the verification"));
  assert.match(tickBlock, /setNowMs\(Date\.now\(\)\)/);
  assert.match(tickBlock, /\}, 1000\);/);
});

test("both intervals are cleared in their effect cleanup", () => {
  const tickBlock = page.slice(page.indexOf("Countdown tick"), page.indexOf("Poll the verification"));
  assert.match(tickBlock, /return \(\) => window\.clearInterval\(tickId\);/);

  const pollBlock = page.slice(page.indexOf("Poll the verification"), page.indexOf("function openVerifyModal"));
  assert.match(pollBlock, /return \(\) => window\.clearInterval\(pollId\);/);
  // The poll also self-clears once the local countdown reaches zero, even before the effect re-runs.
  assert.match(pollBlock, /window\.clearInterval\(pollId\);\s*\n\s*return;/);
});

test("the verification code is never written to the console", () => {
  assert.doesNotMatch(page, /console\.(log|debug|info|warn|error)\([^)]*(code|verification)/i);
  assert.doesNotMatch(page, /console\./);
});

test("permission gating: only can_manage_members or the member's own can_manage row gets action buttons", () => {
  assert.match(page, /canActOnMember = Boolean\(status\.can_manage_members \|\| member\.can_manage\)/);
  assert.match(page, /Bu kaydı yalnızca market yöneticisi yönetebilir\./);
});

test("the WhatsApp deep link opens safely in a new tab", () => {
  assert.match(page, /target="_blank"/);
  assert.match(page, /rel="noopener noreferrer"/);
  assert.match(page, /whatsapp_deep_link/);
});

test("revoking WhatsApp access is guarded by ConfirmDialog, not a direct click handler", () => {
  assert.match(page, /<ConfirmDialog[\s\S]*?isOpen=\{Boolean\(revokeTarget\)\}/);
  assert.match(page, /onConfirm=\{confirmRevoke\}/);
  assert.match(page, /await revokeMemberWhatsApp\(revokeTarget\.membership_id, null\)/);
});

test("no raw backend status enum is ever interpolated directly into JSX text", () => {
  assert.doesNotMatch(page, />\{member\.status\}</);
  assert.doesNotMatch(page, />\{verification\.status\}</);
  assert.doesNotMatch(page, />\{effectiveStatus\}</);
});

test("member status always renders through formatWhatsAppStatus + Badge", () => {
  assert.match(page, /formatWhatsAppStatus\(member\.status\)/);
  assert.match(page, /<Badge tone=\{tone\}>\{label\}<\/Badge>/);
});

test("no raw failure_reason enum reaches the screen — it goes through describeFailureReason", () => {
  assert.match(page, /describeFailureReason\(verification\.failure_reason\)/);
  assert.doesNotMatch(page, /\{verification\.failure_reason \|\|/);
  assert.doesNotMatch(page, />\{verification\.failure_reason\}</);
});

test("closing the dialog does not silently cancel a live code", () => {
  const closeBlock = page.slice(page.indexOf("function closeModal()"), page.indexOf("async function handleCancelVerification"));
  assert.doesNotMatch(closeBlock, /cancelWhatsAppVerification/);
  // Cancelling is an explicit, separately wired action instead.
  assert.match(page, /await cancelWhatsAppVerification\(verification\.verification_id\)/);
  assert.match(page, /onClick=\{handleCancelVerification\}/);
  assert.match(page, /Doğrulamayı İptal Et/);
});

test("a pending member row stays actionable and shows when the code expires", () => {
  assert.match(page, /MEMBER_ACTIONABLE_STATUSES\.has\(member\.status\) \|\| member\.status === "pending"/);
  assert.match(page, /member\.status === "pending" \? "Yeni Kod Oluştur" : "WhatsApp ile Doğrula"/);
  assert.match(page, /member\.pending_expires_at/);
});

test("disabled channel and load-failure states render no dead action buttons", () => {
  const disabledBlock = page.slice(page.indexOf("if (!status?.enabled)"), page.indexOf("const members = status.members"));
  assert.match(disabledBlock, /EmptyState/);
  assert.doesNotMatch(disabledBlock, /<Button/);
});
