import assert from "node:assert/strict";
import { test } from "node:test";
import {
  buildWhatsAppDeepLink,
  describeFailureReason,
  formatCountdown,
  formatWhatsAppStatus,
  isVerificationLive,
  MEMBER_ACTIONABLE_STATUSES,
  secondsUntil,
  WHATSAPP_FAILURE_REASON_LABELS,
  WHATSAPP_STATUS_LABELS,
  WHATSAPP_STATUS_TONES,
} from "./whatsappStatus.js";

const BACKEND_MEMBER_STATUSES = ["not_configured", "pending", "verified", "expired", "revoked"];
const REAL_BADGE_TONES = new Set(["neutral", "primary", "success", "warning", "danger"]);

test("every backend WhatsApp member status has a Turkish label — none render raw", () => {
  for (const status of BACKEND_MEMBER_STATUSES) {
    assert.equal(typeof WHATSAPP_STATUS_LABELS[status], "string");
    assert.notEqual(WHATSAPP_STATUS_LABELS[status].trim(), "");
    assert.notEqual(WHATSAPP_STATUS_LABELS[status], status);
  }
});

test("every mapped tone is a tone that actually exists on Badge", () => {
  for (const status of BACKEND_MEMBER_STATUSES) {
    assert.ok(REAL_BADGE_TONES.has(WHATSAPP_STATUS_TONES[status]), `unexpected tone for "${status}"`);
  }
});

test("formatWhatsAppStatus maps every known status to its label + tone", () => {
  for (const status of BACKEND_MEMBER_STATUSES) {
    const { label, tone } = formatWhatsAppStatus(status);
    assert.equal(label, WHATSAPP_STATUS_LABELS[status]);
    assert.equal(tone, WHATSAPP_STATUS_TONES[status]);
  }
});

test("formatWhatsAppStatus falls back to a safe neutral label for an unknown status instead of rendering it raw", () => {
  assert.deepEqual(formatWhatsAppStatus("some_future_status"), { label: "Bilinmiyor", tone: "neutral" });
  assert.deepEqual(formatWhatsAppStatus(undefined), { label: "Bilinmiyor", tone: "neutral" });
  assert.deepEqual(formatWhatsAppStatus(null), { label: "Bilinmiyor", tone: "neutral" });
});

test("secondsUntil returns remaining whole seconds and clamps at 0", () => {
  const now = Date.parse("2026-08-17T10:00:00Z");
  assert.equal(secondsUntil("2026-08-17T10:05:00Z", now), 300);
  assert.equal(secondsUntil("2026-08-17T09:59:00Z", now), 0);
  assert.equal(secondsUntil("2026-08-17T10:00:00Z", now), 0);
});

test("secondsUntil returns null for a missing or invalid date", () => {
  const now = Date.now();
  assert.equal(secondsUntil(null, now), null);
  assert.equal(secondsUntil(undefined, now), null);
  assert.equal(secondsUntil("", now), null);
  assert.equal(secondsUntil("not-a-date", now), null);
});

test("formatCountdown renders m:ss with zero-padded seconds", () => {
  assert.equal(formatCountdown(545), "9:05");
  assert.equal(formatCountdown(60), "1:00");
  assert.equal(formatCountdown(9), "0:09");
  assert.equal(formatCountdown(0), "0:00");
});

test("formatCountdown returns an empty string for null/undefined", () => {
  assert.equal(formatCountdown(null), "");
  assert.equal(formatCountdown(undefined), "");
});

test("isVerificationLive is true only for a pending verification with time left", () => {
  const now = Date.parse("2026-08-17T10:00:00Z");
  assert.equal(isVerificationLive({ status: "pending", expires_at: "2026-08-17T10:05:00Z" }, now), true);
  assert.equal(isVerificationLive({ status: "pending", expires_at: "2026-08-17T09:59:00Z" }, now), false);
  assert.equal(isVerificationLive({ status: "verified", expires_at: "2026-08-17T10:05:00Z" }, now), false);
  assert.equal(isVerificationLive(null, now), false);
});

test("buildWhatsAppDeepLink URL-encodes the code and returns an empty string when either argument is missing", () => {
  assert.equal(
    buildWhatsAppDeepLink("+33612345678", "LP-X7K4-M92Q"),
    "https://wa.me/33612345678?text=LP-X7K4-M92Q",
  );
  assert.equal(buildWhatsAppDeepLink("", "LP-X7K4-M92Q"), "");
  assert.equal(buildWhatsAppDeepLink("+33612345678", ""), "");
  assert.equal(buildWhatsAppDeepLink(null, null), "");
});

test("MEMBER_ACTIONABLE_STATUSES only offers verification actions for statuses without a live/verified channel", () => {
  assert.deepEqual([...MEMBER_ACTIONABLE_STATUSES].sort(), ["expired", "not_configured", "revoked"].sort());
  assert.equal(MEMBER_ACTIONABLE_STATUSES.has("pending"), false);
  assert.equal(MEMBER_ACTIONABLE_STATUSES.has("verified"), false);
});

// Every reason code the backend can persist in whatsapp_verifications.failure_reason.
const BACKEND_FAILURE_REASONS = [
  "expired",
  "attempt_limit",
  "superseded",
  "identity_revoked",
  "revoked_by_platform_admin",
  "user_inactive",
  "membership_revoked",
  "phone_already_linked",
  "user_already_verified",
];

test("every backend failure reason has a Turkish explanation — none renders raw", () => {
  for (const reason of BACKEND_FAILURE_REASONS) {
    const label = WHATSAPP_FAILURE_REASON_LABELS[reason];
    assert.ok(label, `missing a Turkish explanation for failure reason "${reason}"`);
    assert.notEqual(label, reason);
    assert.equal(describeFailureReason(reason), label);
  }
});

test("an unknown or missing failure reason falls back to a sentence, never the raw code", () => {
  const fallback = describeFailureReason(null);
  assert.ok(fallback.length > 10);
  assert.equal(describeFailureReason("some_new_backend_reason"), fallback);
  assert.doesNotMatch(describeFailureReason("some_new_backend_reason"), /some_new_backend_reason/);
});
