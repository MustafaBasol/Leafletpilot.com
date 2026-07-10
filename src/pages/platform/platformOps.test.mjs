import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  blockerLabel,
  countRows,
  deriveReadiness,
  platformLabels,
  platformLocales,
  statusLabel,
  statusLabels,
} from "./platformI18n.js";

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
];

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
