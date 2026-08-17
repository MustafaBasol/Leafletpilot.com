import { useEffect, useState } from "react";
import { platformApi } from "../../api/platformApi.js";
import { Badge, Card, Icon, Table } from "../../components/ui/index.js";
import { normalizeApiError } from "./platformOps.js";

const PLAN_LABELS = { starter: "Başlangıç", standard: "Plus", pro: "Pro", growth: "Growth (eski)", unassigned: "Atanmamış" };

const HEALTH_LABELS = {
  ok: "Sağlıklı",
  missing: "Eksik",
  inactive: "Pasif",
  duplicate: "Yinelenen",
  currency_mismatch: "Para birimi uyuşmuyor",
  amount_mismatch: "Tutar uyuşmuyor",
  stripe_error: "Stripe hatası",
  stripe_disabled: "Stripe devre dışı",
};

const SUBSCRIPTION_STATUS_LABELS = {
  incomplete: "Eksik",
  incomplete_expired: "Süresi doldu",
  trialing: "Deneme",
  active: "Aktif",
  past_due: "Gecikmiş ödeme",
  canceled: "İptal edildi",
  unpaid: "Ödenmedi",
  paused: "Duraklatıldı",
};

const WEBHOOK_STATUS_LABELS = {
  received: "Alındı",
  processed: "İşlendi",
  ignored: "Yok sayıldı",
  ignored_stale: "Eski (yok sayıldı)",
  failed: "Başarısız",
};

const ENVIRONMENT_LABELS = { live: "CANLI", sandbox: "TEST", not_configured: "Yapılandırılmadı" };

const PORTAL_STATUS_LABELS = {
  ready: "Hazır",
  not_checked: "Kontrol edilmedi",
  permission_missing: "İzin eksik",
  unavailable: "Kullanılamıyor",
};

function formatDateTime(value) {
  return value ? new Date(value).toLocaleString("tr-TR") : "-";
}

function sumCounts(byStatus, keys) {
  return keys.reduce((total, key) => total + Number(byStatus?.[key] || 0), 0);
}

function MetricCard({ icon, label, value, helper, tone = "neutral", badge }) {
  return (
    <section className={`metric-card metric-${tone}`}>
      <div className="metric-top">
        <span>
          <Icon name={icon} />
        </span>
        {badge ? <Badge tone={tone === "danger" ? "danger" : tone === "warning" ? "warning" : "success"}>{badge}</Badge> : null}
      </div>
      <p>{label}</p>
      <strong>{value}</strong>
      {helper ? <small>{helper}</small> : null}
    </section>
  );
}

function HealthSummary({ health }) {
  const activeSubscriptions = sumCounts(health.subscription_counts.by_status, ["active", "trialing"]);
  const failedWebhooks = health.webhook_counts.by_status.failed || 0;
  const stuckReceived = health.webhook_counts.stuck_received_count || 0;
  const webhookTone = failedWebhooks > 0 || stuckReceived > 0 ? "danger" : "success";

  return (
    <div className="metric-grid">
      <MetricCard
        icon="creditCard"
        label="Stripe Bağlantısı"
        value={health.stripe_enabled ? "Etkin" : "Devre dışı"}
        tone={health.stripe_enabled ? "success" : "danger"}
        helper={health.stripe_enabled ? "STRIPE_ENABLED=true" : "STRIPE_ENABLED=false"}
      />
      <MetricCard
        icon="badge"
        label="Ortam"
        value={ENVIRONMENT_LABELS[health.environment] || health.environment}
        tone={health.environment === "live" ? "warning" : "success"}
        helper={health.environment === "live" ? "Gerçek işlemler" : "Sandbox / yapılandırılmadı"}
      />
      <MetricCard
        icon="refresh"
        label="Webhook Sağlığı"
        value={`${health.webhook_counts.by_status.processed || 0} işlendi`}
        tone={webhookTone}
        helper={`${failedWebhooks} başarısız · ${stuckReceived} takılı kaldı`}
        badge={webhookTone === "danger" ? "Dikkat" : "Sağlıklı"}
      />
      <MetricCard
        icon="users"
        label="Aktif Abonelikler"
        value={activeSubscriptions}
        tone="success"
        helper="Aktif + deneme sürümündeki marketler"
      />
      <MetricCard
        icon="alert"
        label="Başarısız Webhook"
        value={failedWebhooks}
        tone={failedWebhooks > 0 ? "danger" : "success"}
        helper="Toplam başarısız Stripe webhook olayı"
      />
      <MetricCard
        icon="alert"
        label="Başarısız Ödeme/Fatura"
        value={health.webhook_counts.failed_invoice_count || 0}
        tone={health.webhook_counts.failed_invoice_count > 0 ? "danger" : "success"}
        helper="invoice.* olaylarında başarısızlık"
      />
    </div>
  );
}

