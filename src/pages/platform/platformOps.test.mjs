import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  canApproveSignup,
  canProvisionSignup,
  canRejectSignup,
  hasEffectiveOwnerInvitation,
  labelFor,
  needsManualInvitationDelivery,
  normalizeApiError,
  normalizeManualLinkError,
  ownerInvitationStatusLabel,
  readinessLabels,
  signupStatusLabels,
} from "./platformOps.js";
import {
  blockerLabel,
  countRows,
  deriveReadiness,
  platformLabels,
  platformLocales,
  statusLabel,
  statusLabels,
} from "./platformI18n.js";

test("frontend regression: React mounts into #app, so diagnostics must not probe #root", async () => {
  const [indexHtml, mainSource] = await Promise.all([
    readFile("index.html", "utf8"),
    readFile("src/main.jsx", "utf8"),
  ]);

  assert.match(indexHtml, /<div id="app"><\/div>/);
  assert.doesNotMatch(indexHtml, /id="root"/);
  assert.match(mainSource, /document\.querySelector\("#app"\)/);
  assert.doesNotMatch(mainSource, /document\.querySelector\("#root"\)/);
});

const statusValues = [
  "pending",
  "reviewing",
  "approved",
  "rejected",
  "provisioned",
  "trial",
  "active",
  "suspended",
  "archived",
  "awaiting_owner",
  "onboarding",
  "ready",
  "blocked",
  "completed",
  "manual_delivery_required",
];

test("signup action availability follows Phase 20B state machine", () => {
  assert.equal(canApproveSignup({ status: "pending" }), true);
  assert.equal(canApproveSignup({ status: "approved" }), false);
  assert.equal(canRejectSignup({ status: "approved" }), true);
  assert.equal(canProvisionSignup({ status: "approved" }), true);
  assert.equal(canProvisionSignup({ status: "approved", provisioned_market_id: "market-id" }), false);
  assert.equal(canProvisionSignup({ status: "pending" }), false);
});

test("status and readiness helpers normalize operator-facing values", () => {
  assert.equal(labelFor(signupStatusLabels, "under_review"), "İnceleniyor");
  assert.equal(labelFor(signupStatusLabels, "reviewing"), "İnceleniyor");
  assert.equal(labelFor(readinessLabels, "awaiting_owner"), "Owner bekleniyor");
  assert.equal(labelFor(readinessLabels, "unknown"), "Bilinmeyen durum: unknown");
});

test("error and invitation helpers avoid raw object display", () => {
  assert.equal(normalizeApiError({}), "İşlem tamamlanamadı.");
  assert.equal(normalizeApiError("Plain error"), "Plain error");
  assert.equal(normalizeApiError({ message: "Readable error" }), "Readable error");
  assert.equal(normalizeApiError({ body: { detail: "API detail" } }), "API detail");
  assert.equal(normalizeApiError({ message: { detail: "Nested detail" } }), "Nested detail");
  assert.notEqual(normalizeApiError({ message: { detail: "" } }), "[object Object]");
  assert.equal(hasEffectiveOwnerInvitation({ owner_invitation: { is_effective: true } }), true);
  assert.equal(hasEffectiveOwnerInvitation({ owner_invitation: { is_effective: false } }), false);
});

test("public signup submit button has visible and accessible labels", async () => {
  const source = await readFile("src/pages/Start.jsx", "utf8");
  assert.match(source, /Başvuruyu Gönder/);
  assert.match(source, /Gönderiliyor\.\.\./);
  assert.match(source, /aria-busy=\{state\.loading\}/);
  assert.match(source, /disabled=\{state\.loading\}/);
  assert.match(source, /if \(state\.loading\) return;/);
});

test("platform login has accessible labels, visible submit text, loading state, normalized errors, and duplicate submit guard", async () => {
  const source = await readFile("src/pages/platform/PlatformLogin.jsx", "utf8");
  assert.match(source, /htmlFor="platform-admin-email"/);
  assert.match(source, /htmlFor="platform-admin-password"/);
  assert.match(source, /type=\{showPassword \? "text" : "password"\}/);
  assert.match(source, /aria-label=\{showPassword \? t\("hidePassword"\) : t\("showPassword"\)\}/);
  assert.match(source, /t\("signingIn"\) : t\("signIn"\)/);
  assert.match(source, /role="alert"/);
  assert.match(source, /normalizeLoginError/);
  assert.match(source, /if \(loading\) return;/);
  assert.match(source, /disabled=\{loading\}/);
});

test("tr/en/fr/de status label parity covers platform statuses", () => {
  for (const locale of platformLocales) {
    for (const value of statusValues) {
      assert.equal(typeof statusLabels[locale][value], "string", `${locale}.${value}`);
      assert.notEqual(statusLabels[locale][value], value, `${locale}.${value} should not leak raw enum`);
    }
  }
});

