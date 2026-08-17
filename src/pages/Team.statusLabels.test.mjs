import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const page = readFileSync(new URL("./Team.jsx", import.meta.url), "utf8");

const BACKEND_INVITATION_STATUSES = [
  "pending",
  "sent",
  "manual_delivery_required",
  "accepted",
  "revoked",
  "expired",
  "failed",
];

test("every backend invitation status has a Turkish customer-facing label — none render raw", () => {
  for (const status of BACKEND_INVITATION_STATUSES) {
    assert.match(page, new RegExp(`${status}:\\s*"[^"]+"`), `missing a Turkish label for status "${status}"`);
  }
});

test("the raw enum value is never used as display text — status rendering always goes through the label map", () => {
  assert.match(page, /statusLabels\[invitation\.status\] \|\| invitation\.status/);
  assert.doesNotMatch(page, /manual_delivery_required<\//);
});

test("manual-share fallback (copy link) only appears for statuses where email delivery actually failed", () => {
  assert.match(page, /MANUAL_SHARE_STATUSES = new Set\(\["manual_delivery_required", "failed"\]\)/);
});