function ConfigurationReadiness({ health }) {
  return (
    <Card title="Yapılandırma Hazırlığı" className="span-6">
      <dl className="detail-list">
        <div>
          <dt>Otomatik Vergi</dt>
          <dd><Badge tone={health.automatic_tax_enabled ? "success" : "neutral"}>{health.automatic_tax_enabled ? "Etkin" : "Devre dışı"}</Badge></dd>
        </div>
        <div>
          <dt>Managed Payments</dt>
          <dd><Badge tone="neutral">{health.managed_payments_disabled ? "Checkout'ta kapalı" : "Etkin"}</Badge></dd>
        </div>
        <div>
          <dt>Müşteri Portalı</dt>
          <dd>
            <Badge tone={health.portal_status === "ready" ? "success" : health.portal_status === "permission_missing" ? "danger" : "neutral"}>
              {PORTAL_STATUS_LABELS[health.portal_status] || health.portal_status}
            </Badge>
          </dd>
        </div>
      </dl>
    </Card>
  );
}

function WebhookHealthCard({ webhookCounts }) {
  const statuses = ["received", "processed", "failed", "ignored", "ignored_stale"];
  return (
    <Card title="Webhook Sağlığı" className="span-6">
      <dl className="detail-list">
        <div>
          <dt>Son işlenen</dt>
          <dd>{formatDateTime(webhookCounts.last_processed_at)}</dd>
        </div>
        <div>
          <dt>Son başarısızlık</dt>
          <dd>{webhookCounts.latest_failure_at ? `${formatDateTime(webhookCounts.latest_failure_at)} · ${webhookCounts.latest_failure_event_type}` : "-"}</dd>
        </div>
        <div>
          <dt>Takılı kalan (30dk+)</dt>
          <dd>
            <Badge tone={webhookCounts.stuck_received_count > 0 ? "warning" : "success"}>{webhookCounts.stuck_received_count}</Badge>
          </dd>
        </div>
      </dl>
      <Table columns={["Durum", "Adet"]}>
        {statuses.map((status) => (
          <tr key={status}>
            <td>{WEBHOOK_STATUS_LABELS[status] || status}</td>
            <td>{webhookCounts.by_status[status] || 0}</td>
          </tr>
        ))}
      </Table>
    </Card>
  );
}

function SubscriptionAndPlanCards({ health }) {
  const subStatuses = Object.keys(SUBSCRIPTION_STATUS_LABELS).filter((status) => health.subscription_counts.by_status[status] !== undefined);
  const planCodes = Object.keys(PLAN_LABELS).filter((code) => health.plan_distribution[code] !== undefined);
  return (
    <>
      <Card title="Abonelik Durumu" className="span-6">
        <Table columns={["Durum", "Market"]}>
          {subStatuses.map((status) => (
            <tr key={status}>
              <td>{SUBSCRIPTION_STATUS_LABELS[status]}</td>
              <td>{health.subscription_counts.by_status[status] || 0}</td>
            </tr>
          ))}
        </Table>
        <p className="inline-result">Bekleyen plan değişikliği: {health.subscription_counts.pending_change_count}</p>
      </Card>
      <Card title="Plan Dağılımı" className="span-6">
        <Table columns={["Plan", "Market"]}>
          {planCodes.map((code) => (
            <tr key={code}>
              <td>{PLAN_LABELS[code]}</td>
              <td>{health.plan_distribution[code] || 0}</td>
            </tr>
          ))}
        </Table>
      </Card>
    </>
  );
}

