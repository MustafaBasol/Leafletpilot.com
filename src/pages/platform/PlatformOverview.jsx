import { useEffect, useState } from "react";
import { platformApi } from "../../api/platformApi.js";
import { Badge, Card, Table } from "../../components/ui/index.js";
import { normalizeApiError } from "./platformOps.js";

function formatDate(value) {
  return value ? new Date(value).toLocaleString("tr-TR") : "-";
}

export function PlatformOverview() {
  const [overview, setOverview] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    platformApi.overview().then(setOverview).catch((err) => setError(normalizeApiError(err)));
  }, []);

  if (!overview && !error) return <p className="inline-result">Yükleniyor...</p>;

  return (
    <>
      <section className="page-heading">
        <div>
          <h2>Platform Kontrol</h2>
          <p>Pilot müşteri onboarding ve market hazırlığını izleyin.</p>
        </div>
      </section>
      {error ? <p className="form-error">{error}</p> : null}
      {overview ? (
        <>
          <section className="dashboard-grid">
            <Card title="Bekleyen Başvuru"><strong className="metric-value">{overview.pending_signup_count}</strong></Card>
            <Card title="Owner Bekleyen"><strong className="metric-value">{overview.markets_awaiting_owner}</strong></Card>
            <Card title="Onboarding"><strong className="metric-value">{overview.markets_onboarding}</strong></Card>
            <Card title="Hazır Market"><strong className="metric-value">{overview.ready_markets}</strong></Card>
            <Card title="Askıda"><strong className="metric-value">{overview.suspended_markets}</strong></Card>
          </section>
          <Card title="Son Platform Aktivitesi">
            <Table columns={["Aksiyon", "Hedef", "Tarih"]}>
              {(overview.recent_activity || []).map((item) => (
                <tr key={item.id}>
                  <td><Badge>{item.action}</Badge></td>
                  <td>{item.target_type} {item.target_id || ""}</td>
                  <td>{formatDate(item.created_at)}</td>
                </tr>
              ))}
              {(overview.recent_activity || []).length === 0 ? (
                <tr><td colSpan="3">Henüz platform aktivitesi yok.</td></tr>
              ) : null}
            </Table>
          </Card>
        </>
      ) : null}
    </>
  );
}
