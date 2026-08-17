// Pure helpers for the market-user WhatsApp verification panel — no React, no DOM.
// Every backend status the WhatsApp integration can return must have a Turkish label here;
// a raw enum value must never reach the screen.

export const WHATSAPP_STATUS_LABELS = {
  not_configured: "Bağlı değil",
  pending: "Doğrulama bekleniyor",
  verified: "Doğrulandı",
  expired: "Süresi doldu",
  revoked: "İptal edildi",
};

// Only the tones that actually exist in src/components/ui/Badge.jsx: neutral, success, warning, danger.
export const WHATSAPP_STATUS_TONES = {
  not_configured: "neutral",
  pending: "warning",
  verified: "success",
  expired: "warning",
  revoked: "danger",
};

export function formatWhatsAppStatus(status) {
  const label = WHATSAPP_STATUS_LABELS[status];
  if (!label) {
    return { label: "Bilinmiyor", tone: "neutral" };
  }
  return { label, tone: WHATSAPP_STATUS_TONES[status] || "neutral" };
}

// Statuses for which a "Doğrula" / "Yeniden doğrula" action is offered.
export const MEMBER_ACTIONABLE_STATUSES = new Set(["not_configured", "expired", "revoked"]);

// The backend records why a challenge ended as a short machine reason code
// (whatsapp_verifications.failure_reason). Those are diagnostic strings, not
// copy — each one needs an explanation the market owner can act on, and the
// unknown case must fall back to a sentence rather than leaking the code.
export const WHATSAPP_FAILURE_REASON_LABELS = {
  expired: "Kodun süresi doldu. Yeni bir kod oluşturun.",
  attempt_limit: "Çok fazla hatalı deneme yapıldı. Yeni bir kod oluşturun.",
  superseded: "Bu kod yerine yeni bir kod oluşturuldu.",
  identity_revoked: "Bu kullanıcının WhatsApp erişimi kaldırıldı.",
  revoked_by_platform_admin: "Bu doğrulama LeafletPilot ekibi tarafından iptal edildi.",
  user_inactive: "LeafletPilot kullanıcısı aktif değil.",
  membership_revoked: "Kullanıcının bu markete erişimi artık yok.",
  phone_already_linked:
    "Kodun gönderildiği WhatsApp numarası başka bir LeafletPilot kullanıcısına bağlı. Önce o bağlantının kaldırılması gerekir.",
  user_already_verified:
    "Bu kullanıcının doğrulanmış başka bir WhatsApp numarası var. Önce mevcut doğrulamayı kaldırın.",
};

export function describeFailureReason(reason) {
  if (!reason) return "Doğrulama tamamlanamadı. Yeni bir kod oluşturabilirsiniz.";
  return WHATSAPP_FAILURE_REASON_LABELS[reason] || "Doğrulama tamamlanamadı. Yeni bir kod oluşturabilirsiniz.";
}

export function secondsUntil(isoString, nowMs) {
  if (!isoString) return null;
  const target = new Date(isoString).getTime();
  if (Number.isNaN(target)) return null;
  const diffMs = target - nowMs;
  const diffSeconds = Math.floor(diffMs / 1000);
  return diffSeconds > 0 ? diffSeconds : 0;
}

export function formatCountdown(seconds) {
  if (seconds === null || seconds === undefined || Number.isNaN(seconds)) return "";
  const clamped = Math.max(0, Math.floor(seconds));
  const minutes = Math.floor(clamped / 60);
  const remainder = clamped % 60;
  return `${minutes}:${String(remainder).padStart(2, "0")}`;
}

export function isVerificationLive(verification, nowMs) {
  if (!verification || verification.status !== "pending") return false;
  const remaining = secondsUntil(verification.expires_at, nowMs);
  return remaining !== null && remaining > 0;
}

export function buildWhatsAppDeepLink(officialNumber, code) {
  if (!officialNumber || !code) return "";
  const digits = officialNumber.replace(/[^\d]/g, "");
  if (!digits) return "";
  return `https://wa.me/${digits}?text=${encodeURIComponent(code)}`;
}