function AttentionMarkets({ items }) {
  return (
    <Card title="Dikkat Gerektiren Marketler" className="span-12">
      {items.length === 0 ? (
        <p className="catalog-empty">Şu anda resync gerektiren market yok.</p>
      ) : (
        <Table columns={["Market", "Plan / Durum", "Sorun", ""]}>
          {items.map((item) => (
            <tr key={item.market_id}>
              <td>{item.market_name}</td>
              <td>{PLAN_LABELS[item.plan_code] || item.plan_code}{item.status ? ` · ${SUBSCRIPTION_STATUS_LABELS[item.status] || item.status}` : ""}</td>
              <td>{item.issue}</td>
              <td>
                <a className="table-action" href={`#/platform/markets/${item.market_id}`}>
                  Detay
                </a>
              </td>
            </tr>
          ))}
        </Table>
      )}
    </Card>
  );
}

function RecentFailures({ items }) {
  return (
    <Card title="Son Faturalandırma Hataları" className="span-12">
      {items.length === 0 ? (
        <p className="catalog-empty">Kayıtlı başarısız webhook olayı yok.</p>
      ) : (
        <Table columns={["Zaman", "Olay", "Market", "Durum", "Hata"]}>
          {items.map((item, index) => (
            <tr key={`${item.event_type}-${item.occurred_at}-${index}`}>
              <td>{formatDateTime(item.occurred_at)}</td>
              <td>{item.event_type}</td>
              <td>{item.market_name || (item.market_id ? item.market_id : "-")}</td>
              <td><Badge tone="danger">{WEBHOOK_STATUS_LABELS[item.status] || item.status}</Badge></td>
              <td>{item.error || "-"}</td>
            </tr>
          ))}
        </Table>
      )}
    </Card>
  );
}

export function PlatformBilling() {
  const [health, setHealth] = useState(null);
  const [healthError, setHealthError] = useState("");
  const [healthLoading, setHealthLoading] = useState(true);
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setHealthLoading(true);
    setHealthError("");
    platformApi
      .getBillingHealth()
      .then(setHealth)
      .catch((err) => setHealthError(normalizeApiError(err)))
      .finally(() => setHealthLoading(false));

    setLoading(true);
    setError("");
    platformApi
      .getBillingPlanHealth()
      .then(setData)
      .catch((err) => setError(normalizeApiError(err)))
      .finally(() => setLoading(false));
  }, []);

  return (
    <>
      <section className="page-heading">
        <div>
          <h2>Faturalandırma</h2>
          <p>Stripe bağlantısı, webhook sağlığı, abonelik senkronizasyonu ve plan eşleştirmeleri tek ekranda.</p>
        </div>
      </section>

      {healthError ? <p className="form-error">{healthError}</p> : null}
      {healthLoading ? <p className="inline-result">Faturalandırma sağlığı yükleniyor...</p> : null}
      {!healthLoading && health ? (
        <>
          <HealthSummary health={health} />
          <section className="dashboard-grid">
            <ConfigurationReadiness health={health} />
            <WebhookHealthCard webhookCounts={health.webhook_counts} />
            <SubscriptionAndPlanCards health={health} />
            <AttentionMarkets items={health.attention_markets} />
            <RecentFailures items={health.recent_failures} />
          </section>
        </>
      ) : null}

      {error ? <p className="form-error">{error}</p> : null}
      {loading ? <p className="inline-result">Yükleniyor...</p> : null}
      {!loading && data && !data.stripe_enabled ? (
        <p className="inline-result inline-result-warning">Stripe devre dışı (STRIPE_ENABLED=false).</p>
      ) : null}
      {!loading && data ? (
        <Card title="Plan Eşleştirmeleri">
          <Table columns={["Plan", "Lookup key", "Durum", "Stripe Price", "Tutar", "Detay"]}>
            {data.plans.map((plan) => (
              <tr key={plan.plan_code}>
                <td>{PLAN_LABELS[plan.plan_code] || plan.plan_code}</td>
                <td>{plan.lookup_key}</td>
                <td><Badge tone={plan.health === "ok" ? "success" : "warning"}>{HEALTH_LABELS[plan.health] || plan.health}</Badge></td>
                <td>{plan.stripe_price_id || "-"}</td>
                <td>{plan.unit_amount !== undefined && plan.unit_amount !== null ? `${(plan.unit_amount / 100).toFixed(2)} ${plan.currency || ""}` : "-"}</td>
                <td>{plan.detail || "-"}</td>
              </tr>
            ))}
          </Table>
        </Card>
      ) : null}
    </>
  );
}
