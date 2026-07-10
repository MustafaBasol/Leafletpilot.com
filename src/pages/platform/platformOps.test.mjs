import test from "node:test";
import assert from "node:assert/strict";

import {
  canApproveSignup,
  canProvisionSignup,
  canRejectSignup,
  hasEffectiveOwnerInvitation,
  labelFor,
  normalizeApiError,
  readinessLabels,
  signupStatusLabels,
} from "./platformOps.js";

test("signup action availability follows Phase 20B state machine", () => {
  assert.equal(canApproveSignup({ status: "pending" }), true);
  assert.equal(canApproveSignup({ status: "approved" }), false);
  assert.equal(canRejectSignup({ status: "approved" }), true);
  assert.equal(canProvisionSignup({ status: "approved" }), true);
  assert.equal(canProvisionSignup({ status: "approved", provisioned_market_id: "market-id" }), false);
  assert.equal(canProvisionSignup({ status: "pending" }), false);
});

test("status and readiness labels normalize operator-facing values", () => {
  assert.equal(labelFor(signupStatusLabels, "under_review"), "İncelemede");
  assert.equal(labelFor(signupStatusLabels, "reviewing"), "İncelemede");
  assert.equal(labelFor(readinessLabels, "awaiting_owner"), "Owner bekliyor");
  assert.equal(labelFor(readinessLabels, "unknown"), "unknown");
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
