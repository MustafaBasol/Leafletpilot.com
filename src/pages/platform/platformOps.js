export const signupStatusLabels = {
  pending: "Bekliyor",
  reviewing: "İncelemede",
  under_review: "İncelemede",
  approved: "Onaylandı",
  rejected: "Reddedildi",
  provisioned: "Provision edildi",
};

export const readinessLabels = {
  awaiting_owner: "Owner bekliyor",
  onboarding: "Onboarding",
  ready: "Hazır",
  suspended: "Askıda",
  blocked: "Blokeli",
};

export const lifecycleLabels = {
  trial: "Deneme",
  active: "Aktif",
  suspended: "Askıda",
  archived: "Arşivli",
};

export function labelFor(map, value) {
  return map[value] || value || "-";
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
  if (!error) return "İşlem tamamlanamadı.";
  if (typeof error === "string" && error.trim()) return error;
  if (typeof error.message === "string" && error.message.trim()) return error.message;
  if (typeof error.body?.detail === "string" && error.body.detail.trim()) return error.body.detail;
  if (typeof error.body?.message === "string" && error.body.message.trim()) return error.body.message;
  if (typeof error.message?.detail === "string" && error.message.detail.trim()) return error.message.detail;
  return "İşlem tamamlanamadı.";
}

export function hasEffectiveOwnerInvitation(market) {
  return Boolean(market?.owner_invitation?.is_effective);
}