test("Turkish platform labels do not render raw technical readiness and lifecycle values", () => {
  assert.equal(statusLabel("completed", "tr"), "Tamamlandı");
  assert.equal(statusLabel("onboarding", "tr"), "Kurulumda");
  assert.equal(statusLabel("trial", "tr"), "Deneme");
  assert.equal(statusLabel("awaiting_owner", "tr"), "Owner bekleniyor");
  assert.equal(blockerLabel("Required market setup is not complete.", "tr"), "Gerekli market kurulumu tamamlanmadı");
  assert.equal(blockerLabel("No active owner user or effective owner invitation.", "tr"), "Owner daveti henüz kabul edilmedi");
});

test("readiness blockers are derived as readable translated messages", () => {
  const readiness = deriveReadiness({
    lifecycle_status: "trial",
    onboarding_status: "not_started",
    member_count: 0,
    product_count: 0,
    campaign_count: 2,
    legal_name: "Vatan Market",
    country_code: "FR",
    language: "tr",
    currency: "EUR",
    timezone: "Europe/Paris",
  });

  assert.equal(readiness.status, "onboarding");
  assert.deepEqual(readiness.blockers.map((blocker) => blocker.code), [
    "active_user_missing",
    "onboarding_incomplete",
    "product_required",
  ]);
  assert.equal(blockerLabel(readiness.blockers[0], "tr"), "Aktif kullanıcı bulunmuyor");
  assert.equal(blockerLabel(readiness.blockers[1], "tr"), "Onboarding tamamlanmadı");
  assert.equal(blockerLabel(readiness.blockers[2], "tr"), "En az bir ürün eklenmeli");
});

test("backend readiness blockers are translated and enriched with specific setup blockers", () => {
  const readiness = deriveReadiness({
    lifecycle_status: "trial",
    onboarding_status: "not_started",
    product_count: 0,
    campaign_count: 2,
    legal_name: "Vatan Market",
    country_code: "FR",
    language: "tr",
    currency: "EUR",
    timezone: "Europe/Paris",
    readiness: {
      state: "onboarding",
      blockers: ["Required market setup is not complete."],
      has_active_market_user: true,
      required_setup_complete: false,
    },
  });

  assert.equal(readiness.status, "onboarding");
  assert.deepEqual(readiness.blockers.map((blocker) => blocker.code), [
    "required_setup_incomplete",
    "onboarding_incomplete",
    "product_required",
  ]);
});

test("product and campaign counts render with explicit labels", () => {
  assert.deepEqual(countRows({ product_count: 0, campaign_count: 2 }, "tr"), [
    { label: "Ürün", value: 0 },
    { label: "Kampanya", value: 2 },
  ]);
});

test("unknown blocker and status fall back safely", () => {
  assert.equal(statusLabel("new_future_status", "tr"), "Bilinmeyen durum: new_future_status");
  assert.equal(blockerLabel({ code: "new_future_blocker", details: { product_count: 0 } }, "tr"), "Bilinmeyen durum: new_future_blocker");
  assert.doesNotMatch(blockerLabel({ details: { product_count: 0 } }, "tr"), /\[object Object\]/);
});

test("platform label dictionaries have tr/en/fr/de parity", () => {
  const referenceKeys = Object.keys(platformLabels.tr).sort();
  for (const locale of platformLocales) {
    assert.deepEqual(Object.keys(platformLabels[locale]).sort(), referenceKeys, locale);
  }
});

test("manual invitation status is localized and duplicate semantic states render once", () => {
  const invitation = { status: "manual_delivery_required", delivery_status: "manual_delivery_required", is_effective: true };
  assert.equal(statusLabel("manual_delivery_required", "tr"), "Manuel teslim gerekli");
  assert.equal(ownerInvitationStatusLabel(invitation), "Manuel teslim gerekli");
  assert.equal(needsManualInvitationDelivery(invitation), true);
  assert.equal(needsManualInvitationDelivery({ ...invitation, is_effective: false }), false);
  assert.equal(ownerInvitationStatusLabel({ status: "sent", delivery_status: "failed" }), "Gönderildi · Başarısız");
  assert.equal(ownerInvitationStatusLabel({ status: "future_state", delivery_status: "future_state" }), "Bilinmeyen durum");
});

test("manual invitation link errors are localized and actionable", () => {
  assert.match(normalizeManualLinkError({ status: 404 }), /Kullanılabilir davet bulunamadı/);
  assert.match(normalizeManualLinkError({ status: 409 }), /Manuel teslim artık gerekli değil/);
  assert.match(normalizeManualLinkError({ status: 500 }), /Güvenli davet bağlantısı oluşturulamadı/);
});

test("manual invitation UI uses the safe API flow without persistent URL storage", async () => {
  const source = await readFile("src/pages/platform/PlatformMarketDetail.jsx", "utf8");
  assert.match(source, /needsManualInvitationDelivery\(market\.owner_invitation\)/);
  assert.match(source, /createManualOwnerInvitationLink\(id\)/);
  assert.match(source, /navigator\.clipboard\.writeText\(response\.accept_url\)/);
  assert.match(source, /await load\(\)/);
  assert.doesNotMatch(source, /localStorage|sessionStorage/);
});
