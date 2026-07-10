import { statusLabel, t } from "./platformI18n.js";

export const signupStatusLabels = {
  pending: statusLabel("pending"),
  reviewing: statusLabel("reviewing"),
  under_review: statusLabel("reviewing"),
  approved: statusLabel("approved"),
  rejected: statusLabel("rejected"),
  provisioned: statusLabel("provisioned"),
};

export const readinessLabels = {
  awaiting_owner: statusLabel("awaiting_owner"),
  onboarding: statusLabel("onboarding"),
  ready: statusLabel("ready"),
  suspended: statusLabel("suspended"),
  blocked: statusLabel("blocked"),
};

export const lifecycleLabels = {
  trial: statusLabel("trial"),
  active: statusLabel("active"),
  suspended: statusLabel("suspended"),
  archived: statusLabel("archived"),
};

export function labelFor(map, value) {
  return map[value] || statusLabel(value);
}

export function canApproveSignup(signup) {
  return ["pending", "reviewing"].includes(signup?.status);
}

export function canRejectSignup(signup) {
  return ["pending", "reviewing", "approved"].includes(signup?.status);
}

export function canProvisionSignup(signup) {
  return signup?.status === "approved" && !signup?.provisioned_market_id;
}

export function normalizeApiError(error) {
  if (!error) return t("operationFailed");
  if (typeof error === "string" && error.trim()) return error;
  if (typeof error.message === "string" && error.message.trim()) return error.message;
  if (typeof error.body?.detail === "string" && error.body.detail.trim()) return error.body.detail;
  if (typeof error.body?.message === "string" && error.body.message.trim()) return error.body.message;
  if (typeof error.message?.detail === "string" && error.message.detail.trim()) return error.message.detail;
  return t("operationFailed");
}

export function hasEffectiveOwnerInvitation(market) {
  return Boolean(market?.owner_invitation?.is_effective);
}
