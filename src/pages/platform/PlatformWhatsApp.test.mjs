import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const source = await readFile(new URL("./PlatformWhatsApp.jsx", import.meta.url), "utf8");

test("PlatformWhatsApp calls all four whatsapp platformApi methods", () => {
  assert.match(source, /platformApi\s*\n?\s*\.getWhatsAppHealth\(\)/);
  assert.match(source, /platformApi\.testWhatsAppConnection\(\)/);
  assert.match(source, /platformApi\s*\n?\s*\.listWhatsAppIdentities\(params\)/);
  assert.match(source, /platformApi\.revokeWhatsAppIdentity\(revokeTarget\.identity_id, \{ reason \}\)/);
});

test("user search and phone search are both debounced at 350ms, not fired per keystroke", () => {
  assert.match(source, /const SEARCH_DEBOUNCE_MS = 350;/);
  assert.match(source, /setTimeout\(\(\) => setDebouncedSearch\(searchTerm\.trim\(\)\), SEARCH_DEBOUNCE_MS\)/);
  assert.match(source, /setTimeout\(\(\) => setDebouncedPhone\(phoneTerm\.trim\(\)\), SEARCH_DEBOUNCE_MS\)/);
  // The list call must depend on the debounced values, not the raw keystroke state.
  assert.match(source, /search: debouncedSearch/);
  assert.match(source, /phone: debouncedPhone/);
  assert.doesNotMatch(source, /search: searchTerm[^.]/);
});

test("revoke goes through ConfirmDialog with a Turkish warning about losing WhatsApp access, plus an optional reason", () => {
  assert.match(source, /<ConfirmDialog/);
  assert.match(source, /isOpen=\{Boolean\(revokeTarget\)\}/);
  assert.match(source, /WhatsApp komut erişimini anında kaybedecek/);
  assert.match(source, /onConfirm=\{confirmRevoke\}/);
  assert.match(source, /placeholder="Neden \(isteğe bağlı\)"/);
  assert.match(source, /revokeReasons\[identity\.identity_id\]/);
  // Revoke must not fire directly from the row button — it must go through the dialog's onConfirm.
  assert.doesNotMatch(source, /onClick=\{confirmRevoke\}/);
});

test("no raw status enum is rendered — identity status always goes through formatIdentityStatus", () => {
  assert.match(source, /formatIdentityStatus\(identity\.status\)/);
  assert.doesNotMatch(source, /\{identity\.status\}/);
  assert.doesNotMatch(source, /<td>\{identity\.status\}<\/td>/);
});

test("connection test button is omitted entirely when the WhatsApp channel is disabled", () => {
  const disabledBranchStart = source.indexOf("health.enabled === false");
  assert.ok(disabledBranchStart !== -1, "must branch on health.enabled === false");
  const disabledBranch = source.slice(disabledBranchStart, source.indexOf("</Card>", disabledBranchStart));
  const [disabledMessage, restOfCard] = [
    disabledBranch.slice(0, disabledBranch.indexOf(") : (")),
    disabledBranch.slice(disabledBranch.indexOf(") : (")),
  ];
  assert.doesNotMatch(disabledMessage, /onTest/);
  assert.match(restOfCard, /onClick=\{onTest\}/);
});

test("connection health card still renders (not hidden) when the channel is disabled, explaining why", () => {
  assert.match(source, /WhatsApp kanalı bu ortamda devre dışı bırakılmış/);
});

test("a failed (ok:false) connection test renders as a warning with the backend's Turkish detail, not a thrown error", () => {
  assert.match(source, /testResult\.ok\s*\?\s*"inline-result-success"\s*:\s*"inline-result-warning"/);
  assert.match(source, /testResult\.detail \|\| "Bağlantı testi başarısız oldu\."/);
  assert.match(source, /catch \(err\) \{\s*setTestResult\(\{ ok: false, detail: normalizeApiError\(err\) \}\);/);
});

test("verified users table renders one row per identity — the multi-market cell uses summarizeMarkets rather than duplicating rows per market", () => {
  assert.match(source, /items\.map\(\(identity\) => \{/);
  assert.match(source, /<MarketsCell markets=\{identity\.markets\} \/>/);
  assert.match(source, /summarizeMarkets\(markets\)/);
  // Must not flat-map identities into one row per market.
  assert.doesNotMatch(source, /flatMap/);
  assert.doesNotMatch(source, /identity\.markets\.map\(\(market\) => <tr/);
});

test("MarketsCell shows each shown market's role and a '+N market daha' overflow indicator", () => {
  assert.match(source, /describeMarketRole\(market\.role\)/);
  assert.match(source, /\+\{summary\.extraCount\} market daha/);
});

test("revoked identities show their revocation reason as a table hint and never get a revoke button", () => {
  assert.match(source, /identity\.status === "revoked" && identity\.revoked_reason/);
  assert.match(source, /identity\.status === "verified" \?/);
});

test("phone filter is sanitized (digits only) before being sent, via buildIdentityQuery/sanitizePhoneFilter", () => {
  assert.match(source, /import \{[^}]*buildIdentityQuery[^}]*\} from "\.\/whatsappOps\.js";/s);
  assert.match(source, /buildIdentityQuery\(\{/);
});

test("a clear-filters control appears only when a filter is active", () => {
  assert.match(source, /const hasActiveFilter = Boolean\(/);
  assert.match(source, /\{hasActiveFilter \? \(/);
  assert.match(source, /Filtreleri Temizle/);
});

test("loading and error states are rendered with role=\"alert\" on failure", () => {
  assert.match(source, /normalizeApiError\(err\)/);
  assert.match(source, /role="alert">\{error\}/);
});

test("empty state uses the shared EmptyState component instead of a bare paragraph", () => {
  assert.match(source, /<EmptyState title="Kayıt yok"/);
});
