// Pure helpers for the Platform Admin > WhatsApp (Evolution) screen.
// No React here — keep this file trivially unit-testable with node:test.

// Every backend identity status must have a label; nothing renders a raw enum.
export const WHATSAPP_IDENTITY_STATUS_LABELS = {
  verified: "Doğrulandı",
  revoked: "İptal edildi",
};

// Tones must match what src/components/ui/Badge.jsx actually renders (badge-<tone> classes
// that exist in src/styles.css): success, warning, danger, neutral.
export const WHATSAPP_IDENTITY_STATUS_TONES = {
  verified: "success",
  revoked: "danger",
};

const MARKET_ROLE_LABELS = {
  market_admin: "Yönetici",
  market_staff: "Personel",
  viewer: "Görüntüleyici",
};

export function formatIdentityStatus(status) {
  const label = WHATSAPP_IDENTITY_STATUS_LABELS[status];
  if (!label) return { label: "Bilinmiyor", tone: "neutral" };
  return { label, tone: WHATSAPP_IDENTITY_STATUS_TONES[status] || "neutral" };
}

export function describeMarketRole(role) {
  return MARKET_ROLE_LABELS[role] || "Bilinmeyen rol";
}

// Connection health badge. Order of checks matters — enabled must be checked before
// configured, and configured before connection_ok, per the backend contract.
export function describeConnection(health) {
  if (!health || health.enabled !== true) {
    return { label: "Devre dışı", tone: "neutral", detail: null };
  }
  if (health.configured === false) {
    return { label: "Yapılandırılmamış", tone: "warning", detail: null };
  }
  if (health.connection_ok === true) {
    return { label: "Bağlı", tone: "success", detail: null };
  }
  if (health.connection_ok === false) {
    return { label: "Bağlantı yok", tone: "danger", detail: health.last_connection_error || null };
  }
  // connection_ok is null/undefined — channel enabled and configured, but never probed yet.
  return { label: "Bilinmiyor", tone: "neutral", detail: null };
}

// Compact "Paris Market, Lyon Market (+1)" style summary for a multi-market identity row.
// `shown` carries the first `limit` entries (with role) for line-by-line rendering in the cell.
export function summarizeMarkets(markets, { limit = 2 } = {}) {
  const list = Array.isArray(markets) ? markets.filter(Boolean) : [];
  const shown = list.slice(0, limit);
  const extraCount = Math.max(list.length - shown.length, 0);
  const text = shown.map((market) => market.market_name || market.market_slug || "Bilinmeyen market").join(", ");
  return { text, extraCount, shown, total: list.length };
}

// Strips everything but digits so a pasted "+33 6 12" becomes "33612" before it is sent
// to the backend `phone` filter (which matches on digits).
export function sanitizePhoneFilter(value) {
  if (typeof value !== "string") return "";
  return value.replace(/\D+/g, "");
}

// Builds the query params object for listWhatsAppIdentities — empty and "all" values are
// omitted entirely so they are never sent as empty-string query params.
export function buildIdentityQuery({ marketId, status, search, phone, limit, offset } = {}) {
  const params = {};
  if (marketId && marketId !== "all") params.market_id = marketId;
  if (status && status !== "all") params.status = status;
  const trimmedSearch = typeof search === "string" ? search.trim() : "";
  if (trimmedSearch) params.search = trimmedSearch;
  const sanitizedPhone = sanitizePhoneFilter(phone);
  if (sanitizedPhone) params.phone = sanitizedPhone;
  if (Number.isFinite(limit)) params.limit = limit;
  if (Number.isFinite(offset) && offset >= 0) params.offset = offset;
  return params;
}

export function formatDateTime(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleString("tr-TR");
}
