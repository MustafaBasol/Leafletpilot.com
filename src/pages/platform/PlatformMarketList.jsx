import { useEffect, useState } from "react";
import { platformApi } from "../../api/platformApi.js";
import { Badge, Card, Table } from "../../components/ui/index.js";
import { normalizeApiError } from "./platformOps.js";
import { statusLabel, t } from "./platformI18n.js";

const lifecycleOptions = ["trial", "active", "suspended", "archived"];
const readinessOptions = ["awaiting_owner", "onboarding", "ready", "suspended", "blocked"];
const billingSyncOptions = ["ok", "error", "no_subscription"];
const billingSyncLabels = { ok: "Sağlıklı", error: "Hata", no_subscription: "Abonelik yok" };
// Mirrors backend MARKET_PLAN_FILTER_RAW_CODES (backend/app/api/routes/platform.py)
// and the public plan display names (backend/app/services/plans.py) — never
// expose the internal "standard"/"growth" codes to the platform admin UI.
const planFilterOptions = ["starter", "standard", "pro", "unassigned"];
const planLabels = { starter: "Başlangıç", standard: "Plus", pro: "Pro", unassigned: "Atanmamış" };

function ownerInvitationLabel(invitation) {
  if (!invitation) return t("none");
  return `${statusLabel(invitation.status)} · ${statusLabel(invitation.delivery_status)}`;
}

export function PlatformMarketList() {
  const [items, setItems] = useState([]);
  const [filters, setFilters] = useState({ lifecycle_status: "", readiness: "", billing_sync_status: "", plan: "" });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    setError("");
    platformApi
      .listMarkets(filters)
      .then((response) => setItems(response.items || []))
      .catch((err) => setError(normalizeApiError(err)))
      .finally(() => setLoading(false));
  }, [filters.lifecycle_status, filters.readiness, filters.billing_sync_status, filters.plan]);

  return (
    <>
      <section className="page-heading">
        <div>
          <h2>{t("markets")}</h2>
          <p>{t("marketOperationsOverview")}</p>
        </div>
      </section>
      <div className="filter-bar">
        <select value={filters.lifecycle_status} onChange={(event) => setFilters({ ...filters, lifecycle_status: event.target.value })}>
          <option value="">{t("allLifecycle")}</option>
          {lifecycleOptions.map((status) => (
            <option key={status} value={status}>{statusLabel(status)}</option>
          ))}
        </select>
        <select value={filters.readiness} onChange={(event) => setFilters({ ...filters, readiness: event.target.value })}>
          <option value="">{t("allReadiness")}</option>
          {readinessOptions.map((status) => (
            <option key={status} value={status}>{statusLabel(status)}</option>
          ))}
        </select>
        <select value={filters.billing_sync_status} onChange={(event) => setFilters({ ...filters, billing_sync_status: event.target.value })}>
          <option value="">Tüm faturalandırma durumları</option>
          {billingSyncOptions.map((status) => (
            <option key={status} value={status}>{billingSyncLabels[status]}</option>
          ))}
        </select>
        <select value={filters.plan} onChange={(event) => setFilters({ ...filters, plan: event.target.value })}>
          <option value="">Tüm planlar</option>
          {planFilterOptions.map((code) => (
            <option key={code} value={code}>{planLabels[code]}</option>
          ))}
        </select>
      </div>
      {error ? <p className="form-error">{error}</p> : null}
      <Card title={t("marketList")}>
        {loading ? <p className="inline-result">{t("loading")}</p> : null}
        {!loading && items.length === 0 ? <p className="inline-result">{t("noMarketsForFilters")}</p> : null}
        {!loading && items.length > 0 ? (
          <Table columns={[t("market"), t("lifecycle"), t("readiness"), "Faturalandırma", "Plan", t("ownerInvitation"), t("onboarding"), t("members"), ""]}>
            {items.map((market) => (
              <tr key={market.id}>
                <td><strong>{market.name}</strong><small>{market.slug}</small></td>
                <td><Badge>{statusLabel(market.lifecycle_status)}</Badge></td>
                <td><Badge>{statusLabel(market.readiness?.state)}</Badge></td>
                <td><Badge>{billingSyncLabels[market.billing?.billing_sync_status] || market.billing?.billing_sync_status}</Badge></td>
                <td><Badge>{market.subscription_plan_display || planLabels[market.subscription_plan] || market.subscription_plan}</Badge></td>
                <td>{ownerInvitationLabel(market.owner_invitation)}</td>
                <td>{statusLabel(market.onboarding_status)}</td>
                <td>{market.member_count}</td>
                <td><a className="table-action" href={`#/platform/markets/${market.id}`}>{t("open")}</a></td>
              </tr>
            ))}
          </Table>
        ) : null}
      </Card>
    </>
  );
}
