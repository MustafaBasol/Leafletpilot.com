import { statusLabel, statusLabels, t } from "./platformI18n.js";

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

export function ownerInvitationStatusLabel(invitation, locale = "tr") {
  if (!invitation) return t("none", locale);
  const status = invitation.status;
  const deliveryStatus = invitation.delivery_status;
  if (!status && !deliveryStatus) return t("unknownStatus", locale);
  if (!deliveryStatus || status === deliveryStatus) return ownerStatusLabel(status || deliveryStatus, locale);
  if (!status) return ownerStatusLabel(deliveryStatus, locale);
  return `${ownerStatusLabel(status, locale)} · ${ownerStatusLabel(deliveryStatus, locale)}`;
}

function ownerStatusLabel(value, locale) {
  return typeof value === "string" && statusLabels[locale]?.[value]
    ? statusLabel(value, locale)
    : t("unknownStatus", locale);
}

export function needsManualInvitationDelivery(invitation) {
  return Boolean(
    invitation?.is_effective &&
      (invitation.status === "manual_delivery_required" || invitation.delivery_status === "manual_delivery_required"),
  );
}

export function normalizeManualLinkError(error) {
  if (error?.status === 404) return t("manualLinkNotFound");
  if (error?.status === 409) return t("manualLinkConflict");
  return t("manualLinkFailed");
}

export function hasEffectiveOwnerInvitation(market) {
  return Boolean(market?.owner_invitation?.is_effective);
}
