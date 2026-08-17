import assert from "node:assert/strict";
import test from "node:test";
import {
  WHATSAPP_IDENTITY_STATUS_LABELS,
  WHATSAPP_IDENTITY_STATUS_TONES,
  buildIdentityQuery,
  describeConnection,
  describeMarketRole,
  formatDateTime,
  formatIdentityStatus,
  sanitizePhoneFilter,
  summarizeMarkets,
} from "./whatsappOps.js";

test("every backend identity status has a Turkish label and a Badge-compatible tone", () => {
  for (const status of Object.keys(WHATSAPP_IDENTITY_STATUS_LABELS)) {
    assert.equal(typeof WHATSAPP_IDENTITY_STATUS_LABELS[status], "string");
    assert.notEqual(WHATSAPP_IDENTITY_STATUS_LABELS[status], status);
    assert.match(WHATSAPP_IDENTITY_STATUS_TONES[status], /^(success|warning|danger|neutral)$/);
  }
  assert.equal(WHATSAPP_IDENTITY_STATUS_LABELS.verified, "Doğrulandı");
  assert.equal(WHATSAPP_IDENTITY_STATUS_LABELS.revoked, "İptal edildi");
});

test("formatIdentityStatus never leaks a raw enum and falls back safely", () => {
  assert.deepEqual(formatIdentityStatus("verified"), { label: "Doğrulandı", tone: "success" });
  assert.deepEqual(formatIdentityStatus("revoked"), { label: "İptal edildi", tone: "danger" });
  assert.deepEqual(formatIdentityStatus("some_future_status"), { label: "Bilinmiyor", tone: "neutral" });
  assert.deepEqual(formatIdentityStatus(undefined), { label: "Bilinmiyor", tone: "neutral" });
  assert.deepEqual(formatIdentityStatus(null), { label: "Bilinmiyor", tone: "neutral" });
});

test("describeMarketRole falls back for unknown roles", () => {
  assert.equal(describeMarketRole("market_admin"), "Yönetici");
  assert.equal(describeMarketRole("market_staff"), "Personel");
  assert.equal(describeMarketRole("viewer"), "Görüntüleyici");
  assert.equal(describeMarketRole("owner"), "Bilinmeyen rol");
  assert.equal(describeMarketRole(undefined), "Bilinmeyen rol");
});

test("describeConnection: channel not enabled", () => {
  assert.deepEqual(describeConnection({ enabled: false }), { label: "Devre dışı", tone: "neutral", detail: null });
});

test("describeConnection: enabled but not configured", () => {
  assert.deepEqual(
    describeConnection({ enabled: true, configured: false, connection_ok: null }),
    { label: "Yapılandırılmamış", tone: "warning", detail: null },
  );
});

test("describeConnection: connected", () => {
  assert.deepEqual(
    describeConnection({ enabled: true, configured: true, connection_ok: true }),
    { label: "Bağlı", tone: "success", detail: null },
  );
});

test("describeConnection: not connected surfaces the last connection error as detail", () => {
  assert.deepEqual(
    describeConnection({ enabled: true, configured: true, connection_ok: false, last_connection_error: "Zaman aşımı" }),
    { label: "Bağlantı yok", tone: "danger", detail: "Zaman aşımı" },
  );
  assert.deepEqual(
    describeConnection({ enabled: true, configured: true, connection_ok: false, last_connection_error: null }),
    { label: "Bağlantı yok", tone: "danger", detail: null },
  );
});

test("describeConnection: never probed (connection_ok is null/undefined) but configured", () => {
  assert.deepEqual(
    describeConnection({ enabled: true, configured: true, connection_ok: null }),
    { label: "Bilinmiyor", tone: "neutral", detail: null },
  );
  assert.deepEqual(
    describeConnection({ enabled: true, configured: true, connection_ok: undefined }),
    { label: "Bilinmiyor", tone: "neutral", detail: null },
  );
});

test("describeConnection tolerates null/undefined input without throwing", () => {
  assert.doesNotThrow(() => describeConnection(null));
  assert.doesNotThrow(() => describeConnection(undefined));
  assert.deepEqual(describeConnection(null), { label: "Devre dışı", tone: "neutral", detail: null });
  assert.deepEqual(describeConnection(undefined), { label: "Devre dışı", tone: "neutral", detail: null });
});

test("summarizeMarkets handles missing/empty input", () => {
  assert.deepEqual(summarizeMarkets(undefined), { text: "", extraCount: 0, shown: [], total: 0 });
  assert.deepEqual(summarizeMarkets(null), { text: "", extraCount: 0, shown: [], total: 0 });
  assert.deepEqual(summarizeMarkets([]), { text: "", extraCount: 0, shown: [], total: 0 });
});

test("summarizeMarkets handles a single market", () => {
  const result = summarizeMarkets([{ market_id: "1", market_name: "Paris Market" }]);
  assert.equal(result.text, "Paris Market");
  assert.equal(result.extraCount, 0);
  assert.equal(result.total, 1);
  assert.equal(result.shown.length, 1);
});

test("summarizeMarkets handles exactly two markets (no overflow)", () => {
  const result = summarizeMarkets([
    { market_id: "1", market_name: "Paris Market" },
    { market_id: "2", market_name: "Lyon Market" },
  ]);
  assert.equal(result.text, "Paris Market, Lyon Market");
  assert.equal(result.extraCount, 0);
  assert.equal(result.total, 2);
});

test("summarizeMarkets shows the first two and reports the rest as extraCount for 3+", () => {
  const result = summarizeMarkets([
    { market_id: "1", market_name: "Paris Market" },
    { market_id: "2", market_name: "Lyon Market" },
    { market_id: "3", market_name: "Nice Market" },
  ]);
  assert.equal(result.text, "Paris Market, Lyon Market");
  assert.equal(result.extraCount, 1);
  assert.equal(result.total, 3);
  assert.equal(result.shown.length, 2);
});

test("sanitizePhoneFilter strips everything but digits", () => {
  assert.equal(sanitizePhoneFilter("+33 6 12 34 56 78"), "33612345678");
  assert.equal(sanitizePhoneFilter("+33*******78"), "3378");
  assert.equal(sanitizePhoneFilter(""), "");
  assert.equal(sanitizePhoneFilter("abc"), "");
  assert.equal(sanitizePhoneFilter(undefined), "");
  assert.equal(sanitizePhoneFilter(null), "");
});

test("buildIdentityQuery omits empty and 'all' values entirely", () => {
  assert.deepEqual(buildIdentityQuery({}), {});
  assert.deepEqual(
    buildIdentityQuery({ marketId: "all", status: "all", search: "  ", phone: "", limit: undefined, offset: undefined }),
    {},
  );
});

test("buildIdentityQuery includes only the meaningful filters", () => {
  assert.deepEqual(
    buildIdentityQuery({ marketId: "market-1", status: "verified", search: "  ada  ", phone: "+33 6 12", limit: 50, offset: 0 }),
    { market_id: "market-1", status: "verified", search: "ada", phone: "33612", limit: 50, offset: 0 },
  );
});

test("buildIdentityQuery keeps offset when paginating past the first page", () => {
  assert.deepEqual(buildIdentityQuery({ offset: 50, limit: 50 }), { offset: 50, limit: 50 });
});

test("formatDateTime falls back to '-' for missing/invalid values", () => {
  assert.equal(formatDateTime(null), "-");
  assert.equal(formatDateTime(undefined), "-");
  assert.equal(formatDateTime(""), "-");
  assert.equal(formatDateTime("not-a-date"), "-");
  assert.notEqual(formatDateTime("2026-08-17T10:00:00Z"), "-");
});
