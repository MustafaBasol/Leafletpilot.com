import { useEffect, useState } from "react";
import { platformApi } from "../../api/platformApi.js";
import { Badge, Button, Card, ConfirmDialog, EmptyState, FilterBar, Icon, Table } from "../../components/ui/index.js";
import { normalizeApiError } from "./platformOps.js";
import {
  buildIdentityQuery,
  describeConnection,
  describeMarketRole,
  formatDateTime,
  formatIdentityStatus,
  summarizeMarkets,
} from "./whatsappOps.js";

const SEARCH_DEBOUNCE_MS = 350;
const PAGE_SIZE = 50;

const statusOptions = [
  { value: "all", label: "Tümü" },
  { value: "verified", label: "Doğrulandı" },
  { value: "revoked", label: "İptal edildi" },
];

const defaultFilters = { marketId: "all", status: "all" };

function FilterSelect({ label, value, onChange, options }) {
  return (
    <label className="filter-select">
      <span>{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value)} aria-label={label}>
        {options.map((option) => (
          <option key={option.value} value={option.value}>{option.label}</option>
        ))}
      </select>
    </label>
  );
}

function ConnectionHealthCard({ health, loading, error, onTest, testing, testResult, onReload }) {
  if (loading) return <Card title="Bağlantı Sağlığı"><p className="inline-result">Yükleniyor...</p></Card>;
  if (error) return <Card title="Bağlantı Sağlığı"><p className="form-error" role="alert">{error}</p></Card>;
  if (!health) return null;

  const connection = describeConnection(health);

  return (
    <Card
      title="Bağlantı Sağlığı"
      action={<Button onClick={onReload}>Yenile</Button>}
    >
      <div className="metric-grid">
        <section className="metric-card metric-neutral">
          <div className="metric-top">
            <span><Icon name="message" /></span>
            <Badge tone={connection.tone}>{connection.label}</Badge>
          </div>
          <p>Bağlantı Durumu</p>
          <strong>{health.instance_name || "-"}</strong>
          <small>{health.base_url_host || "Evolution host bilinmiyor"}</small>
        </section>
        <section className="metric-card metric-neutral">
          <div className="metric-top">
            <span><Icon name="users" /></span>
          </div>
          <p>Doğrulanmış Kimlik</p>
          <strong>{health.verified_identity_count ?? 0}</strong>
          <small>{health.pending_verification_count ?? 0} doğrulama bekliyor</small>
        </section>
        <section className="metric-card metric-neutral">
          <div className="metric-top">
            <span><Icon name="store" /></span>
          </div>
          <p>Doğrulanmış Kullanıcısı Olan Market</p>
          <strong>{health.market_count_with_verified_users ?? 0}</strong>
        </section>
      </div>

      <dl className="detail-list">
        <div>
          <dt>Merkezi numara</dt>
          <dd>{health.official_number_masked || "-"}</dd>
        </div>
        <div>
          <dt>Son bağlantı kontrolü</dt>
          <dd>{formatDateTime(health.last_connection_check_at)}</dd>
        </div>
        <div>
          <dt>Son bağlantı hatası</dt>
          <dd>{health.last_connection_error || "-"}</dd>
        </div>
        <div>
          <dt>Son webhook</dt>
          <dd>{health.last_webhook_at ? `${formatDateTime(health.last_webhook_at)} · ${health.last_webhook_event_type || "-"}` : "-"}</dd>
        </div>
        <div>
          <dt>Son gelen mesaj</dt>
          <dd>{formatDateTime(health.last_inbound_message_at)}</dd>
        </div>
        <div>
          <dt>Son giden mesaj</dt>
          <dd>{formatDateTime(health.last_outbound_at)}</dd>
        </div>
        <div>
          <dt>Son giden mesaj hatası</dt>
          <dd>{health.last_outbound_error ? `${health.last_outbound_error} · ${formatDateTime(health.last_outbound_error_at)}` : "-"}</dd>
        </div>
      </dl>

      {health.enabled === false ? (
        <p className="inline-result">WhatsApp kanalı bu ortamda devre dışı bırakılmış. Bağlantı testi bu nedenle kullanılamıyor.</p>
      ) : (
        <>
          <div className="page-actions">
            <Button variant="primary" onClick={onTest} disabled={testing}>
              {testing ? "Test ediliyor..." : "Bağlantıyı Test Et"}
            </Button>
          </div>
          {testResult ? (
            <p className={`inline-result ${testResult.ok ? "inline-result-success" : "inline-result-warning"}`} role={testResult.ok ? "status" : "alert"}>
              {testResult.ok
                ? `Bağlantı testi başarılı (${testResult.state || "open"}).`
                : testResult.detail || "Bağlantı testi başarısız oldu."}
            </p>
          ) : null}
        </>
      )}
    </Card>
  );
}

