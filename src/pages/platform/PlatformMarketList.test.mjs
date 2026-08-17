import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const source = await readFile(new URL("./PlatformMarketList.jsx", import.meta.url), "utf8");

// ---------------------------------------------------------------------------
// PR #69 final closure round — PART C: Platform Admin market list gets a
// "Plan" column (public display names only, never raw "standard"/"growth")
// and a composable `plan=` filter alongside the existing lifecycle/readiness/
// billing_sync filters.
// ---------------------------------------------------------------------------

test("plan filter options and public labels mirror the backend canonical codes — never expose 'standard'/'growth'", () => {
  assert.match(source, /const planFilterOptions = \["starter", "standard", "pro", "unassigned"\];/);
  assert.match(source, /const planLabels = \{ starter: "Başlangıç", standard: "Plus", pro: "Pro", unassigned: "Atanmamış" \};/);
  assert.doesNotMatch(source, /<option[^>]*>\s*standard\s*<\/option>/i);
  assert.doesNotMatch(source, />\s*growth\s*</i);
});

test("filters state includes a plan field alongside the existing filters, and the effect depends on it", () => {
  assert.match(source, /useState\(\{ lifecycle_status: "", readiness: "", billing_sync_status: "", plan: "" \}\)/);
  assert.match(source, /\[filters\.lifecycle_status, filters\.readiness, filters\.billing_sync_status, filters\.plan\]/);
});

function planSelectBlock() {
  const selectStart = source.indexOf("<select value={filters.plan}");
  assert.ok(selectStart !== -1, "the plan filter <select> must exist");
  const selectEnd = source.indexOf("</select>", selectStart);
  return source.slice(selectStart, selectEnd);
}

test("a 'Tüm planlar' (all plans) filter option exists and each plan option sends the correct value", () => {
  const block = planSelectBlock();
  assert.match(block, /<option value="">Tüm planlar<\/option>/);
  assert.match(block, /planFilterOptions\.map\(\(code\) => \(/);
  assert.match(block, /<option key=\{code\} value=\{code\}>\{planLabels\[code\]\}<\/option>/);
});

test("changing the plan filter updates state via setFilters, same pattern as the other filters", () => {
  const block = planSelectBlock();
  assert.match(block, /onChange=\{\(event\) => setFilters\(\{ \.\.\.filters, plan: event\.target\.value \}\)\}/);
});

test("existing lifecycle/readiness/billing_sync filters are preserved, not replaced", () => {
  assert.match(source, /const lifecycleOptions = \["trial", "active", "suspended", "archived"\];/);
  assert.match(source, /const readinessOptions = \["awaiting_owner", "onboarding", "ready", "suspended", "blocked"\];/);
  assert.match(source, /const billingSyncOptions = \["ok", "error", "no_subscription"\];/);
  assert.match(source, /filters\.lifecycle_status/);
  assert.match(source, /filters\.readiness/);
  assert.match(source, /filters\.billing_sync_status/);
});

test("Plan column header is placed in the table, and every row renders the public display label", () => {
  assert.match(
    source,
    /columns=\{\[t\("market"\), t\("lifecycle"\), t\("readiness"\), "Faturalandırma", "Plan", t\("ownerInvitation"\), t\("onboarding"\), t\("members"\), ""\]\}/,
  );
  assert.match(
    source,
    /<td><Badge>\{market\.subscription_plan_display \|\| planLabels\[market\.subscription_plan\] \|\| market\.subscription_plan\}<\/Badge><\/td>/,
  );
});

test("Plan cell renders the server-provided display label first (never re-derives 'standard'/'growth' as a label)", () => {
  const cellMatch = source.match(/<td><Badge>\{market\.subscription_plan_display[^<]*<\/Badge><\/td>/);
  assert.ok(cellMatch, "plan cell must exist");
  assert.match(cellMatch[0], /market\.subscription_plan_display \|\|/, "must prefer the backend's normalized display label");
});

test("no layout regression: the market row still renders name/slug, lifecycle, readiness, billing, owner invitation, onboarding, members, and the open link", () => {
  const rowStart = source.indexOf("{items.map((market) => (");
  const rowEnd = source.indexOf("))}", rowStart);
  const row = source.slice(rowStart, rowEnd);
  assert.match(row, /<strong>\{market\.name\}<\/strong><small>\{market\.slug\}<\/small>/);
  assert.match(row, /statusLabel\(market\.lifecycle_status\)/);
  assert.match(row, /statusLabel\(market\.readiness\?\.state\)/);
  assert.match(row, /billingSyncLabels\[market\.billing\?\.billing_sync_status\]/);
  assert.match(row, /ownerInvitationLabel\(market\.owner_invitation\)/);
  assert.match(row, /statusLabel\(market\.onboarding_status\)/);
  assert.match(row, /\{market\.member_count\}/);
  assert.match(row, /href=\{`#\/platform\/markets\/\$\{market\.id\}`\}/);
});

test("listMarkets is still called with the full filters object (plan included) via platformApi", () => {
  assert.match(source, /platformApi\s*\n\s*\.listMarkets\(filters\)/);
});
