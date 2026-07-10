import { useEffect, useState } from "react";
import { platformApi } from "../../api/platformApi.js";
import { Badge, Card, Table } from "../../components/ui/index.js";
import { normalizeApiError } from "./platformOps.js";
import { t } from "./platformI18n.js";

function formatDate(value) {
  return value ? new Date(value).toLocaleString("tr-TR") : "-";
}

export function PlatformOverview() {
  const [overview, setOverview] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    platformApi.overview().then(setOverview).catch((err) => setError(normalizeApiError(err)));
  }, []);

  if (!overview && !error) return <p className="inline-result">{t("loading")}</p>;

  return (
    <>
      <section className="page-heading">
        <div>
          <h2>{t("platformControl")}</h2>
          <p>{t("platformControlOverview")}</p>
        </div>
      </section>
      {error ? <p className="form-error">{error}</p> : null}
      {overview ? (
        <>
          <section className="dashboard-grid">
            <Card title={t("pendingSignup")}><strong className="metric-value">{overview.pending_signup_count}</strong></Card>
            <Card title={t("awaitingOwner")}><strong className="metric-value">{overview.markets_awaiting_owner}</strong></Card>
            <Card title={t("onboarding")}><strong className="metric-value">{overview.markets_onboarding}</strong></Card>
            <Card title={t("readyMarket")}><strong className="metric-value">{overview.ready_markets}</strong></Card>
            <Card title={t("suspended")}><strong className="metric-value">{overview.suspended_markets}</strong></Card>
          </section>
          <Card title={t("recentPlatformActivity")}>
            <Table columns={[t("action"), t("target"), t("date")]}>
              {(overview.recent_activity || []).map((item) => (
                <tr key={item.id}>
                  <td><Badge>{item.action}</Badge></td>
                  <td>{item.target_type} {item.target_id || ""}</td>
                  <td>{formatDate(item.created_at)}</td>
                </tr>
              ))}
              {(overview.recent_activity || []).length === 0 ? (
                <tr><td colSpan="3">{t("noPlatformActivity")}</td></tr>
              ) : null}
            </Table>
          </Card>
        </>
      ) : null}
    </>
  );
}