function MarketsCell({ markets }) {
  const summary = summarizeMarkets(markets);
  if (summary.total === 0) return <span className="table-hint">Market yok</span>;
  return (
    <div className="field-stack">
      {summary.shown.map((market) => (
        <div key={market.market_id}>
          <strong>{market.market_name || market.market_slug || "Bilinmeyen market"}</strong>
          <small> · {describeMarketRole(market.role)}</small>
        </div>
      ))}
      {summary.extraCount > 0 ? <small className="table-hint">+{summary.extraCount} market daha</small> : null}
    </div>
  );
}

export function PlatformWhatsApp() {
  const [health, setHealth] = useState(null);
  const [healthLoading, setHealthLoading] = useState(true);
  const [healthError, setHealthError] = useState("");
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);

  const [markets, setMarkets] = useState([]);
  const [filters, setFilters] = useState(defaultFilters);
  const [searchTerm, setSearchTerm] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [phoneTerm, setPhoneTerm] = useState("");
  const [debouncedPhone, setDebouncedPhone] = useState("");
  const [offset, setOffset] = useState(0);

  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const [revokeTarget, setRevokeTarget] = useState(null);
  const [revokeReasons, setRevokeReasons] = useState({});
  const [revoking, setRevoking] = useState(false);

  function loadHealth() {
    setHealthLoading(true);
    setHealthError("");
    return platformApi
      .getWhatsAppHealth()
      .then(setHealth)
      .catch((err) => setHealthError(normalizeApiError(err)))
      .finally(() => setHealthLoading(false));
  }

  useEffect(() => {
    loadHealth();
    platformApi
      .listMarkets({ limit: 100 })
      .then((response) => setMarkets(response.items || []))
      .catch(() => setMarkets([]));
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(searchTerm.trim()), SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [searchTerm]);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedPhone(phoneTerm.trim()), SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [phoneTerm]);

  useEffect(() => {
    setOffset(0);
  }, [filters.marketId, filters.status, debouncedSearch, debouncedPhone]);

  function loadIdentities(nextOffset = offset) {
    setLoading(true);
    setError("");
    const params = buildIdentityQuery({
      marketId: filters.marketId,
      status: filters.status,
      search: debouncedSearch,
      phone: debouncedPhone,
      limit: PAGE_SIZE,
      offset: nextOffset,
    });
    return platformApi
      .listWhatsAppIdentities(params)
      .then((response) => {
        setItems(response.items || []);
        setTotal(response.total || 0);
      })
      .catch((err) => setError(normalizeApiError(err)))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    loadIdentities(offset);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters.marketId, filters.status, debouncedSearch, debouncedPhone, offset]);

  async function handleTestConnection() {
    if (testing) return;
    setTesting(true);
    setTestResult(null);
    try {
      const result = await platformApi.testWhatsAppConnection();
      setTestResult(result);
    } catch (err) {
      setTestResult({ ok: false, detail: normalizeApiError(err) });
    } finally {
      setTesting(false);
      await loadHealth();
    }
  }

  const hasActiveFilter = Boolean(
    filters.marketId !== "all" || filters.status !== "all" || searchTerm.trim() || phoneTerm.trim(),
  );

  function clearFilters() {
    setFilters(defaultFilters);
    setSearchTerm("");
    setDebouncedSearch("");
    setPhoneTerm("");
    setDebouncedPhone("");
  }

  function requestRevoke(identity) {
    setNotice("");
    setRevokeTarget(identity);
  }

  async function confirmRevoke() {
    if (!revokeTarget) return;
    setRevoking(true);
    setError("");
    try {
      const reason = (revokeReasons[revokeTarget.identity_id] || "").trim() || null;
      await platformApi.revokeWhatsAppIdentity(revokeTarget.identity_id, { reason });
      setRevokeTarget(null);
      setNotice(`${revokeTarget.user_full_name || revokeTarget.user_email} için WhatsApp doğrulaması kaldırıldı.`);
      await loadIdentities();
      await loadHealth();
    } catch (err) {
      setError(normalizeApiError(err));
    } finally {
      setRevoking(false);
    }
  }

  const canPrev = offset > 0;
  const canNext = offset + PAGE_SIZE < total;

  return (
    <>
      <section className="page-heading">
        <div>
          <h2>WhatsApp</h2>
          <p>Evolution API bağlantı sağlığını ve doğrulanmış WhatsApp kimliklerini yönetin.</p>
        </div>
      </section>

      <ConnectionHealthCard
        health={health}
        loading={healthLoading}
        error={healthError}
        onTest={handleTestConnection}
        testing={testing}
        testResult={testResult}
        onReload={loadHealth}
      />

      <Card title="Doğrulanmış Kullanıcılar" action={<span className="card-summary">{total} kimlik</span>}>
        <FilterBar
          searchPlaceholder="E-posta veya isimle ara"
          searchValue={searchTerm}
          onSearchChange={(event) => setSearchTerm(event.target.value)}
        >
          <FilterSelect
            label="Market"
            value={filters.marketId}
            onChange={(value) => setFilters((current) => ({ ...current, marketId: value }))}
            options={[{ value: "all", label: "Tüm marketler" }, ...markets.map((market) => ({ value: market.id, label: market.name }))]}
          />
          <FilterSelect
            label="Durum"
            value={filters.status}
            onChange={(value) => setFilters((current) => ({ ...current, status: value }))}
            options={statusOptions}
          />
          <label className="filter-select">
            <span>Telefon</span>
            <input
              type="text"
              placeholder="+33 6 12 34 56 78"
              value={phoneTerm}
              onChange={(event) => setPhoneTerm(event.target.value)}
              aria-label="Telefon numarasıyla ara"
            />
          </label>
          {hasActiveFilter ? (
            <button className="filter-reset" type="button" onClick={clearFilters}>
              <Icon name="close" /> Filtreleri Temizle
            </button>
          ) : null}
        </FilterBar>

        {error ? <p className="form-error" role="alert">{error}</p> : null}
        {notice ? <p className="inline-result inline-result-success" role="status">{notice}</p> : null}
        {loading ? <p className="inline-result">Yükleniyor...</p> : null}

        {!loading && items.length === 0 ? (
          <EmptyState title="Kayıt yok" text="Bu filtrelerde doğrulanmış WhatsApp kimliği bulunamadı." />
        ) : null}

        {!loading && items.length > 0 ? (
          <Table columns={["Kullanıcı", "Marketler", "Telefon", "Durum", "Doğrulanma", "Son Aktivite", "Aksiyonlar"]}>
            {items.map((identity) => {
              const status = formatIdentityStatus(identity.status);
              return (
                <tr key={identity.identity_id}>
                  <td>
                    <strong>{identity.user_full_name || identity.user_email}</strong>
                    <small>{identity.user_email}</small>
                  </td>
                  <td><MarketsCell markets={identity.markets} /></td>
                  <td>{identity.phone_e164 || identity.phone_masked || "-"}</td>
                  <td>
                    <Badge tone={status.tone}>{status.label}</Badge>
                    {identity.status === "revoked" && identity.revoked_reason ? (
                      <small className="table-hint">{identity.revoked_reason}</small>
                    ) : null}
                  </td>
                  <td>{formatDateTime(identity.verified_at)}</td>
                  <td>{formatDateTime(identity.last_seen_at)}</td>
                  <td className="table-actions">
                    {identity.status === "verified" ? (
                      <>
                        <label>
                          <span className="visually-hidden">Neden (isteğe bağlı)</span>
                          <input
                            type="text"
                            placeholder="Neden (isteğe bağlı)"
                            value={revokeReasons[identity.identity_id] || ""}
                            onChange={(event) =>
                              setRevokeReasons((current) => ({ ...current, [identity.identity_id]: event.target.value }))
                            }
                          />
                        </label>
                        <Button variant="danger" onClick={() => requestRevoke(identity)}>Doğrulamayı Kaldır</Button>
                      </>
                    ) : null}
                  </td>
                </tr>
              );
            })}
          </Table>
        ) : null}

        {!loading && total > 0 ? (
          <div className="table-actions">
            <Button disabled={!canPrev} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>Önceki</Button>
            <span className="card-summary">{offset + 1}-{Math.min(offset + PAGE_SIZE, total)} / {total}</span>
            <Button disabled={!canNext} onClick={() => setOffset(offset + PAGE_SIZE)}>Sonraki</Button>
          </div>
        ) : null}
      </Card>

      <ConfirmDialog
        isOpen={Boolean(revokeTarget)}
        title="WhatsApp doğrulamasını kaldır"
        description={
          revokeTarget
            ? `${revokeTarget.user_full_name || revokeTarget.user_email} kullanıcısının WhatsApp doğrulaması kaldırılacak. Kullanıcı WhatsApp komut erişimini anında kaybedecek.`
            : ""
        }
        confirmLabel="Doğrulamayı Kaldır"
        onCancel={() => setRevokeTarget(null)}
        onConfirm={confirmRevoke}
        isLoading={revoking}
      />
    </>
  );
}
